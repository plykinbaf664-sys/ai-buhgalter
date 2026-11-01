"""Generate fictitious PDF/PNG review artifacts. No Telegram, OpenAI or real 1C."""
import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain import InvoiceCommand, ServiceSelection, TaxRequest
from app.fake_onec import FakeOneC
from app.service import InvoiceService


async def main():
    output = Path(__file__).resolve().parents[1] / "artifacts" / "invoices"
    output.mkdir(parents=True, exist_ok=True)
    for name, count, taxed, long in (("one-vat", 1, True, False), ("multi-no-vat", 3, False, False),
                                    ("long-multi-vat", 20, True, True)):
        backend = FakeOneC()
        if long:
            backend.clients["client-001"] = backend.clients["client-001"].model_copy(update={
                "display_name": "ООО «Длинное вымышленное название компании для проверки бухгалтерского счёта и переноса текста»"})
            for key, value in backend.services.items():
                backend.services[key] = value.model_copy(update={"description": value.description +
                    " / Detailed test services including reporting, document preparation and a fictitious extended description." * 3})
        queries = ("бухгалтерское обслуживание", "юридическую консультацию", "налоговую консультацию")
        command = InvoiceCommand(client="ООО Ромашка", invoice_date=date(2026, 10, 1),
            tax=TaxRequest(mode="with_tax" if taxed else "without_tax"),
            services=tuple(ServiceSelection(query=queries[i % 3], quantity=Decimal("1")) for i in range(count)))
        service = InvoiceService(backend)
        prepared = await service.prepare(command, "review", 123)
        result = await service.execute(prepared, "review", 123)
        (output / f"{name}.pdf").write_bytes(result.pdf.content)
        (output / f"{name}-preview.json").write_text(prepared.preview.model_dump_json(indent=2), encoding="utf-8")
        with pymupdf.open(stream=result.pdf.content, filetype="pdf") as doc:
            for i, page in enumerate(doc, 1):
                page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(str(output / f"{name}-{i}.png"))
            print(f"{name}: {len(doc)} pages; {count} lines; total {prepared.preview.total} AED")


if __name__ == "__main__":
    asyncio.run(main())
