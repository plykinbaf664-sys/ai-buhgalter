"""Bounded literal money/rate decoding. The model chooses spans, never amounts."""
import re
from decimal import Decimal

from app.domain import UserProblem

UNITS = dict(zip(("ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
    "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать",
    "семнадцать", "восемнадцать", "девятнадцать"), range(20)))
UNITS.update(одна=1, одну=1, две=2)
TENS = dict(zip(("двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"), range(20, 100, 10)))
HUNDREDS = dict(zip(("сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"), range(100, 1000, 100)))
SCALES = {"тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
          "миллион": 1000000, "миллиона": 1000000, "миллионов": 1000000}


def explicit_tax_rate(evidence: str) -> tuple[Decimal, str] | None:
    """An explicit percentage outranks the model's guessed with/without-tax label."""
    match = re.search(r"\b(?:ндс|vat|налог\w*|ставк\w*)\s*[:=]?\s*(.+?)\s*(?:%|процент\w*)", evidence, re.I)
    if match is None:
        return None
    if re.search(r"\bбез\b|\bno\s+vat\b", evidence, re.I):
        raise UserProblem("НДС 0% и «Без НДС» — разные режимы. Укажите один из них.")
    literal = match[1].strip()
    return explicit_decimal(literal, places=3), literal


def _integer(tokens):
    total = group = 0
    last_scale, last_rank = 10**9, 1000
    for token in tokens:
        if token in SCALES:
            scale = SCALES[token]
            if scale >= last_scale or group == 0 and last_rank != 1000:
                raise ValueError()
            total += (group or 1) * scale
            group, last_rank, last_scale = 0, 1000, scale
        else:
            value = (UNITS | TENS | HUNDREDS)[token]
            rank = 100 if value >= 100 else 10 if value >= 20 else 1
            if rank >= last_rank or last_rank == 10 and value >= 10 or value == 0 and len(tokens) > 1:
                raise ValueError()
            group += value
            last_rank = rank
    return total + group


def explicit_decimal(evidence: str, *, places: int = 2) -> Decimal:
    text = " ".join(evidence.casefold().replace("ё", "е").replace("\u00a0", " ").split()).strip()
    try:
        if len(text) > 200 or not text:
            raise ValueError()
        if re.fullmatch(r"(?:\d+|\d{1,3}(?: \d{3})+)(?:[.,]\d{1," + str(places) + r"})?", text):
            value = Decimal(text.replace(" ", "").replace(",", "."))
        else:
            tokens = text.split()
            if tokens.count("запятая") > 1:
                raise ValueError()
            if "запятая" in tokens:
                index = tokens.index("запятая")
                whole, fraction = tokens[:index], tokens[index + 1:]
                if not whole or not fraction:
                    raise ValueError()
                if all(t in UNITS and UNITS[t] < 10 for t in fraction):
                    digits = "".join(str(UNITS[t]) for t in fraction)
                else:
                    digits = str(_integer(fraction))
                if len(digits) > places:
                    raise ValueError()
                value = Decimal(str(_integer(whole)) + "." + digits)
            else:
                value = Decimal(_integer(tokens))
        if value < 0 or value > Decimal("999999999999.99"):
            raise ValueError()
        return value
    except (ValueError, KeyError, ArithmeticError):
        raise UserProblem("Укажите одно точное число: например 1500, 1500,50 или «тысяча пятьсот».") from None
