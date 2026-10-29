import asyncio
import json
from types import SimpleNamespace

import httpx2
import pytest
from openai import AsyncOpenAI
from pydantic import SecretStr

from app.ai import CommandInterpreter
from app.ai import Extraction
from app.domain import InvoiceCommand
from app.http import ExternalFailure
from app.model_selection import OpenAIModelSelector
from app.voice import AudioFile, SpeechToText, Transcript

AUDIO = b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 32
NATURAL = "Выстави, пожалуйста, счёт ООО Ромашка за сентябрь 2026"


def fake_sdk_model(model_id):
    return SimpleNamespace(id=model_id, model_dump=lambda: {"id": model_id})


class FakeModels:
    def __init__(self, names=(), error=None):
        self.names, self.error, self.calls = names, error, 0

    def list(self):
        async def items():
            self.calls += 1
            if self.error is not None:
                raise self.error
            for name in self.names:
                yield fake_sdk_model(name)
        return items()


@pytest.mark.parametrize("available,llm,stt", [
    (("gpt-5-mini", "gpt-4o-mini", "gpt-4o-mini-transcribe"),
     "gpt-5-mini", "gpt-4o-mini-transcribe"),
    (("gpt-4o-mini", "gpt-4o-transcribe"),
     "gpt-4o-mini", "gpt-4o-transcribe"),
])
def test_selects_supported_available_models_once(available, llm, stt):
    models = FakeModels(available)
    selector = OpenAIModelSelector(SimpleNamespace(models=models))

    async def scenario():
        return await selector.llm(), await selector.stt(), await selector.llm()

    assert asyncio.run(scenario()) == (llm, stt, llm)
    assert models.calls == 1


@pytest.mark.parametrize("available,operation,code", [
    (("unrelated-model",), "llm", "llm_model_unavailable"),
    (("gpt-4o-mini",), "stt", "stt_model_unavailable"),
])
def test_unsupported_catalog_fails_closed(available, operation, code):
    selector = OpenAIModelSelector(SimpleNamespace(models=FakeModels(available)))
    with pytest.raises(ExternalFailure) as failure:
        asyncio.run(getattr(selector, operation)())
    assert failure.value.code == code


def test_discovery_error_does_not_leak_credentials(caplog):
    secret = "sk-private-test-secret"
    selector = OpenAIModelSelector(SimpleNamespace(models=FakeModels(error=RuntimeError(secret))))
    with pytest.raises(ExternalFailure) as failure:
        asyncio.run(selector.llm())
    assert failure.value.code == "model_discovery_failed"
    assert secret not in caplog.text and secret not in str(failure.value)


def test_sdk_catalog_and_shared_pipeline_use_selected_models():
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx2.Response(200, json={"object": "list", "data": [
                {"id": name, "object": "model", "created": 1, "owned_by": "openai"}
                for name in ("gpt-4o-mini", "gpt-4o-mini-transcribe")
            ]})
        if request.url.path.endswith("/audio/transcriptions"):
            return httpx2.Response(200, json={
                "text": NATURAL, "logprobs": [{"token": "word", "logprob": -0.1}],
            })
        if request.url.path.endswith("/responses"):
            return httpx2.Response(200, json={
                "id": "resp_test", "object": "response", "created_at": 1,
                "status": "completed", "model": "gpt-4o-mini", "output": [{
                    "id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": Extraction(
                        action="create_invoice", client="ООО Ромашка", year=2026, month=9,
                    ).model_dump_json(), "annotations": []}],
                }],
            })
        pytest.fail("Unexpected OpenAI API path")

    async def scenario():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as transport:
            sdk = AsyncOpenAI(api_key="sk-test", base_url="https://api.openai.com/v1",
                              http_client=transport, max_retries=0)
            selector = OpenAIModelSelector(sdk)
            transcript = await SpeechToText(
                None, SecretStr("sk-test"), "auto", sdk_client=sdk, model_selector=selector,
            ).transcribe(AudioFile(content=AUDIO))
            interpreted = await CommandInterpreter(
                api_key=SecretStr("sk-test"), model="auto", sdk_client=sdk,
                model_selector=selector,
            ).interpret(transcript.text)
            await sdk.close()
            return transcript, interpreted

    transcript, interpreted = asyncio.run(scenario())
    assert isinstance(transcript, Transcript)
    assert isinstance(interpreted.command, InvoiceCommand)
    assert interpreted.needs_confirmation
    assert sum(request.url.path.endswith("/models") for request in requests) == 1
    assert len(requests) == 3
    llm_request = next(request for request in requests if request.url.path.endswith("/responses"))
    stt_request = next(request for request in requests if request.url.path.endswith("/audio/transcriptions"))
    assert json.loads(llm_request.content)["model"] == "gpt-4o-mini"
    assert b"gpt-4o-mini-transcribe" in stt_request.content
