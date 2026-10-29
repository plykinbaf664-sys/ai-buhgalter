"""Local name comparison only: similarity suggests candidates, never identities."""
import re
import unicodedata
from difflib import SequenceMatcher


def tokens(value: str) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return tuple(re.findall(r"[^\W_]+", text, re.UNICODE))


def exact_key(value: str) -> str:
    # Preserve every letter/digit. Case, punctuation and word spacing are immaterial.
    return "".join(tokens(value))


_CYRILLIC = dict(zip("абвгдежзийклмнопрстуфхцчшщыэюяьъ",
    ("a", "b", "v", "g", "d", "e", "zh", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
     "kh", "ts", "ch", "sh", "shch", "y", "e", "yu", "ya", "", "")))
_LETTERS = {"эй": "a", "би": "b", "бэ": "b", "си": "c", "ди": "d", "дэ": "d", "и": "e", "эф": "f",
    "джи": "g", "эйч": "h", "ай": "i", "джей": "j", "кей": "k", "кэй": "k", "эл": "l", "эль": "l",
    "эм": "m", "эн": "n", "оу": "o", "пи": "p", "пэ": "p", "кью": "q", "ар": "r", "эр": "r",
    "эс": "s", "ти": "t", "тэ": "t", "ю": "u", "ви": "v", "экс": "x", "уай": "y", "зет": "z", "зэд": "z", "зи": "z"}
_LETTER_SYLLABLES = tuple(sorted(_LETTERS, key=len, reverse=True))
_BUSINESS_WORDS = {"груп": "group", "групп": "group", "группа": "group", "гроуп": "group",
    "фзко": "fzco", "фзсо": "fzco", "эфзетсиоу": "fzco", "элэлси": "llc", "лимитед": "limited"}
_BUSINESS_PARTS = re.compile("(" + "|".join(sorted(_BUSINESS_WORDS, key=len, reverse=True)) + ")")
_LEGAL = {"llc", "ltd", "limited", "inc", "fzco", "fze", "fzllc", "ooo", "ооо", "ао", "ип"}
_GENERIC = {"компания", "компании", "компанию", "фирма", "фирмы", "организация", "организации"}


def _voice_word(word: str) -> str:
    if word in _BUSINESS_WORDS:
        return _BUSINESS_WORDS[word]
    remaining, letters = word, []
    while remaining:
        syllable = next((s for s in _LETTER_SYLLABLES if remaining.startswith(s)), None)
        if syllable is None:
            break
        letters.append(_LETTERS[syllable])
        remaining = remaining[len(syllable):]
    if not remaining and letters:
        return "".join(letters)
    if letters and remaining in _BUSINESS_WORDS:
        return "".join(letters) + _BUSINESS_WORDS[remaining]
    return "".join(_CYRILLIC.get(c, c) for c in word)


def _voice_tokens(value: str) -> tuple[str, ...]:
    # STT may glue acronym, group and legal-form words together.
    parts = [p for w in tokens(value) if w not in _GENERIC for p in _BUSINESS_PARTS.split(w) if p]
    words = [_voice_word(w) for w in parts]
    # Join spoken individual acronym letters, then remove optional legal forms.
    joined = []
    acronym = ""
    for word in words + [""]:
        if len(word) == 1 and word.isalpha() and word.isascii():
            acronym += word
        else:
            if acronym:
                joined.append(acronym)
                acronym = ""
            if word:
                joined.append(word)
    return tuple(w for w in joined if w not in _LEGAL)


def _sound_key(value: str) -> str:
    # Approximate retrieval only: Cyrillic к may represent Latin c, and final e may be silent.
    value = value.replace("ph", "f").replace("ck", "k").replace("qu", "kv")
    value = re.sub(r"c(?=[eiy])", "s", value).replace("c", "k").replace("q", "k")
    value = re.sub(r"([a-z])\1+", r"\1", value)
    return value[:-1] if len(value) > 4 and value.endswith("e") else value


def _word_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    # One insertion/deletion/substitution or adjacent transposition, before
    # phonetic folding removes letters. Retrieval only; never selects identity.
    if min(len(left), len(right)) >= 3 and _one_typo(left, right):
        return .9 if min(len(left), len(right)) >= 4 else .85
    left, right = _sound_key(left), _sound_key(right)
    if min(len(left), len(right)) < 4:
        if len(left) == len(right) == 3 and sum(a != b for a, b in zip(left, right)) <= 1:
            return .85
        return 0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _one_typo(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        different = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        return len(different) <= 1 or (len(different) == 2
            and different[1] == different[0] + 1
            and left[different[0]] == right[different[1]]
            and left[different[1]] == right[different[0]])
    shorter, longer = sorted((left, right), key=len)
    first = next((i for i, (a, b) in enumerate(zip(shorter, longer)) if a != b), len(shorter))
    return shorter[first:] == longer[first + 1:]


def similarity(query: str, name: str) -> float:
    """Conservative ranking for explicit user selection; never an auto-match rule."""
    query_words, name_words = _voice_tokens(query), _voice_tokens(name)
    q, n = "".join(query_words), "".join(name_words)
    if not q or not n or len(q) < 3:
        return 0
    if q == n:
        return .99
    if q in n:
        return .94
    if len(q) < 5:
        # One misheard letter in a short spoken acronym still yields choices.
        # Two-letter queries stay blocked; this never changes exact identity.
        if len(query_words) == 1 and len(q) >= 3 and any(
                len(word) == len(q) and sum(a != b for a, b in zip(q, word)) == 1
                for word in name_words):
            return .82
        return 0
    if len(_sound_key(q)) >= 4 and _sound_key(q) in _sound_key(n):
        return .93
    # Word order and minor transcription/spelling variations only affect suggestions.
    ratio = max(SequenceMatcher(None, q, n, autojunk=False).ratio(),
        SequenceMatcher(None, " ".join(sorted(query_words)), " ".join(sorted(name_words)), autojunk=False).ratio())
    # A short spoken brand can match one word inside a much longer legal company name.
    # Require every query word to have its own strong token match; never auto-select it.
    available = list(name_words)
    scores = []
    for word in query_words:
        best = max(((_word_similarity(word, other), i) for i, other in enumerate(available)), default=(0, -1))
        if best[0] < .8:
            break
        scores.append(best[0])
        available.pop(best[1])
    if len(scores) == len(query_words):
        ratio = max(ratio, min(scores) * .98)
    return ratio if ratio >= .78 else 0
