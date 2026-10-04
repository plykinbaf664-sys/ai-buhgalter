import re

from app.domain import InvoiceCommand, UserProblem

MONTHS = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)
PATTERN = re.compile(
    r'(?:сформируй|создай|сделай) сч[её]т для '
    r'(?P<client>[А-Яа-яЁёA-Za-z0-9 «»"\-]{2,180})'
    r' за (?P<month>' + "|".join(MONTHS) + r') (?P<year>20\d{2}|2100)\.?',
    re.IGNORECASE,
)
HELP = 'Укажите одну команду и год: «Сформируй счёт для ООО Ромашка за сентябрь 2026».'


def parse_command(text: str) -> InvoiceCommand:
    # Stage 1 deliberately accepts a narrow grammar. No guessed year or amount.
    if len(text) > 1000 or any(ord(char) < 32 for char in text):
        raise UserProblem(HELP)
    match = PATTERN.fullmatch(" ".join(text.strip().split()))
    if not match:
        raise UserProblem(HELP)
    # A legacy name must not swallow additional invoice parameters. Such input
    # belongs to the structured language interpreter, not this compatibility grammar.
    if re.search(r"\b(?:за|на|с|со|без|как|количество)\b", match["client"], re.I):
        raise UserProblem(HELP)
    return InvoiceCommand(
        client=match["client"], year=int(match["year"]),
        month=MONTHS.index(match["month"].lower()) + 1,
    )
