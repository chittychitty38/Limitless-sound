"""Turn spoken numbers into digits.

Speech recognizers return "go to bar thirty two" or "tempo one twenty".
We rewrite runs of number words into digits before matching commands, so
every pattern can just say {n:number}.

Each language gives its number words as a table (languages/<code>.yaml, "numbers"):
  units      words for a number that can't take another after it ("seven", "twelve", "veintidós")
  tens       twenty to ninety, which can ("twenty" eight, "treinta" y dos)
  hundreds   words that are a whole number of hundreds ("doscientos"); English has none
  scales     words that multiply what came before ("hundred", "thousand", "mil")
  joiners    words that join numbers, and what they may follow: English "and" after a scale
             ("one hundred and five"), Spanish "y" after tens ("treinta y dos")
  homophones words heard in place of a number, trusted only right after a word that expects one
  articles   number words that are also the article "a" (Portuguese "um", "uma"): numbers only
             right after a word that expects one, or inside a number ("trinta e um")
  misheard   number words that, before an ordinary word, are really another word ("go two sleep")
"""


class Numbers:
    def __init__(self, units, tens, hundreds=None, scales=None, joiners=None, homophones=None,
                 expects_number=(), misheard=None, misheard_unless_before=(), articles=()):
        self.units = dict(units)
        self.tens = dict(tens)
        self.hundreds = dict(hundreds or {})
        self.scales = dict(scales or {})
        self.joiners = {w: set(after) for w, after in (joiners or {}).items()}
        self.homophones = dict(homophones or {})
        self.expects = set(expects_number)
        self.misheard = dict(misheard or {})
        self.misheard_unless = set(misheard_unless_before)
        self.articles = set(articles)
        self.words = set(self.units) | set(self.tens) | set(self.hundreds) | set(self.scales)

    @classmethod
    def from_table(cls, table):
        return cls(**table)

    def _kind(self, word):
        for kind in ("units", "tens", "hundreds", "scales"):
            if word in getattr(self, kind):
                return kind
        return None

    def _may_join(self, word, last):
        return word in self.joiners and last is not None and self._kind(last) in self.joiners[word]

    def _parse_group(self, words):
        """Parse one strict number ("three hundred and twelve", "doscientos treinta y dos")."""
        total, current = 0, 0
        for w in words:
            if w in self.units:
                current += self.units[w]
            elif w in self.tens:
                current += self.tens[w]
            elif w in self.hundreds:
                current += self.hundreds[w]
            elif w in self.scales:
                if self.scales[w] < 1000:
                    current = max(current, 1) * self.scales[w]
                else:
                    total += max(current, 1) * self.scales[w]
                    current = 0
        return total + current

    def _split_groups(self, words):
        """Split a run like "one twenty eight" into ["one"], ["twenty", "eight"].

        A new group starts when a word can't extend the previous one, which is
        how people read tempos and bar numbers aloud.
        """
        groups, cur, last = [], [], None
        for w in words:
            open_ = last is None or last in self.scales or last in self.joiners or last in self.hundreds
            if w in self.scales or w in self.joiners:
                cur.append(w)
            elif w in self.units:
                # "twenty" + "eight" extends; anything else after a unit/teen starts over
                if last in self.tens and self.units[w] < 10 or open_:
                    cur.append(w)
                else:
                    groups.append(cur)
                    cur = [w]
            elif w in self.tens or w in self.hundreds:
                if open_ and not (w in self.hundreds and last in self.hundreds):
                    cur.append(w)
                else:
                    groups.append(cur)
                    cur = [w]
            last = w
        if cur:
            groups.append(cur)
        return groups

    def to_number(self, words):
        """Return the integer a run of number words means, or None."""
        words = [w for w in words if w]
        if not words or not all(w in self.words or w in self.joiners for w in words):
            return None
        groups = self._split_groups(words)
        if len(groups) == 1:
            return self._parse_group(groups[0])
        # "one twenty" -> 120, "one two eight" -> 128
        return int("".join(str(self._parse_group(g)) for g in groups))

    def fix_misheard(self, tokens):
        """Recognizers often hear "go to sleep" as "go two sleep".

        "two" followed by an ordinary word is almost always "to"; a real two is
        followed by another number, "times", or nothing.
        """
        out = list(tokens)
        for i, tok in enumerate(out[:-1]):
            nxt = out[i + 1]
            if tok in self.misheard and nxt not in self.words and nxt not in self.misheard_unless:
                out[i] = self.misheard[tok]
        return out

    def normalize(self, text):
        """Replace each run of number words in text with digits."""
        out, run = [], []

        def flush():
            # a joiner only joins numbers; a trailing one is a real word
            tail = []
            while run and run[-1] in self.joiners:
                tail.append(run.pop())
            if run:
                out.append(str(self.to_number(run)))
                run.clear()
            out.extend(tail)

        for tok in self.fix_misheard(text.split()):
            # Only trust homophones ("for" -> 4) right after a word that expects a number.
            expecting = run or (bool(out) and out[-1] in self.expects)
            word = self.homophones.get(tok, tok) if expecting else tok
            if word in self.articles and not expecting:
                word = None   # "adicionar uma faixa": the article, not 1
            if word in self.words or (run and self._may_join(word, run[-1])):
                run.append(word)
            else:
                flush()
                out.append(tok)
        flush()
        return " ".join(out)


def _english():
    from .language import ENGLISH
    return ENGLISH.numbers


def __getattr__(name):
    # English's tables, by their old names (they're read from languages/en.yaml)
    if name == "NUMBER_WORDS":
        return _english().words
    if name == "HOMOPHONES":
        return _english().homophones
    raise AttributeError(name)


def words_to_number(words):
    """English: the integer a run of number words means, or None."""
    return _english().to_number(words)


def normalize_numbers(text):
    """English: replace each run of number words in text with digits."""
    return _english().normalize(text)


def number_to_words(n):
    """12 -> "twelve", 105 -> "one hundred five". For 0..999999. English, as the suite's
    action labels are."""
    numbers = _english()
    units = {v: w for w, v in numbers.units.items()}
    tens = {v: w for w, v in numbers.tens.items()}
    if n < 20:
        return units[n]
    if n < 100:
        return tens[n // 10 * 10] + (" " + number_to_words(n % 10) if n % 10 else "")
    if n < 1000:
        rest = n % 100
        return number_to_words(n // 100) + " hundred" + (" " + number_to_words(rest) if rest else "")
    rest = n % 1000
    return number_to_words(n // 1000) + " thousand" + (" " + number_to_words(rest) if rest else "")
