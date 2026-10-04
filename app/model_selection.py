"""Choose only known API models that satisfy this workflow's contracts."""
import asyncio

from pydantic import Field

from app.domain import ExternalModel, StrictModel
from app.http import ExternalFailure

LLM_MODELS = ("gpt-5-mini", "gpt-4o-mini")
STT_MODELS = ("gpt-4o-mini-transcribe", "gpt-4o-transcribe")


class AvailableModel(ExternalModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")


class ModelCatalog(StrictModel):
    ids: frozenset[str]


class OpenAIModelSelector:
    def __init__(self, sdk_client: object):
        self.client = sdk_client
        self._catalog: ModelCatalog | None = None
        self._lock = asyncio.Lock()

    async def _available(self) -> ModelCatalog:
        if self._catalog is not None:
            return self._catalog
        async with self._lock:
            if self._catalog is not None:
                return self._catalog
            try:
                ids = set()
                supported = set(LLM_MODELS + STT_MODELS)
                async for item in self.client.models.list():
                    if getattr(item, "id", None) in supported:
                        model = AvailableModel.model_validate(item.model_dump())
                        ids.add(model.id)
                catalog = ModelCatalog(ids=frozenset(ids))
            except Exception:
                # SDK errors may contain credentials or provider payloads.
                raise ExternalFailure("model_discovery_failed") from None
            self._catalog = catalog
            return catalog

    async def llm(self) -> str:
        available = (await self._available()).ids
        for model in LLM_MODELS:
            if model in available:
                return model
        raise ExternalFailure("llm_model_unavailable")

    async def stt(self) -> str:
        available = (await self._available()).ids
        for model in STT_MODELS:
            if model in available:
                return model
        raise ExternalFailure("stt_model_unavailable")
