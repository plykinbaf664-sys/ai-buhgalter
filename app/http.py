"""Bounded external I/O. No retries, redirects, raw payload logging or wire logs."""
import asyncio
import logging

import httpx


class ExternalFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def disable_wire_logs() -> None:
    for name in ("httpx", "httpcore", "httpx2", "httpcore2"):
        logging.getLogger(name).setLevel(logging.CRITICAL + 1)
        logging.getLogger(name).disabled = True
        for child in tuple(logging.Logger.manager.loggerDict):
            if child.startswith(name + "."):
                logging.getLogger(child).disabled = True


async def bounded_request(client: httpx.AsyncClient, method: str, url: str, *,
                          limit: int = 65_536, deadline: float = 20, **kwargs) -> bytes:
    async def read():
        async with client.stream(method, url, **kwargs) as response:
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                if len(content) + len(chunk) > limit:
                    raise ExternalFailure("response_too_large")
                content.extend(chunk)
            return bytes(content)
    try:
        return await asyncio.wait_for(read(), timeout=deadline)
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise ExternalFailure("timeout") from None
    except httpx.HTTPStatusError as exc:
        raise ExternalFailure(f"http_{exc.response.status_code}") from None
    except httpx.HTTPError:
        raise ExternalFailure("http_error") from None
