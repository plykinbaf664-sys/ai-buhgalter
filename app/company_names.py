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
        return 0
    # Word order and minor transcription/spelling variations only affect suggestions.
    ratio = max(SequenceMatcher(None, q, n, autojunk=False).ratio(),
        SequenceMatcher(None, " ".join(sorted(query_words)), " ".join(sorted(name_words)), autojunk=False).ratio())
    return ratio if ratio >= .78 else 0
