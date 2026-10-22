"""
A drummer's part from a finished song, for the panda to play it (and for the render tool's `song`
and `songpromo` modes):

    MDX=kuielab_a_drums.onnx ADTOF=<ADTOF-pytorch checkout> \\
        python transcribe_drums.py <song audio> <out.json> [workdir]

1. The drums are separated from the mix with KUIELab's MDX-Net drums model (ONNX; from the
   TRvlvr/model_repo releases), the reference way: 44.1 kHz, n_fft 4096, hop 1024, 2048 bins,
   chunks overlapping by half an FFT, the model run on the spectrum and its negation and averaged.
2. ADTOF (Zehren et al.; the xavriley/ADTOF-pytorch port and its weights) finds the kicks,
   snares, toms, hi-hats and cymbals, on the mix and on the separated drums; the two are averaged.
3. The song's click: a fixed tempo and phase fitted to the drums' onsets over the whole song.
   Every hit goes on it, timed to the drums' own attacks (measured on the snares and hats).
4. A drummer's reading of it:
   - velocity from each hit's own loudness in its band, against the median of its kind;
   - an open hi-hat (46) where it rings on, else closed (42);
   - toms by pitch: rack 1 (48), rack 2 (45), floor (43); a bar grooving on the toms is on
     the floor tom;
   - a cymbal or hat heard on an off-beat with the kick or snare is their crack, not a hit;
   - a crash opens a section and lands on the one after a snare roll, on the side of the hand
     keeping time (49 his left over the hats, 57 his right over the ride), in place of the hat
     or ride under it; the rest is ridden on the ride (51);
   - no hat or ride under a snare roll (both hands are on it);
   - a single eighth missing from a steady hat or ride run is put back.

Writes {"bpm", "slot", "start", "bar0", "notes": [[seconds, note, velocity], ...]}: bpm is the
click's, a slot one step of the part's grid (an eighth of the click), bars of the part start
bar0 slots after start. Needs numpy, librosa, soundfile, onnxruntime, torch, scikit-learn.
"""

import json
import os
import sys

import librosa
import numpy as np
import onnxruntime as ort
import soundfile as sf
import torch

SR = 44100
K_, S_, T_, H_, C_ = range(5)


# ---------------------------------------------------------------------------- 1. the drums alone
def separate(song, model_path, dim_t=9):
    n_fft, hop, dim_f = 4096, 1024, 2048
    dt = 2 ** dim_t
    bins = n_fft // 2 + 1
    chunk = hop * (dt - 1)
    trim = n_fft // 2
    gen = chunk - 2 * trim
    window = torch.hann_window(n_fft, periodic=True)

    def stft(x):
        s = torch.stft(x.reshape([-1, chunk]), n_fft=n_fft, hop_length=hop, window=window, center=True, return_complex=True)
        s = torch.view_as_real(s).permute([0, 3, 1, 2]).reshape([-1, 2, 2, bins, dt]).reshape([-1, 4, bins, dt])
        return s[:, :, :dim_f]

    def istft(s):
        s = torch.cat([s, torch.zeros([s.shape[0], 4, bins - dim_f, dt])], -2)
        s = s.reshape([-1, 2, 2, bins, dt]).reshape([-1, 2, bins, dt]).permute([0, 2, 3, 1]).contiguous()
        return torch.istft(torch.view_as_complex(s), n_fft=n_fft, hop_length=hop, window=window, center=True).reshape([-1, 2, chunk])

    mix, _ = librosa.load(song, sr=SR, mono=False)
    if mix.ndim == 1:
        mix = np.stack([mix, mix])
    n = mix.shape[1]
    pad = gen - n % gen
    mixp = np.concatenate([np.zeros((2, trim)), mix, np.zeros((2, pad)), np.zeros((2, trim))], 1).astype(np.float32)
    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    outs = []
    for i in range(0, n + pad, gen):
        spec = stft(torch.from_numpy(mixp[None, :, i:i + chunk]))
        a = sess.run(None, {"input": spec.numpy()})[0]
        b = sess.run(None, {"input": (-spec).numpy()})[0]
        outs.append(istft(torch.from_numpy(a * 0.5 - b * 0.5))[0, :, trim:-trim].numpy())
    return mix, np.concatenate(outs, 1)[:, :n]


# ---------------------------------------------------------------------------- 2. the hits
def adtof(paths, src):
    sys.path.insert(0, os.path.join(src, "src"))
    from adtof_pytorch.model import calculate_n_bins, create_frame_rnn_model, load_audio_for_model
    model = create_frame_rnn_model(calculate_n_bins())
    state = torch.load(os.path.join(src, "data", "adtof_frame_rnn_pytorch_weights.pth"), map_location="cpu", weights_only=True)
    model.load_state_dict(state.get("model_weights", state), strict=False)
    model.eval()
    acts = []
    with torch.no_grad():
        for p in paths:
            acts.append(model(load_audio_for_model(p))[0].numpy())
    n = min(len(a) for a in acts)
    return np.mean([a[:n] for a in acts], 0)


