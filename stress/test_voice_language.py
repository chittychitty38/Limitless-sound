"""Limitless Voice's words against its speech model's vocabulary.

The command recognizer can only hear a word its model knows: given one it doesn't, it drops the
word and warns ("Ignoring word missing in vocabulary"), and the open recognizer can never write
it down. So every word of every phrase in a language must be one its model knows, spelled the
model's way ("compás", not "compas"). Words it doesn't know are spelled as words it does in the
language's sounds_like ("quantize" as "quant ties"); app names for "open ..." are left out. For
each word it doesn't know, the nearest words it does are printed.

Reads the vocabulary from the model's graph (graph/Gr.fst), so it needs no recognizer. Needs
VOSK_MODEL; VOICE_LANGUAGE says which language that model is for (default en).
"""

from __future__ import annotations

import difflib
import os
import struct
from pathlib import Path

import pytest

from conftest import need

need("voice")

from limitless_voice.actions import APP_ALIASES  # noqa: E402
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs  # noqa: E402
from limitless_voice.language import load  # noqa: E402

LANG = load(os.environ.get("VOICE_LANGUAGE") or "en")
MODEL = os.environ.get("VOSK_MODEL")


def vocabulary(model):
    """Every word the model knows: the output symbols of its grammar graph, an OpenFst file."""
    data = (Path(model) / "graph" / "Gr.fst").read_bytes()
    pos = 0

    def take(fmt):
        nonlocal pos
        value = struct.unpack_from(fmt, data, pos)[0]
        pos += struct.calcsize(fmt)
        return value

    def string():
        nonlocal pos
        n = take("<i")
        pos += n
        return data[pos - n:pos].decode("utf-8", "replace")

    assert take("<i") == 2125659606, "not an OpenFst file"
    string(), string()                 # FST and arc type
    take("<i")                         # version
    flags = take("<i")
    take("<q"), take("<q"), take("<q"), take("<q")   # properties, start state, states, arcs
    tables = []
    for bit in (1, 2):                 # input, then output symbols
        if flags & bit:
            assert take("<i") == 2125658996, "not an OpenFst symbol table"
            string()
            take("<q")
            tables.append([(string(), take("<q"))[0] for _ in range(take("<q"))])
    assert tables, "the graph has no symbol table"
    return set(tables[-1])


@pytest.mark.skipif(not MODEL, reason="set VOSK_MODEL")
def test_every_word_voice_listens_for_is_known():
    """Every word Voice's command recognizer listens for in the language is in its model."""
    known = vocabulary(MODEL)
    packs = LANG.translate(load_packs([DEFAULT_PACK_DIR], "mac"))
    app_words = {w for name in APP_ALIASES for w in name.split()}
    words = {w for phrase in LANG.recognizer_phrases(packs) for w in phrase.split()}
    unknown = sorted(w for w in words - known if w not in LANG.sounds_like and w not in app_words)
    readme = Path(MODEL) / "README"
    print(f"\n{Path(MODEL).name}: {len(known)} words. {LANG.english_name}: {len(words)} words Voice listens for, "
          f"{len(unknown)} unknown: {', '.join(unknown) or 'none'}")
    for w in unknown:
        # what to write instead: the model's own spellings nearest to it
        print(f"  {w}: closest it knows: {', '.join(difflib.get_close_matches(w, known, n=6, cutoff=0.6)) or '-'}")
    if readme.is_file():
        lines = [x.strip() for x in readme.read_text(errors="replace").splitlines() if x.strip()]
        print("Its README: " + " / ".join(lines[:4] + [x for x in lines[4:] if "licen" in x.lower()]))
    assert not unknown, f"the {Path(MODEL).name} model doesn't know: {', '.join(unknown)}"
