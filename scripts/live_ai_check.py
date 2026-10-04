"""Optional paid OpenAI check with fictitious inputs; no Telegram or 1C writes."""
import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import AsyncOpenAI

from app.ai import CommandInterpreter
from app.config import Settings
from app.domain import ServiceSelection, UserProblem
from app.fake_onec import FakeOneC
from app.intent import InvoiceDraft, merge_intent
from app.model_selection import OpenAIModelSelector
from app.service import InvoiceService
from app.http import ExternalFailure


async def main():
    settings = Settings.from_env()
    if settings.ai_mode != "openai":
        raise RuntimeError("AI_MODE=openai is required")
    backend = FakeOneC()
    service = InvoiceService(backend)
    async with AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(),
                           base_url="https://api.openai.com/v1", timeout=30, max_retries=0) as sdk:
        interpreter = CommandInterpreter(sdk_client=sdk, model=settings.llm_model,
            model_selector=OpenAIModelSelector(sdk) if settings.llm_model == "auto" else None)
        draft = InvoiceDraft()
        cases = (
            ("Сформируй счёт для ООО Ромашка на 1 октября 2026 за бухгалтерское обслуживание с НДС", date(2026, 10, 1), "1050.00", 1),
            ("В этот раз убери налог", date(2026, 10, 1), "1000.00", 1),
            ("Дату поменяй на пятое", date(2026, 10, 5), "1000.00", 1),
            ("Добавь ещё юридическую консультацию", date(2026, 10, 5), "1500.00", 2),
            ("Во второй строке поставь количество два", date(2026, 10, 5), "2000.00", 2),
            ("Сделай как в прошлом месяце, только с НДС на первое октября 2026", date(2026, 10, 1), "1050.00", 1),
        )
        for number, (text, expected_date, total, count) in enumerate(cases, 1):
            parsed = await interpreter.interpret(text, draft)
            assert parsed.intent is not None
            draft = merge_intent(draft, parsed.intent)
            command = draft.command()
            prepared = await service.prepare(command, "live-ai-check", 123)
            assert prepared.preview.invoice_date == expected_date
            assert prepared.preview.total == Decimal(total)
            assert len(prepared.preview.lines) == count
            assert not backend.documents
            # Use canonical adapter selections as in Bot.show_preview.
            draft = InvoiceDraft.model_validate({**draft.model_dump(), "invoice_date": prepared.preview.invoice_date,
                "services": tuple(ServiceSelection(query=line.description, quantity=line.quantity) for line in prepared.preview.lines)})
            print(f"Live LLM case {number}: validated read-only preview OK", flush=True)
        cancel = await interpreter.interpret("Отмени этот запрос", draft)
        assert cancel.intent.action == "cancel" and not backend.documents
        print("LIVE LLM OK: 7 fictitious cases; no Telegram calls or financial writes")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        # Provider exception messages can contain sensitive payloads.
        code = exc.code if isinstance(exc, ExternalFailure) else type(exc).__name__
        print(f"LIVE LLM FAILED: {code}", file=sys.stderr)
        if isinstance(exc, UserProblem):
            print(str(exc), file=sys.stderr)
        sys.exit(1)