def peaks_of(acts, src):
    from adtof_pytorch.post_processing import FRAME_RNN_THRESHOLDS, PeakPicker
    return PeakPicker(FRAME_RNN_THRESHOLDS, fps=100).pick(acts, labels=list(range(5)))[0]


# ---------------------------------------------------------------------------- 3. the click
def fit_click(stem, lo=60.0, hi=200.0):
    """A fixed tempo and phase (of its sixteenths) fitted to the drums' onsets."""
    y = librosa.to_mono(stem)
    hop = 256
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=hop, aggregate=np.median, fmax=16000)
    dur = len(y) / SR
    tempo = float(np.atleast_1d(librosa.beat.beat_track(onset_envelope=env, sr=SR, hop_length=hop)[0])[0])
    while tempo < lo:
        tempo *= 2
    while tempo > hi:
        tempo /= 2

    def score(bpm, ph):
        g = np.arange(ph, dur, 15.0 / bpm)
        return env[np.clip(np.round(g * SR / hop).astype(int), 0, len(env) - 1)].mean()

    best = max((score(b, p), b, p) for b in np.arange(tempo - 3, tempo + 3, 0.01) for p in np.linspace(0, 15.0 / b, 24, endpoint=False))
    _, b0, p0 = best
    best = max((score(b, p), b, p) for b in np.arange(b0 - 0.02, b0 + 0.02, 0.0005) for p in np.arange(p0 - 0.006, p0 + 0.006, 0.0005))
    return best[1], best[2]


def attack_offset(stem, peaks, grid0, step):
    """Where the snares' and hats' attacks fall against the grid (s): the steepest rise of their
    band's envelope near each hit."""
    import scipy.signal as sg
    y = librosa.to_mono(stem)
    res = []
    for k, (lo, hi) in ((S_, (1500, 6000)), (H_, (7000, 15000))):
        b, a = sg.butter(4, [lo / (SR / 2), hi / (SR / 2)], btype="band")
        env = np.abs(sg.hilbert(sg.filtfilt(b, a, y)))
        env = sg.filtfilt(*sg.butter(2, 400 / (SR / 2)), env)
        d = np.diff(env, prepend=env[0])
        for t in peaks[k]:
            i0, i1 = max(0, int((t - 0.045) * SR)), int((t + 0.045) * SR)
            at = (i0 + int(np.argmax(d[i0:i1]))) / SR
            res.append(at - (grid0 + np.round((at - grid0) / step) * step))
    return float(np.median(res)) if res else 0.0


