"""Fetch real people saying Limitless Voice's and Zoom's command words, for stress/test_command_words.py.

    python stress/tools/get_command_words.py OUT_DIR [--lang es] [--per-word 500] [--words cut,paste,delete]

Makes OUT_DIR/<word>/<speaker>_nohash_<take>.wav: 16 kHz mono 16-bit WAV, one second each, named
the way Google Speech Commands names its clips, so the tests pick them the same way (everyone's
first take before anyone's second). Up to --per-word clips a word, one per person while there are
enough people. OUT_DIR/clips.csv says which recording each one is and who said it.

The recordings are the Multilingual Spoken Words Corpus (MSWC) v1.0 from MLCommons: one-second
clips of single words, cut by forced alignment out of Mozilla Common Voice, where volunteers read
sentences aloud into their own phones and laptops. So each word was said inside a sentence, not on
its own as a command, and the alignment sometimes cuts a clip a little early or late.
Its English has no "redo" or "metronome", and no word shorter than three letters ("up").
"stop" and "forward" are fetched too: Speech Commands has them, so the two sources can be compared.
"zoom" is too: Zoom's commands start with it, but alone it isn't one.
--lang es fetches Voice's Spanish command words instead (WORDS below says which), and words that
sound like them but aren't commands ("grabación", "pagar", "corte"), to check those stay quiet.
--lang pt does the same for Brazilian Portuguese ("gravar", "pagar" and "apagar", "parte" and "pare").
Who said each clip comes from MSWC's split lists (an anonymous id and a gender per clip).

How it gets only these words: MSWC's English audio is one 35 GB .tar.gz of 6.6 million clips
(each language is one such file), in exactly the order its metadata.json lists them. A gzip file can't normally be read from the
middle, because each part copies bytes from the 32 KiB before it. So this jumps to a little before
each word, finds where a compressed block starts, and decompresses from there four times with four
different stand-ins for the missing 32 KiB: bytes that come out the same every time are right,
and the others say which missing byte they're a copy of. What those missing bytes were is worked
out from what every clip has in common: the same first 841 bytes, nearly the same tar header,
usually the same last page, and silence packets at each end. A clip is kept only if every Ogg page
in it passes its CRC, so a wrong guess loses a clip rather than changing one. That reads about
160 MB of the 35 GB, plus the 108 MB metadata and 725 MB of the split lists, in a few minutes.

The Multilingual Spoken Words Corpus, https://mlcommons.org/datasets/multilingual-spoken-words/,
is licensed CC BY 4.0 (Mazumder et al., 2021, NeurIPS Datasets and Benchmarks), and is made from
Mozilla Common Voice (CC0). Never commit the clips.
Needs `pip install numpy soundfile` (soundfile reads Ogg Opus).
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
import time
import urllib.request
import wave
import zlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

MSWC = "https://storage.googleapis.com/public-datasets-mswc"
METADATA = f"{MSWC}/metadata.json.gz"
LANG = "en"   # set by --lang
AUDIO = f"{MSWC}/audio/en.tar.gz"
SPLITS = f"{MSWC}/splits/en.tar.gz"

# The words fetched for each language. MSWC only has words said at least five times in Common
# Voice, and none shorter than three letters, so not every command is here ("sí", "deshacer").
WORDS = {
    "en": ("record play undo redo save solo mute cut copy paste delete metronome cycle mixer "
           "louder quieter zoom fit taller shorter again stop forward").split(),
    # Voice's Spanish commands that work alone with Logic Pro in front; numbers, which it listens
    # for ("compás treinta y dos"); then words that sound like a command but aren't ("grabación"
    # and "grabar", "pagar" and "pegar", "corte" and "cortar") and a few said all the time. Not
    # "corta", "pega" or "elimina": they're Cut, Paste and Delete too, only not said alone.
    "es": ("grabar graba reproduce reproducir play parar detener stop guardar guarda solo cortar "
           "copia eliminar borrar suprimir ciclo bucle adelante avanzar atrás dividir divide unir une "
           "biblioteca inspector editor editores partitura navegador explorador ayuda escape ampliar reducir "
           "arma cancelar cancela "
           "uno dos tres cuatro cinco seis siete ocho nueve diez veinte treinta "
           "grabación grabado grabó pagar paga corte corto guardia silencio mezcla parada sola unión "
           "reproducción dividido detenido cola paso nada este").split(),
    # The same for Brazilian Portuguese: its commands that work alone with Logic Pro in front
    # ("não" is cancel, "dormir" sleep, "ajuda" help); numbers; other forms of command words and
    # words said alone all the time, which Voice listens for so they're written as themselves
    # ("gravação", "pagar", which is a letter from "apagar", "isso"); and words a letter from a
    # command that Voice doesn't listen for ("parte" and "pare", "sala" and "salva", "muita" and
    # "muta"). Not "corta", "cola" or "apaga": they're Cut, Paste and Delete too, only not said alone.
    "pt": ("gravar toca tocar reproduzir parar pare salvar salva solo cortar colar apagar ciclo avançar "
           "volta voltar dividir juntar junta biblioteca navegador ajuda aproxima afasta afastar reduzir "
           "arma dormir esquece não "
           "uma dois duas três quatro cinco seis sete oito nove dez vinte trinta "
           "gravação grave tocando toque parado parada parou salvou corte cortado divisão união silêncio "
           "reprodução voltou pagar paga pagou isso nada aqui este "
           "parte sala muita copa troca aroma calar").split(),
}

PROBE = 256 * 1024  # bytes read to find out where in the archive a spot is
CHUNK = 2 * 1024 * 1024  # bytes read at a time once there
LEAD = 150  # aim this many clips before a word, so the missing 32 KiB is worked out by then
WARM = 60  # and start at least this many before it
CLOSE = 600  # read forward rather than jump again when a word starts within this many clips

downloaded = defaultdict(int)


def get(url, start=None, stop=None, what="audio"):
    """Bytes start..stop of url, or all of it. Retries a dropped or short read."""
    headers = {} if start is None else {"Range": f"bytes={start}-{stop - 1}"}
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
                data = resp.read()
            if start is not None and len(data) != stop - start:
                raise OSError(f"got {len(data)} of {stop - start} bytes")
            downloaded[what] += len(data)
            return data
        except OSError as e:
            print(f"  {url} {start}-{stop}: {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    sys.exit(f"couldn't download {url}")


def size_of(url):
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as resp:
        return int(resp.headers["Content-Length"])


# --- what's in the archive, in order ---------------------------------------------------------

class Archive:
    """audio/en.tar.gz as metadata.json lists it: 'en/', 'en/clips/', then for each word its
    folder and its clips. Member g is the g-th entry in the tar."""

    def __init__(self):
        raw = gzip.decompress(get(METADATA, what="metadata"))
        key = f'"{LANG}": '.encode()
        at = raw.find(key + b'{"language": ')
        if at < 0:
            sys.exit(f"metadata.json has no {LANG}")
        en, _ = json.JSONDecoder().raw_decode(raw[at + len(key):].decode())
        del raw
        self.files = en["filenames"]
        self.words = list(self.files)
        self.first = {}
        g, starts, ids = 2, [], ["", ""]
        for w in self.words:
            self.first[w] = g
            starts.append(g)
            ids.append("")
            ids += [f.removeprefix(f"common_voice_{LANG}_").removesuffix(".opus") for f in self.files[w]]
            g += 1 + len(self.files[w])
        self.total = g
        self.starts = np.array(starts)
        # Clip ids in member order, to find a member from the digits of its name.
        self.ids = "/" + "/".join(ids)
        self.offsets = np.cumsum([0] + [len(i) + 1 for i in ids[:-1]])

    def name(self, g):
        i = int(np.searchsorted(self.starts, g, "right")) - 1
        w, k = self.words[i], g - self.starts[i]
        return f"{LANG}/clips/{w}/" if k == 0 else f"{LANG}/clips/{w}/{self.files[w][k - 1]}"

    def find(self, pattern, lo, hi):
        """The member between lo and hi whose name fits pattern (100 bytes, -1 where unknown)."""
        runs, run = [], []
        for k, b in enumerate(list(pattern) + [-1]):
            if 48 <= b <= 57:
                run.append(k)
            else:
                if len(run) >= 5:
                    runs.append(run)
                run = []
        for run in sorted(runs, key=len, reverse=True)[:2]:
            digits = bytes(int(pattern[k]) for k in run).decode()
            found, at = set(), self.ids.find(digits)
            while at >= 0:
                g = int(np.searchsorted(self.offsets, at, "right")) - 1
                if lo <= g <= hi:
                    name = self.name(g).encode().ljust(100, b"\0")
                    if all(p < 0 or p == name[k] for k, p in enumerate(pattern)):
                        found.add(g)
                at = self.ids.find(digits, at + 1)
            if len(found) == 1:
                return found.pop()
        return None


class Layout:
    """What the archive's tar headers and clips look like, from its first megabyte.

    Every clip starts with the same 841 bytes but for its serial number and two CRCs, and every
    tar header is the same but for name, size, time and checksum. Most clips also have the same
    third-page flags and granule position, and the same 31-byte last page; those are only
    likely, so they're learnt from, but a clip still has to pass its CRCs."""

    def __init__(self):
        head = zlib.decompressobj(31).decompress(get(AUDIO, 0, 1 << 20))
        pos, self.dir, self.file, self.opus = 0, None, None, None
        third, last, packets = Counter(), Counter(), defaultdict(Counter)
        while pos + 512 <= len(head) and head[pos:pos + 512] != bytes(512):
            h = head[pos:pos + 512]
            size = int(h[124:136].rstrip(b"\0 ") or b"0", 8)
            clip = head[pos + 512:pos + 512 + size]
            if len(clip) < size:
                break
            prefix = f"{LANG}/clips/".encode()
            if h[156:157] == b"5" and h.startswith(prefix) and h[len(prefix):100].strip(b"\0").count(b"/") == 1:
                if self.dir is None:
                    self.dir = np.frombuffer(h, np.uint8).astype(np.int16)
            elif h[156:157] == b"0" and self.dir is not None:
                if self.file is None:
                    self.file = np.frombuffer(h, np.uint8).astype(np.int16)
                    self.opus = np.frombuffer(clip[:841], np.uint8).astype(np.int16)
                pages, p = [], 0
                while p + 27 <= len(clip) and clip[p:p + 4] == b"OggS":
                    pages.append(p)
                    nseg = clip[p + 26]
                    at, n = p + 27 + nseg, 0
                    for lace in clip[p + 27:p + 27 + nseg]:
                        n += lace
                        if lace < 255:
                            if n <= 8 and len(pages) > 2:
                                packets[n][clip[at:at + n]] += 1
                            at, n = at + n, 0
                    p = at
                if len(pages) == 4:
                    third[clip[pages[2] + 5:pages[2] + 14]] += 1
                    page = bytearray(clip[pages[3]:])
                    page[14:18] = page[22:26] = b"\0\0\0\0"
                    last[bytes(page)] += 1
            pos += 512 + (size + 511) // 512 * 512
        if self.file is None or bytes(self.opus[28:36].astype(np.uint8)) != b"OpusHead" \
                or bytes(self.opus[77:85].astype(np.uint8)) != b"OpusTags" or not last:
            sys.exit("the archive's first clips aren't laid out as expected")
        for h in (self.dir, self.file):
            h[:100] = -1  # name
            h[136:147] = -1  # mtime
            h[148:154] = -1  # checksum
        self.file[130:135] = -1  # size: "000000" then five octal digits; clips are under 32 KiB
        self.opus[14:18] = self.opus[22:26] = -1  # serial number and CRC of page 0
        self.opus[61:65] = self.opus[69:73] = -1  # and of page 1
        self.third = np.frombuffer(third.most_common(1)[0][0], np.uint8).astype(np.int16)
        # Short Opus packets are mostly the same few bytes: silence.
        self.packets = {n: np.frombuffer(c.most_common(1)[0][0], np.uint8).astype(np.int16)
                        for n, c in packets.items() if c.most_common(1)[0][1] * 2 > sum(c.values())}
        self.last = np.frombuffer(last.most_common(1)[0][0], np.uint8).astype(np.int16)
        self.last[18:22] = (3, 0, 0, 0)

    def header(self, name):
        h = (self.dir if name.endswith("/") else self.file).copy()
        h[:100] = np.frombuffer(name.encode().ljust(100, b"\0"), np.uint8)
        return h

    def clip(self, serial):
        c = self.opus.copy()
        c[14:18] = c[61:65] = serial
        return c

    def last_page(self, serial):
        page = self.last.copy()
        page[14:18] = serial
        page[22:26] = -1
        return page


