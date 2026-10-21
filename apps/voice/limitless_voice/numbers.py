"""Turn spoken numbers into digits.

Speech recognizers return "go to bar thirty two" or "tempo one twenty".
We rewrite runs of number words into digits before matching commands, so
every pattern can just say {n:number}.
"""

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
SCALES = {"hundred": 100, "thousand": 1000}
# Words recognizers commonly hear in place of a number.
HOMOPHONES = {"won": "one", "too": "two", "to": "two", "for": "four", "ate": "eight", "fore": "four"}

NUMBER_WORDS = set(UNITS) | set(TENS) | set(SCALES)


def _parse_group(words):
    """Parse a strict English number ("three hundred and twelve")."""
    total, current = 0, 0
    for w in words:
        if w in UNITS:
            current += UNITS[w]
        elif w in TENS:
            current += TENS[w]
        elif w == "hundred":
            current = max(current, 1) * 100
        elif w == "thousand":
            total += max(current, 1) * 1000
            current = 0
    return total + current


def _split_groups(words):
    """Split a run like "one twenty eight" into ["one"], ["twenty", "eight"].

    A new group starts when a word can't extend the previous one, which is
    how people read tempos and bar numbers aloud.
    """
    groups, cur, last = [], [], None
    for w in words:
        if w in SCALES or w == "and":
            cur.append(w)
        elif w in UNITS:
            # "twenty" + "eight" extends; anything else after a unit/teen starts over
            if last in TENS and UNITS[w] < 10 or last in SCALES or last == "and" or last is None:
                cur.append(w)
            else:
                groups.append(cur)
                cur = [w]
        elif w in TENS:
            if last in SCALES or last == "and" or last is None:
                cur.append(w)
            else:
                groups.append(cur)
                cur = [w]
        last = w
    if cur:
        groups.append(cur)
    return groups


def words_to_number(words):
    """Return the integer a run of number words means, or None."""
    words = [w for w in words if w]
    if not words or not all(w in NUMBER_WORDS or w == "and" for w in words):
        return None
    groups = _split_groups(words)
    if len(groups) == 1:
        return _parse_group(groups[0])
    # "one twenty" -> 120, "one two eight" -> 128
    return int("".join(str(_parse_group(g)) for g in groups))


def fix_to_two(tokens):
    """Recognizers often hear "go to sleep" as "go two sleep".

    "two" followed by an ordinary word is almost always "to"; a real two is
    followed by another number, "times", or nothing.
    """
    out = list(tokens)
    for i, tok in enumerate(out[:-1]):
        nxt = out[i + 1]
        if tok == "two" and nxt not in NUMBER_WORDS and nxt not in ("times", "time", "and"):
            out[i] = "to"
    return out


def normalize_numbers(text):
    """Replace each run of number words in text with digits."""
    out, run = [], []

    def flush():
        # "and" only joins numbers after hundred/thousand; a trailing one is a real word
        tail = []
        while run and run[-1] == "and":
            tail.append(run.pop())
        if run:
            out.append(str(words_to_number(run)))
            run.clear()
        out.extend(tail)

    for tok in fix_to_two(text.split()):
        word = HOMOPHONES.get(tok, tok) if (run or _expects_number(out)) else tok
        if word in NUMBER_WORDS or (word == "and" and run and run[-1] in SCALES):
            run.append(word)
        else:
            flush()
            out.append(tok)
    flush()
    return " ".join(out)


_NUMBER_CONTEXT = {"bar", "track", "marker", "location", "tempo", "channel", "number"}


def _expects_number(out):
    # Only trust homophones ("for" -> 4) right after a word that expects a number.
    return bool(out) and out[-1] in _NUMBER_CONTEXT



def number_to_words(n):
    """12 -> "twelve", 105 -> "one hundred five". For 0..999999."""
    if n < 20:
        return next(w for w, v in UNITS.items() if v == n)
    if n < 100:
        tens = next(w for w, v in TENS.items() if v == n // 10 * 10)
        return tens + (" " + number_to_words(n % 10) if n % 10 else "")
    if n < 1000:
        rest = n % 100
        return number_to_words(n // 100) + " hundred" + (" " + number_to_words(rest) if rest else "")
    rest = n % 1000
    return number_to_words(n // 1000) + " thousand" + (" " + number_to_words(rest) if rest else "")