# ---------------------------------------------------------------------------- 4. a drummer's part
def part(acts, peaks, stem, bpm, phase):
    E = 60.0 / bpm / 2
    grid0 = phase + E / 2
    off = attack_offset(stem, peaks, grid0, E)
    T0 = grid0 + off
    y = librosa.to_mono(stem)
    hop = 128
    X = np.abs(librosa.stft(y, n_fft=4096, hop_length=hop))
    f = librosa.fft_frequencies(sr=SR, n_fft=4096)
    fr = lambda t: max(0, int(t * SR / hop))
    bands = {K_: (40, 120), S_: (150, 6000), T_: (60, 350), H_: (6000, 16000), C_: (5000, 16000)}
    benv = {k: X[(f >= lo) & (f < hi)].sum(0) for k, (lo, hi) in bands.items()}
    hi_env = X[f > 5000].sum(0)
    slot_of = lambda t: int(round((t - T0) / E))
    time_of = lambda s: T0 + s * E

    hits = {k: {} for k in range(5)}
    strength = {k: {} for k in range(5)}
    for k in range(5):
        for t in peaks[k]:
            s = slot_of(t)
            e = benv[k][fr(time_of(s)):fr(time_of(s) + 0.04)].max()
            hits[k][s] = max(hits[k].get(s, 0.0), float(e))
            strength[k][s] = max(strength[k].get(s, 0.0), float(acts[min(len(acts) - 1, int(round(t * 100))), k]))
    # The part's bars: where the kicks fall most in a cycle of 16 steps is its one.
    counts = np.bincount([s % 16 for s in hits[K_]], minlength=16)
    bar0 = int(np.argmax(counts))
    for k in (H_, C_):
        for s in list(hits[k]):
            if (s - bar0) % 2 == 1 and (s in hits[K_] or s in hits[S_]) and strength[k][s] < 0.75:
                del hits[k][s]

    def vel_of(k, e, top=127, floor=40):
        med = np.median(list(hits[k].values()))
        return int(np.clip(100 + 26 * np.log2(max(e, 1e-9) / med), floor, top))

    notes = [(s, 36, vel_of(K_, e)) for s, e in hits[K_].items()]
    notes += [(s, 38, vel_of(S_, e, floor=34)) for s, e in hits[S_].items()]
    for s, e in hits[T_].items():
        t = time_of(s)
        spec = X[:, fr(t + 0.02):fr(t + 0.10)].mean(1)
        m = (f > 60) & (f < 350)
        pitch = f[m][np.argmax(spec[m])]
        notes.append((s, 48 if pitch >= 170 else 45 if pitch >= 120 else 43, vel_of(T_, e)))
    grooving = {}
    for s in hits[T_]:
        grooving[(s - bar0) // 16] = grooving.get((s - bar0) // 16, 0) + 1
    notes = [(s, 43 if n in (45, 48) and grooving.get((s - bar0) // 16, 0) >= 6 and (s - bar0) % 16 < 12 else n, v) for s, n, v in notes]
    for s, e in hits[H_].items():
        t = time_of(s)
        ring = hi_env[fr(t + 0.10):fr(t + 0.16)].mean() / (hi_env[fr(t):fr(t + 0.03)].mean() + 1e-9)
        notes.append((s, 46 if ring > 0.9 else 42, vel_of(H_, e, top=118)))
    rolled = {s + 4 for s in hits[S_] if (s - bar0) % 16 == 12 and all(s + i in hits[S_] for i in range(4))}
    cs = sorted(hits[C_])
    for i, s in enumerate(cs):
        gap = s - cs[i - 1] if i else 99
        crash = gap > 8 or ((s - bar0) % 16 == 0 and (s in rolled or s - 1 in rolled or s + 1 in rolled))
        notes.append((s, 49, vel_of(C_, hits[C_][s], floor=104)) if crash else (s, 51, vel_of(C_, hits[C_][s], top=112, floor=72)))
    # Timekeeping put back where a single eighth is missing from a steady run.
    roll = set()
    for s in hits[S_]:
        if s + 1 in hits[S_] and s + 2 in hits[S_]:
            roll.update(range(s - 1, s + 4))
    for keep in (42, 51):
        hs = {s for s, n, _ in notes if n == keep or (keep == 42 and n == 46)}
        vels = [v for _, n, v in notes if n == keep]
        if not vels:
            continue
        busy = {s for s, n, _ in notes if n == 49}
        for s in sorted(hs):
            if s + 4 in hs and s + 2 not in hs and s + 2 not in roll and s + 2 not in busy \
                    and (s - 2 in hs or s - 4 in hs) and (s + 6 in hs or s + 8 in hs):
                notes.append((s + 2, keep, int(np.median(vels) * 0.92)))
                hs.add(s + 2)
    # No hat or ride under a snare roll.
    in_roll = set()
    for s in hits[S_]:
        if s + 1 in hits[S_] and s + 2 in hits[S_]:
            in_roll.update(x for x in (s, s + 1, s + 2, s + 3) if x in hits[S_])
    notes = [(s, n, v) for s, n, v in notes if not (n in (42, 46, 51) and s in in_roll)]
    # A crash replaces the timekeeping under it, on the side of the hand keeping time.
    crashes = {s for s, n, _ in notes if n == 49}
    notes = [(s, n, v) for s, n, v in notes if not (n in (42, 46, 51) and s in crashes)]
    keeping = {s: n for s, n, _ in notes if n in (42, 46, 51)}

    def side_of(s):
        near = [n for o, n in keeping.items() if 0 < abs(o - s) <= 16]
        return 57 if sum(1 for n in near if n == 51) * 2 > len(near) else 49

    notes = sorted((s, side_of(s) if n == 49 else n, v) for s, n, v in notes)
    return dict(bpm=bpm, slot=E, start=T0, bar0=bar0, notes=[[round(time_of(s), 5), n, v] for s, n, v in notes])


def main(song, out, work=None):
    work = work or os.path.dirname(os.path.abspath(out))
    mix, drums = separate(song, os.environ["MDX"])
    stem_path = os.path.join(work, "drums.wav")
    sf.write(stem_path, drums.T, SR, subtype="FLOAT")
    src = os.environ["ADTOF"]
    acts = adtof([song, stem_path], src)
    peaks = peaks_of(acts, src)
    bpm, phase = fit_click(drums)
    result = part(acts, peaks, drums, bpm, phase)
    with open(out, "w") as f:
        json.dump(result, f)
    counts = {}
    for _, n, _v in result["notes"]:
        counts[n] = counts.get(n, 0) + 1
    print("click %.3f bpm, %d notes" % (bpm, len(result["notes"])), dict(sorted(counts.items())))


if __name__ == "__main__":
    main(*sys.argv[1:4])