# --- inflating from the middle ---------------------------------------------------------------

GUESSES = (bytes(32768), b"\xff" * 32768, bytes(range(256)) * 128, bytes(j >> 8 for j in range(32768)))
REVERSE = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
MAX_CLIP = 32768


def block_start(buf):
    """The first bit of buf where a compressed block starts that inflates cleanly for 64 KiB."""
    shifted = [buf] + [(int.from_bytes(buf, "little") >> s).to_bytes(len(buf), "little") for s in range(1, 8)]
    views = [memoryview(s) for s in shifted]
    for k in range(min(len(buf) - 2, len(buf) // 2)):
        for s in range(8):
            b = shifted[s][k]
            # not the last block, dynamic Huffman codes, at most 286 and 30 codes
            if b & 7 != 4 or b >> 3 > 29 or shifted[s][k + 1] & 31 > 29:
                continue
            try:
                if len(zlib.decompressobj(-15, zdict=GUESSES[0]).decompress(views[s][k:k + 131072], 65536)) >= 65536:
                    return 8 * k + s
            except zlib.error:
                pass
    return None


def ogg_crc(page):
    """Ogg's page checksum (CRC-32, polynomial 0x04c11db7, not reflected) via zlib's reflected one."""
    page = page[:22] + b"\0\0\0\0" + page[26:]
    c = zlib.crc32(page.translate(REVERSE), 0xFFFFFFFF) ^ 0xFFFFFFFF
    return int(f"{c:032b}"[::-1], 2)


def misfit(page):
    """Zero when an Ogg page's checksum matches it. Linear in the page's bytes."""
    return ogg_crc(page) ^ int.from_bytes(page[22:26], "little")


def octal(field):
    if (field < 0).any():
        return None
    try:
        return int(bytes(field.astype(np.uint8)).rstrip(b"\0 "), 8)
    except ValueError:
        return None


class Lost(Exception):
    pass


class Stream:
    """The archive inflated from a block start in the middle, without the 32 KiB before it.

    val is what came out with zeros for the missing bytes. src is -1 where that's right
    regardless, and otherwise which missing byte it's a copy of. known is what each missing
    byte has been worked out to be (-1 while unknown)."""

    def __init__(self, size, bit, first):
        self.size, self.shift, self.carry = size, bit % 8, b""
        self.next = bit // 8 + len(first)
        self.inflaters = [zlib.decompressobj(-15, zdict=g) for g in GUESSES]
        self.val, self.src, self.base = np.zeros(0, np.uint8), np.zeros(0, np.int32), 0
        self.votes = np.zeros((32768, 256), np.int32)
        self.known = np.full(32768, -1, np.int16)
        self.h = self.g = None
        self._push(first)

    def _push(self, data):
        if self.shift:
            buf = self.carry + data
            data = (int.from_bytes(buf, "little") >> self.shift).to_bytes(len(buf), "little")[:-1]
            self.carry = buf[-1:]
        a, b, lo, hi = (np.frombuffer(z.decompress(data), np.uint8) for z in self.inflaters)
        src = (hi.astype(np.int32) << 8) | lo
        src[a == b] = -1
        self.val = np.concatenate((self.val, a))
        self.src = np.concatenate((self.src, src))

    def need(self, end):
        while self.base + len(self.val) < end:
            if self.next >= self.size:
                raise Lost("end of the archive")
            stop = min(self.next + CHUNK, self.size)
            self._push(get(AUDIO, self.next, stop))
            self.next = stop

    def drop(self, upto):
        cut = upto - self.base
        self.val, self.src, self.base = self.val[cut:], self.src[cut:], upto

    def at(self, pos, n):
        """Bytes pos..pos+n as far as they're known (-1 where not)."""
        self.need(pos + n)
        i = pos - self.base
        v, s = self.val[i:i + n].astype(np.int16), self.src[i:i + n]
        copied = s >= 0
        v[copied] = self.known[s[copied]]
        return v

    def learn(self, pos, expected, weight=1):
        """These bytes should be at pos (-1 where we can't say). If none of the sure ones
        disagree, count the rest as votes for what the missing bytes were. Returns disagreements."""
        n = len(expected)
        self.need(pos + n)
        i = pos - self.base
        v, s = self.val[i:i + n], self.src[i:i + n]
        said = expected >= 0
        sure = said & (s < 0)
        wrong = int(np.count_nonzero(v[sure] != expected[sure]))
        if wrong:
            return wrong
        copied = said & (s >= 0)
        js = s[copied]
        np.add.at(self.votes, (js, expected[copied]), weight)
        js = np.unique(js)
        rows = self.votes[js]
        top, second = rows.max(1), np.partition(rows, -2, axis=1)[:, -2]
        self.known[js] = np.where(top > 2 * second, rows.argmax(1), -1)
        return 0

    def anchors(self):
        """Where clips start, from their random serial number, which each clip repeats 47 and
        841 bytes on (pages 0, 1 and 2) and which inflates right whatever the missing bytes."""
        v, sure = self.val, self.src < 0
        n = len(v) - 850
        if n <= 0:
            return []
        same = sure[:n + 3] & sure[47:n + 50] & sure[841:n + 844]
        same &= (v[:n + 3] == v[47:n + 50]) & (v[:n + 3] == v[841:n + 844])
        run = same[:n] & same[1:n + 1] & same[2:n + 2] & same[3:n + 3]
        return [self.base + int(i) - 14 for i in np.nonzero(run)[0] if i >= 14 and v[i:i + 4].any()]

    def pages(self, q, serial, layout):
        """Learn what the clip at q shows of the missing bytes, and find its Ogg pages:
        [(start, length or None)]. Each page repeats the clip's serial number 14 bytes in."""
        if self.learn(q, layout.clip(serial)):
            raise Lost("doesn't start like a clip")
        b = self.at(q, MAX_CLIP)
        hit = np.ones(MAX_CLIP - 17, bool)
        for k in range(4):
            hit &= b[14 + k:MAX_CLIP - 3 + k] == serial[k]
        starts = [q + int(p) for p in np.nonzero(hit)[0]]
        out, header = [], np.full(22, -1, np.int16)
        header[:5] = np.frombuffer(b"OggS\0", np.uint8)
        header[14:18] = serial
        for k, p in enumerate(starts):
            header[18:22] = np.frombuffer(k.to_bytes(4, "little"), np.uint8)
            if self.learn(p, header):
                break
            if k == 2 and len(starts) == 4:
                self.learn(p + 5, layout.third)
            if k == 3 and len(starts) == 4:
                self.learn(p, layout.last_page(serial))
            out.append(p)
        if len(out) < 3:
            raise Lost("its pages can't be found")
        lengths = [b - a for a, b in zip(out, out[1:])]
        head = self.at(out[-1], 27)
        segs = self.at(out[-1] + 27, max(int(head[26]), 0))
        lengths.append(None if head[26] < 0 or (segs < 0).any() else 27 + int(head[26]) + int(segs.sum()))
        return list(zip(out, lengths))

    def check(self, page_at, length, layout):
        """Does the page pass its CRC? Where bytes are still unknown, first guess short packets
        are the usual silence; then if one or two missing bytes are left, find the values that
        make it pass (the CRC is linear, so that's a small search). A page only counts as
        checked when at most 8 of its 32 CRC bits went into finding them."""
        b = self.at(page_at, length)
        i = page_at - self.base
        s = self.src[i:i + length]
        unknown = b < 0
        if not unknown.any():
            return misfit(bytes(b.astype(np.uint8))) == 0
        guessed = self.guess(b, s, layout)
        if guessed is not None:
            b = guessed
            unknown = b < 0
            if not unknown.any():
                if misfit(bytes(b.astype(np.uint8))) != 0:
                    return False
                self._settle(s, b)
                return True
        js = np.unique(s[unknown])
        if len(js) > 2:
            return False
        base = misfit(bytes(np.where(unknown, 0, b).astype(np.uint8)))
        effects = []
        for j in js:
            for bit in range(8):
                e = np.zeros(length, np.uint8)
                e[s == j] = 1 << bit
                effects.append(misfit(e.tobytes()))
        values = np.arange(256 ** len(js), dtype=np.uint32)
        acc = np.full(len(values), base, np.uint32)
        for k, e in enumerate(effects):
            acc ^= np.where((values >> k) & 1, np.uint32(e), np.uint32(0))
        hits = np.nonzero(acc == 0)[0]
        if len(hits) != 1:
            return False
        for k, j in enumerate(js):
            b[s == j] = (int(hits[0]) >> 8 * k) & 255
        self._settle(s, b)
        return len(js) == 1

    def guess(self, b, s, layout):
        """b with unknown bytes in short packets filled in with the usual packet of that
        length, or None if the segment table isn't known or a guess contradicts itself."""
        nseg = int(b[26])
        segs = b[27:27 + nseg]
        if nseg < 0 or (segs < 0).any():
            return None
        out, at, n = b.copy(), 27 + nseg, 0
        for lace in segs:
            n += int(lace)
            if lace < 255:
                part = out[at:at + n]
                usual = layout.packets.get(n)
                if usual is not None and (part < 0).any():
                    sure = part >= 0
                    if (part[sure] != usual[sure]).any():
                        return None
                    out[at:at + n] = usual
                at, n = at + n, 0
        filled = (b < 0) & (out >= 0)
        for j in np.unique(s[filled]):
            value = np.unique(out[filled & (s == j)])
            if len(value) > 1:
                return None
            out[s == j] = value[0]  # and wherever else this page copies the same missing byte
        return out

    def _settle(self, s, b):
        """A page passed its CRC with these bytes: the missing bytes it copies are now known."""
        copied = s >= 0
        js, values = s[copied], b[copied]
        self.votes[js, values] += 1000
        self.known[js] = values

    def member(self, archive, layout):
        """Read member self.g at self.h and move past it. Returns (name, clip bytes or None)."""
        name, h = archive.name(self.g), self.h
        if self.learn(h, layout.header(name)):
            raise Lost(f"{name} isn't where expected")
        if name.endswith("/"):
            self.h, self.g = h + 512, self.g + 1
            return name, None
        size = octal(self.at(h + 124, 12))
        q = h + 512
        serial = self.at(q + 14, 4)
        if (serial < 0).any():
            raise Lost(f"{name}: no serial number")
        pages = self.pages(q, serial, layout)
        start, length = pages[-1]
        if length is not None and (size is None or size == start + length - q):
            size = start + length - q
        elif size is not None and length is None:
            pages[-1] = (start, q + size - start)
        if size is None:
            raise Lost(f"{name}: can't tell where it ends")
        self.h, self.g = q + (size + 511) // 512 * 512, self.g + 1
        if pages[-1][0] + pages[-1][1] != q + size or not all([self.check(p, n, layout) for p, n in pages]):
            return name, None
        field = np.frombuffer(f"{size:011o}\0".encode(), np.uint8).astype(np.int16)
        self.learn(h + 124, field)
        self.learn(q + size, np.zeros(self.h - q - size, np.int16))
        return name, bytes(self.at(q, size).astype(np.uint8))

    def warm(self, layout):
        """Learn what the missing bytes were from every clip start inflated so far."""
        header = layout.file.copy()
        for q in self.anchors():
            if q - 512 < self.base or q + MAX_CLIP > self.base + len(self.val):
                continue
            try:
                self.pages(q, self.at(q + 14, 4), layout)
            except Lost:
                continue
            self.learn(q - 512, header)

    def resync(self, archive, lost):
        """After losing count at member lost: the next clip after it that can be named."""
        for q in self.anchors():
            if q - 512 <= self.h:
                continue
            g = archive.find(self.at(q - 512, 100), lost + 1, lost + 80)
            if g is not None:
                self.h, self.g = q - 512, g
                return True
        return False


def probe(size, archive, layout, points, c):
    """Inflate from the first block after byte c and name a member there: (stream, or None)."""
    c = max(0, min(c, size - PROBE))
    buf = get(AUDIO, c, c + PROBE)
    bit = block_start(buf)
    if bit is None:
        return None
    try:
        stream = Stream(size, 8 * c + bit, buf[bit // 8:])
    except zlib.error:
        return None
    below = [g for cc, g in points if cc <= c]
    above = [g for cc, g in points if cc > c]
    lo, hi = max(below, default=0) - 100, min(above, default=archive.total) + 100
    for q in stream.anchors():
        if q - 512 < stream.base:
            continue
        g = archive.find(stream.at(q - 512, 100), lo, hi)
        if g is not None:
            stream.h, stream.g = q - 512, g
            points.append((c + bit // 8, g))
            points.sort()
            stream.warm(layout)
            return stream
    return None


def locate(size, archive, layout, points, g0):
    """A stream that has just named a member a little before member g0."""
    target, nudge = g0 - LEAD, 0
    for attempt in range(20):
        below = max((p for p in points if p[1] <= target), key=lambda p: p[1])
        above = min((p for p in points if p[1] > target), key=lambda p: p[1])
        c = below[0] + (target - below[1]) * (above[0] - below[0]) // max(above[1] - below[1], 1)
        stream = probe(size, archive, layout, points, c - nudge)
        if stream is None:  # nothing nameable there: look a little earlier
            nudge += PROBE // 2
            continue
        if g0 - CLOSE <= stream.g <= g0 - WARM:
            return stream, attempt + 1
    sys.exit(f"couldn't find member {g0} ({archive.name(g0)})")


def fetch(archive, layout, wanted):
    """{word: {clip file name: opus bytes}} for wanted {word: set of clip file names}."""
    size = size_of(AUDIO)
    points = [(0, 0), (size, archive.total)]
    got, stream, probes = defaultdict(dict), None, 0
    for word in sorted(wanted, key=archive.first.get):
        g0 = archive.first[word]
        index = {f: g0 + 1 + k for k, f in enumerate(archive.files[word])}
        need = {index[f]: f for f in wanted[word]}
        last = max(need)
        started = time.monotonic()
        if stream is None or not (stream.g <= g0 and g0 - stream.g <= CLOSE):
            stream, n = locate(size, archive, layout, points, g0)
            probes += n
        lost = 0
        while stream.g <= last:
            g = stream.g
            try:
                name, data = stream.member(archive, layout)
            except Lost as e:
                print(f"  lost count at {archive.name(g)}: {e}", flush=True)
                lost += 1
                if lost > 20:
                    sys.exit(f"keep losing count in {word}")
                stream.need(stream.base + len(stream.val) + CHUNK)
                if stream.resync(archive, g):
                    stream.warm(layout)
                else:
                    stream, n = locate(size, archive, layout, points, max(g, g0))
                    probes += n
                continue
            if g in need and data is not None:
                got[word][need[g]] = data
            stream.drop(stream.h)
        print(f"  {word}: {len(got[word])} of {len(need)} clips read whole, {len(need) - len(got[word])} not, "
              f"{time.monotonic() - started:.0f} s", flush=True)
    return got, probes


# --- who said what ---------------------------------------------------------------------------

class Counted:
    def __init__(self, f, what):
        self.f, self.what = f, what

    def read(self, n=-1):
        data = self.f.read(n)
        downloaded[self.what] += len(data)
        return data


def speakers(words):
    """{word: [(clip file, speaker, gender, set)]} from MSWC's split lists, valid clips only."""
    want = {w.encode() for w in words}
    rows = defaultdict(list)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(SPLITS, timeout=60) as resp, \
                    tarfile.open(fileobj=Counted(resp, "splits"), mode="r|gz") as tar:
                for member in tar:
                    if member.name != f"{LANG}_splits.csv":
                        continue
                    f = tar.extractfile(member)
                    if f.readline().strip() != b"SET,LINK,WORD,VALID,SPEAKER,GENDER":
                        sys.exit(f"{LANG}_splits.csv has different columns now")
                    for line in f:
                        part = line.split(b",", 3)
                        if part[2] in want:
                            split, link, word, valid, speaker, gender = line.decode().strip().split(",")
                            if valid == "True":
                                rows[word].append((link.split("/", 1)[1], speaker, gender, split))
                    return rows
        except OSError as e:
            print(f"  {SPLITS}: {e}", flush=True)
            rows.clear()
            time.sleep(5 * (attempt + 1))
    sys.exit(f"couldn't download {SPLITS}")


def choose(rows, per_word):
    """Up to per_word clips: everyone's first take before anyone's second, in a fixed order."""
    ranked = []
    by_speaker = defaultdict(list)
    for row in rows:
        by_speaker[row[1]].append(row)
    for speaker, theirs in by_speaker.items():
        for take, row in enumerate(sorted(theirs)):
            ranked.append(((take, hashlib.sha1(speaker.encode()).hexdigest()), take, row))
    ranked.sort()
    return [(take, row) for _, take, row in ranked[:per_word]]


# --- 48 kHz Opus to 16 kHz WAV ---------------------------------------------------------------

def lowpass(factor, taps=193):
    n = np.arange(taps) - taps // 2
    cutoff = 0.45 / factor
    h = 2 * cutoff * np.sinc(2 * cutoff * n) * np.kaiser(taps, 8.0)
    return h / h.sum()


def to_wav(opus, path):
    import soundfile

    audio, rate = soundfile.read(io.BytesIO(opus), dtype="float64")
    if audio.ndim != 1 or rate % 16000:
        raise ValueError(f"expected mono at a multiple of 16 kHz, got {rate} Hz {audio.shape}")
    factor = rate // 16000
    if factor > 1:
        h = lowpass(factor)
        n = 1 << (len(audio) + len(h) - 1).bit_length()
        full = np.fft.irfft(np.fft.rfft(audio, n) * np.fft.rfft(h, n), n)
        audio = full[len(h) // 2:len(h) // 2 + len(audio)][::factor]
    pcm = np.clip(np.round(audio * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--per-word", type=int, default=500, help="most clips to keep of a word (default 500)")
    ap.add_argument("--lang", default="en", help="MSWC language code (default en)")
    ap.add_argument("--words", help="comma-separated words instead of Voice's words for the language")
    args = ap.parse_args()
    global LANG, AUDIO, SPLITS
    LANG = args.lang
    AUDIO, SPLITS = f"{MSWC}/audio/{LANG}.tar.gz", f"{MSWC}/splits/{LANG}.tar.gz"
    words = args.words.split(",") if args.words else WORDS[LANG]
    started = time.monotonic()

    print("metadata: what's in the archive, in order", flush=True)
    archive = Archive()
    missing = [w for w in words if w not in archive.first]
    words = [w for w in words if w in archive.first]
    if missing:
        print(f"  not in MSWC {LANG}: {', '.join(missing)}")
    print("split lists: who said each clip", flush=True)
    rows = speakers(words)
    chosen = {w: choose(rows[w], args.per_word) for w in words}
    layout = Layout()
    print(f"audio: {sum(map(len, chosen.values()))} clips of {len(words)} words", flush=True)
    got, probes = fetch(archive, layout, {w: {row[0] for _, row in chosen[w]} for w in words if chosen[w]})

    shutil.rmtree(args.out, ignore_errors=True)
    args.out.mkdir(parents=True)
    table, summary = [], []
    for w in words:
        (args.out / w).mkdir()
        people, genders = set(), Counter()
        for take, (clip, speaker, gender, split) in chosen[w]:
            if clip not in got[w]:
                continue
            path = args.out / w / f"{speaker[:16]}_nohash_{take}.wav"
            try:
                to_wav(got[w][clip], path)
            except (ValueError, RuntimeError) as e:
                print(f"  {w}/{clip}: {e}")
                continue
            people.add(speaker)
            genders[gender] += 1
            table.append((f"{w}/{path.name}", w, f"{w}/{clip}", speaker, gender, split))
        summary.append((w, len(archive.files[w]), len({r[1] for r in rows[w]}), len(chosen[w]),
                        sum(1 for t in table if t[1] == w), len(people),
                        f"{genders['FEMALE']}/{genders['MALE']}/{sum(genders.values()) - genders['FEMALE'] - genders['MALE']}"))
    with open(args.out / "clips.csv", "w", newline="") as f:
        csv.writer(f).writerows([("file", "word", "mswc_clip", "speaker", "gender", "set")] + table)

    print(f"\n{'word':<10} {'in MSWC':>8} {'people':>7} {'chosen':>7} {'written':>8} {'people':>7}  women/men/other or unsaid")
    for w, n, p, c, written, people, genders in summary:
        print(f"{w:<10} {n:>8} {p:>7} {c:>7} {written:>8} {people:>7}  {genders}")
    for w in missing:
        print(f"{w:<10} {'none':>8}")
    total = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file())
    print(f"\n{len(table)} clips, {total / 1e6:.0f} MB in {args.out}; downloaded "
          + ", ".join(f"{k} {v / 1e6:.0f} MB" for k, v in downloaded.items())
          + f"; {probes} jumps; {time.monotonic() - started:.0f} s")


if __name__ == "__main__":
    main()
