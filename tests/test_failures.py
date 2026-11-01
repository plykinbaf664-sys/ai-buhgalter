import asyncio
import json
import secrets

import httpx
import pytest
from pydantic import SecretStr

from app.ai import CommandInterpreter
from app.domain import UserProblem
from app.http import ExternalFailure, bounded_request
from app.validation import validate_json
from app.telegram_models import Update

NATURAL = "Выстави счёт ООО Ромашка за сентябрь 2026"


@pytest.mark.parametrize("body", [
    b'{"update_id":1,"update_id":2}', b'{"update_id":NaN}',
])
def test_ambiguous_json_rejected(body):
    with pytest.raises(ValueError):
        validate_json(Update, body)


def test_stream_limit_without_content_length():
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(10):
                yield b"x" * 20

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=Stream()),
        )) as client:
            with pytest.raises(ExternalFailure, match="response_too_large"):
                await bounded_request(client, "GET", "https://example.test", limit=30)
    asyncio.run(scenario())


def test_absolute_deadline_stops_trickling_response():
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x"
            await asyncio.sleep(10)
            yield b"y"

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=Stream()),
        )) as client:
            with pytest.raises(ExternalFailure, match="timeout"):
                await bounded_request(client, "GET", "https://example.test", deadline=0.01)
    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["refusal", "incomplete", "tool", "multiple", "json", "duplicate", "timeout", "oversize"])
def test_llm_envelope_failure_is_safe(case):
    content = {"type": "output_text", "text": json.dumps({
        "action": "create_invoice", "client": "ООО Ромашка", "year": 2026, "month": 9,
    })}
    body = {"status": "completed", "output": [{
        "type": "message", "status": "completed", "role": "assistant", "content": [content],
    }]}
    if case == "refusal":
        body["output"][0]["content"] = [{"type": "refusal", "refusal": "sensitive provider data"}]
    elif case == "incomplete":
        body["status"] = "incomplete"
    elif case == "tool":
        body["output"] = [{"type": "function_call", "name": "delete", "arguments": "{}"}]
    elif case == "multiple":
        body["output"].append(body["output"][0])
    elif case == "json":
        content["text"] = "{"
    elif case == "duplicate":
        content["text"] = content["text"].replace('"month": 9', '"month": 10, "month": 9')

    async def scenario():
        def respond(request):
            if case == "timeout":
                raise httpx.ReadTimeout("sensitive", request=request)
            if case == "oversize":
                return httpx.Response(200, content=b"x" * 65_537)
            return httpx.Response(200, json=body)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(UserProblem if case == "refusal" else ExternalFailure):
                await CommandInterpreter(client, SecretStr(secrets.token_urlsafe(32)), "test-model").interpret(NATURAL)
    asyncio.run(scenario())
