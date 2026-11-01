"""Formatting only. All financial values are already validated in InvoicePreview."""
from decimal import Decimal

from app.domain import InvoicePreview


def money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ")


def quantity(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def preview_text(preview: InvoicePreview) -> str:
    preview = InvoicePreview.model_validate(preview)
    if preview.historical_proposal is not None:
        return historical_preview_text(preview)
    parts = ["Счёт к формированию", f"Компания: {preview.recipient.name}",
             f"Поставщик: {preview.issuer.name}", f"Дата счёта: {preview.invoice_date:%d.%m.%Y}",
             "Дата оказания услуги: " + (f"{preview.supply_date:%d.%m.%Y}" if preview.supply_date else "не определена")]
    if preview.service_period:
        parts.append(f"Период услуги: {preview.service_period.month:02d}.{preview.service_period.year}")
    if preview.historical_proposal:
        source = preview.historical_proposal
        parts.extend((f"Договор: {source.contract_name} ({source.contract_id})",
            f"Источник предложения: posted invoice {source.source_number} от {source.source_date:%d.%m.%Y}",
            f"ID источника: {source.source_id}",
            "Исторические цены, количества и НДС — предложение, а не действующий тариф. Проверьте каждую строку.",
            "Банковские реквизиты, условия оплаты, дата оказания и налоговые реквизиты поставщика не определены для нового счёта. Запись заблокирована."))
    elif preview.previous_reference:
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
                  f"Налоговый номер клиента: {preview.recipient.tax_number or 'не указан'}",
                  *([f"Банк: {preview.bank.bank}", f"IBAN: {preview.bank.iban}",
                     f"SWIFT: {preview.bank.swift or 'не определён'}", f"Получатель платежа: {preview.bank.beneficiary}"]
                    if preview.bank else []),
                  *([f"Условия оплаты: {preview.terms.payment}"] if preview.terms else []),
                  "", "Подтвердите, измените текстом/голосом или отмените. Подтверждение действует 5 минут."))
    if preview.user_overrides:
        parts.extend(("", manual_changes_text(preview)))
    return "\n".join(parts)


def historical_preview_text(preview: InvoicePreview) -> str:
    source = preview.historical_proposal
    parts = ["Предварительный счёт", f"Компания: {preview.recipient.name}",
             f"Поставщик по образцу: {preview.issuer.name}", f"Дата счёта: {preview.invoice_date:%d.%m.%Y}"]
    if preview.service_period:
        parts.append(f"Период услуги: {preview.service_period.month:02d}.{preview.service_period.year}")
    parts.extend((f"Договор: {source.contract_name}",
                  f"Образец: счёт №{source.source_number} от {source.source_date:%d.%m.%Y}"))
    source_map = {item.source_id: item for item in source.sources}
    for i, line in enumerate(preview.lines, 1):
        parts.extend(("", f"{i}. {line.description}",
            f"{quantity(line.quantity)} {line.uom} × {money(line.price)} {preview.currency}",
            f"Без НДС: {money(line.subtotal)}; НДС {quantity(line.tax.rate)}% ({line.tax.label}): {money(line.tax_amount)}",
            f"Сумма строки: {money(line.total)} {preview.currency}"))
        if len(source_map) > 1 and line.source_id in source_map:
            origin = source_map[line.source_id]
            parts.append(f"Образец строки: №{origin.source_number} от {origin.source_date:%d.%m.%Y}")
    parts.extend(("", f"Всего без НДС: {money(preview.subtotal)} {preview.currency}",
                  f"Всего НДС: {money(preview.tax_amount)} {preview.currency}",
                  f"Итого: {money(preview.total)} {preview.currency}", "",
                  ("Основа — указанный счёт. Ручные изменения отмечены ниже; проверьте значения."
                   if preview.user_overrides else "Цена и количество взяты из указанного счёта. Проверьте их актуальность.")))
    if preview.user_overrides:
        parts.append(manual_changes_text(preview))
    if source.contract_entity_name:
        parts.append(f"В договоре другая организация: {source.contract_entity_name}. "
                     "Поставщик нового документа пока не подтверждён.")
    if preview.execution_review is not None:
        review = preview.execution_review
        parts.extend(('', 'Учётные реквизиты предлагаются из образца. Непустые ссылки проверены в live 1С.',
            'Это явный перенос для данного черновика; актуальный тариф или defaults не утверждаются.',
            f'Оплата: 100% в дату счёта {review.payment_date:%d.%m.%Y}. Дата цен образца: {review.price_date:%d.%m.%Y}.'))
        roles = {'BankAccount_Key': 'Банковский счёт', 'PaymentTerms_Key': 'Условия оплаты',
            'PaymentTermsVersion_Key': 'Версия условий', 'AccountsReceivableGLAccount_GL_Key': 'Дебиторская задолженность',
            'AdvancesReceivedGLAccount_GL_Key': 'Полученные авансы', 'GLAccount_GL_Key': 'Учёт услуги',
            'SalesRevenueGLAccount_GL_Key': 'Выручка', 'OutputVATGLAccount_GL_Key': 'НДС'}
        for item in review.references:
            pieces = item.role.split(':')
            role = pieces[-1]
            if role in roles:
                prefix = f'Строка {pieces[1]}, ' if len(pieces) == 3 else ''
                parts.append(f'{prefix}{roles[role]}: {item.label}')
        parts.append('Подтверждение создаст один ЧЕРНОВИК в 1С. Автоматическое проведение и штатный PDF пока заблокированы.')
    else:
        parts.extend((preview.write_blocker or 'Для записи ещё нужны проверенные реквизиты, условия и дата оказания услуги.',
                      'Можно изменить запрос текстом/голосом, проверить preview или отменить.'))
    return "\n".join(parts)


def manual_changes_text(preview: InvoicePreview) -> str:
    changes = []
    for edit in preview.user_overrides:
        fields = [label for field, label in (("price", "цена без НДС"), ("amount", "сумма без НДС"), ("tax", "налог"), ("description", "название"))
                  if getattr(edit, field) is not None]
        changes.append(f"строка {edit.line_number}: {', '.join(fields)}")
    return "Изменено пользователем — " + "; ".join(changes) + (
        '. Изменения включены в подтверждаемый план черновика.' if preview.execution_review is not None else
        ". Только preview; это не изменение данных 1С.")


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
