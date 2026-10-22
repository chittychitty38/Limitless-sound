// Built-in instrument so GazeStage sounds good with no DAW or MIDI setup at all.
// Two voices: "Soft keys" (a warm electric-piano tone) and "Warm pad" (slow, wide strings).

const PRESETS = {
  keys: { name: 'Soft keys', attack: 0.005, decay: 1.6, sustain: 0.25, release: 0.6, gain: 0.32, reverb: 0.22 },
  pad: { name: 'Warm pad', attack: 0.35, decay: 0.8, sustain: 0.75, release: 1.4, gain: 0.16, reverb: 0.38 },
};
export const SYNTH_PRESETS = Object.fromEntries(Object.entries(PRESETS).map(([k, v]) => [k, v.name]));

export class Synth {
  constructor() { this.ctx = null; this.voices = new Map(); this.preset = 'keys'; }

  ensure() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return this.ctx; }
    const ctx = this.ctx = new AudioContext({ latencyHint: 'interactive' });
    this.master = ctx.createGain(); this.master.gain.value = 0.9;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14; comp.ratio.value = 4; comp.attack.value = 0.003; comp.release.value = 0.2;
    this.dry = ctx.createGain(); this.wet = ctx.createGain();
    this.reverb = ctx.createConvolver(); this.reverb.buffer = this.impulse(2.6);
    // The tone pad can shape the built-in sound: brightness (a low-pass) and room (reverb).
    this.shapeFilter = ctx.createBiquadFilter(); this.shapeFilter.type = 'lowpass';
    this.shapeFilter.frequency.value = 20000; this.shapeFilter.Q.value = 0.9;
    this.dry.connect(comp); this.wet.connect(this.reverb).connect(comp);
    comp.connect(this.shapeFilter).connect(this.master).connect(ctx.destination);
    this.setPreset(this.preset);
    return ctx;
  }

  // x, y: 0..1 from the tone pad, or null to put the sound back to its preset.
  shape(x, y) {
    this.shaping = x == null ? null : [x, y];
    if (!this.ctx) return;
    const t = this.ctx.currentTime, p = PRESETS[this.preset];
    const freq = x == null ? 20000 : 250 * 2 ** (x * 6.3);
    const wet = x == null ? p.reverb : 0.05 + y * 0.75, dry = x == null ? 1 - p.reverb * 0.5 : 1 - y * 0.4;
    this.shapeFilter.frequency.setTargetAtTime(freq, t, 0.03);
    this.wet.gain.setTargetAtTime(wet, t, 0.05); this.dry.gain.setTargetAtTime(dry, t, 0.05);
  }

  // Decaying stereo noise: a small, soft room.
  impulse(seconds) {
    const ctx = this.ctx, len = Math.floor(ctx.sampleRate * seconds), buf = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const d = buf.getChannelData(ch);
      for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3.2);
    }
    return buf;
  }

  setPreset(name) {
    this.preset = PRESETS[name] ? name : 'keys';
    if (!this.ctx) return;
    if (this.shaping) { this.shape(...this.shaping); return; }
    const p = PRESETS[this.preset];
    this.wet.gain.value = p.reverb; this.dry.gain.value = 1 - p.reverb * 0.5;
  }
  setVolume(v) { this.ensure(); this.master.gain.value = v; }

  noteOn(note, velocity = 100) {
    const ctx = this.ensure();
    this.noteOff(note, true);
    const p = PRESETS[this.preset], t = ctx.currentTime, f = 440 * 2 ** ((note - 69) / 12);
    const amp = ctx.createGain(), peak = p.gain * (0.35 + 0.65 * velocity / 127);
    amp.gain.setValueAtTime(0, t);
    amp.gain.linearRampToValueAtTime(peak, t + p.attack);
    amp.gain.setTargetAtTime(peak * p.sustain, t + p.attack, p.decay / 3);
    const pan = ctx.createStereoPanner(); pan.pan.value = Math.max(-0.5, Math.min(0.5, (note - 64) / 40));
    amp.connect(pan); pan.connect(this.dry); pan.connect(this.wet);
    const oscs = [];
    if (this.preset === 'keys') {
      // Two-operator FM: a sine carrier with a bright, fast-decaying modulator (tine attack).
      const car = ctx.createOscillator(), mod = ctx.createOscillator(), modGain = ctx.createGain();
      car.frequency.value = f; mod.frequency.value = f * 2;
      modGain.gain.setValueAtTime(f * 1.4 * (velocity / 127 + 0.3), t);
      modGain.gain.setTargetAtTime(f * 0.15, t, 0.25);
      mod.connect(modGain).connect(car.frequency);
      const body = ctx.createOscillator(); body.type = 'triangle'; body.frequency.value = f;
      const bodyGain = ctx.createGain(); bodyGain.gain.value = 0.35;
      body.connect(bodyGain).connect(amp); car.connect(amp);
      oscs.push(car, mod, body);
    } else {
      // Three detuned saws through a soft low-pass filter.
      const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.Q.value = 0.5;
      lp.frequency.setValueAtTime(600, t); lp.frequency.linearRampToValueAtTime(Math.min(3200, f * 6), t + p.attack * 2);
      lp.connect(amp);
      for (const cents of [-9, 0, 8]) {
        const o = ctx.createOscillator(); o.type = 'sawtooth'; o.frequency.value = f; o.detune.value = cents;
        o.connect(lp); oscs.push(o);
      }
    }
    oscs.forEach(o => o.start(t));
    this.voices.set(note, { amp, oscs, release: p.release });
  }

  noteOff(note, immediate = false) {
    const v = this.voices.get(note); if (!v) return;
    this.voices.delete(note);
    const t = this.ctx.currentTime, r = immediate ? 0.02 : v.release;
    v.amp.gain.cancelScheduledValues(t);
    v.amp.gain.setValueAtTime(v.amp.gain.value, t);
    v.amp.gain.setTargetAtTime(0, t, r / 4);
    v.oscs.forEach(o => o.stop(t + r + 0.1));
  }

  allOff() { for (const n of [...this.voices.keys()]) this.noteOff(n); }

  // A short, quiet click to confirm a selection (optional feedback for the player).
  tick() {
    const ctx = this.ensure(), t = ctx.currentTime;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = 1500; g.gain.setValueAtTime(0.08, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.05);
    o.connect(g).connect(this.master); o.start(t); o.stop(t + 0.06);
  }
}
