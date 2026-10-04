"""Formatting only. All financial values are already validated in InvoicePreview."""
from decimal import Decimal

from app.domain import InvoicePreview


def money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ")


def quantity(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def preview_text(preview: InvoicePreview) -> str:
    preview = InvoicePreview.model_validate(preview)
    parts = ["Счёт к формированию", f"Компания: {preview.recipient.name}",
             f"Поставщик: {preview.issuer.name}", f"Дата счёта: {preview.invoice_date:%d.%m.%Y}",
             f"Дата оказания услуги: {preview.supply_date:%d.%m.%Y}"]
    if preview.service_period:
        parts.append(f"Период услуги: {preview.service_period.month:02d}.{preview.service_period.year}")
    if preview.previous_reference:
        parts.append(f"Подсказка из предыдущего счёта: {preview.previous_reference}. Цены проверены заново в 1С.")
    for i, line in enumerate(preview.lines, 1):
        parts.extend(("", f"{i}. Услуга: {line.description}", f"Количество: {quantity(line.quantity)} {line.uom}",
            f"Цена без НДС: {money(line.price)} {preview.currency}",
            f"Сумма без НДС: {money(line.subtotal)} {preview.currency}",
            f"Налог: {line.tax.label}; ставка {quantity(line.tax.rate)}%",
            f"НДС: {money(line.tax_amount)} {preview.currency}", f"Сумма строки: {money(line.total)} {preview.currency}"))
    parts.extend(("", f"Всего без НДС: {money(preview.subtotal)} {preview.currency}",
                  f"Всего НДС: {money(preview.tax_amount)} {preview.currency}",
                  f"Итого: {money(preview.total)} {preview.currency}",
                  f"Налоговый номер клиента: {preview.recipient.tax_number}",
                  f"Банк: {preview.bank.bank}", f"IBAN: {preview.bank.iban}",
                  f"SWIFT: {preview.bank.swift}", f"Получатель платежа: {preview.bank.beneficiary}",
                  f"Условия оплаты: {preview.terms.payment}",
                  "", "Подтвердите, измените текстом/голосом или отмените. Подтверждение действует 5 минут."))
    return "\n".join(parts)


def message_chunks(text: str) -> tuple[str, ...]:
    chunks, current = [], ""
    for line in text.splitlines():
        if len(line) > 4000:
            raise ValueError("Unbounded response line")
        if len(current) + len(line) + 1 > 4000:
            chunks.append(current); current = ""
        current += ("\n" if current else "") + line
    if current:
        chunks.append(current)
    return tuple(chunks)
