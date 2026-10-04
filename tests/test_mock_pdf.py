import asyncio
from datetime import date
from decimal import Decimal

import pymupdf
import pytest
from pydantic import ValidationError

from app.domain import InvoiceCommand, InvoiceLine, ServiceSelection, TaxProfile, TaxRequest
from app.fake_onec import FakeOneC
from app.mock_pdf import render_mock_pdf
from app.presentation import money, preview_text
from app.service import InvoiceService


async def sample(line_count=1, taxed=True, long=False):
    backend = FakeOneC()
    if long:
        backend.clients["client-001"] = backend.clients["client-001"].model_copy(update={
            "display_name": 'ООО «Очень длинное вымышленное название компании для проверки переноса текста ' + 'Тестовые услуги ' * 6 + '»'})
        for key, item in backend.services.items():
            backend.services[key] = item.model_copy(update={"description": item.description +
                " / Detailed fictitious professional services with a long scope of work, supporting documents and reporting." * 3})
    queries = ("бухгалтерское обслуживание", "юридическую консультацию", "налоговую консультацию")
    command = InvoiceCommand(client="ООО Ромашка", invoice_date=date(2026, 10, 1),
        tax=TaxRequest(mode="with_tax" if taxed else "without_tax"),
        services=tuple(ServiceSelection(query=queries[i % 3], quantity=Decimal("1.125") if i == 1 else Decimal("1"))
                       for i in range(line_count)))
    service = InvoiceService(backend)
    prepared = await service.prepare(command, "pdf-test", 123)
    result = await service.execute(prepared, "pdf-test", 123)
    return prepared.preview, result.pdf.content


@pytest.mark.parametrize("count,taxed,long", [(1, True, False), (1, False, False), (3, True, False),
    (3, False, True), (20, True, True), (20, False, True)])
def test_pdf_opens_wraps_and_matches_confirmed_preview(count, taxed, long):
    preview, data = asyncio.run(sample(count, taxed, long))
    assert render_mock_pdf(preview).content == data
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        text = " ".join(" ".join(page.get_text().split()) for page in doc)
        assert "TAX INVOICE" in text and "TEST / MOCK" in text
        assert " ".join(preview.recipient.name.split()) in text
        assert "01.10.2026" in text
        for line in preview.lines:
            assert " ".join(line.description.split()) in text
            for value in (line.price, line.subtotal, line.tax_amount, line.total):
                assert money(value) in text and money(value) in preview_text(preview)
        for value in (preview.subtotal, preview.tax_amount, preview.total):
            assert money(value) in text and money(value) in preview_text(preview)
        assert preview.amount_in_words in text
        assert "Released By" in text and "Received By" in text
        if count == 20:
            assert len(doc) > 1
        for page in doc:
            image = page.get_pixmap(matrix=pymupdf.Matrix(.5, .5))
            assert image.width > 0 and image.height > 0
            # Every extracted word must remain inside printable page bounds.
            for x0, y0, x1, y1, *_ in page.get_text("words"):
                assert 20 <= x0 < x1 <= page.rect.width - 20
                assert 10 <= y0 < y1 <= page.rect.height - 10


def test_external_arithmetic_and_invalid_money_cannot_be_accepted():
    preview, _ = asyncio.run(sample())
    line = preview.lines[0]
    with pytest.raises(ValidationError):
        InvoiceLine.model_validate({**line.model_dump(), "total": Decimal("1")})
    with pytest.raises(ValidationError):
        InvoiceLine.model_validate({**line.model_dump(), "price": Decimal("NaN")})
    with pytest.raises(ValidationError):
        TaxProfile(tax_id="bad", label="bad", treatment="exempt", rate=Decimal("5"))
