$ErrorActionPreference = 'Stop'

if (-not (Test-Path '.\pyproject.toml')) {
    throw 'Run this script from C:\Users\Zainab\Projects\c-backend'
}

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feat/ai-provider-abstraction') {
    throw "Expected branch feat/ai-provider-abstraction, found: $branch"
}

New-Item -ItemType Directory -Force 'src\c_backend\ai' | Out-Null

@'
from abc import ABC, abstractmethod
from dataclasses import dataclass


class AIProviderError(RuntimeError):
    """Base error for AI provider failures."""


class AIProviderConfigurationError(AIProviderError):
    """Raised when a provider is selected without valid configuration."""


@dataclass(frozen=True, slots=True)
class AIResponse:
    text: str
    provider: str
    model: str


class AIProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> AIResponse:
        """Generate a text response using the active provider."""
'@ | Set-Content -Encoding UTF8 'src\c_backend\ai\base.py'

@'
from google import genai
from google.genai import types

from c_backend.ai.base import (
    AIProvider,
    AIProviderConfigurationError,
    AIProviderError,
    AIResponse,
)


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, *, api_key: str | None, model: str) -> None:
        if not api_key or not api_key.strip():
            raise AIProviderConfigurationError(
                "GEMINI_API_KEY is required when AI_PROVIDER=gemini"
            )
        if not model.strip():
            raise AIProviderConfigurationError(
                "GEMINI_MODEL must not be empty"
            )

        self.model = model.strip()
        self._client = genai.Client(api_key=api_key.strip())

    async def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> AIResponse:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise AIProviderError("Prompt must not be empty")

        config = None
        if system_prompt and system_prompt.strip():
            config = types.GenerateContentConfig(
                system_instruction=system_prompt.strip()
            )

        try:
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=clean_prompt,
                config=config,
            )
        except Exception as exc:
            raise AIProviderError(
                f"Gemini request failed: {exc}"
            ) from exc

        text = (response.text or "").strip()
        if not text:
            raise AIProviderError("Gemini returned no text")

        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
        )
'@ | Set-Content -Encoding UTF8 'src\c_backend\ai\gemini_provider.py'

@'
from openai import AsyncOpenAI

from c_backend.ai.base import (
    AIProvider,
    AIProviderConfigurationError,
    AIProviderError,
    AIResponse,
)


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise AIProviderConfigurationError(
                "OPENAI_API_KEY is required when AI_PROVIDER=openai"
            )
        if not model or not model.strip():
            raise AIProviderConfigurationError(
                "OPENAI_MODEL is required when AI_PROVIDER=openai"
            )

        self.model = model.strip()
        self._client = AsyncOpenAI(api_key=api_key.strip())

    async def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> AIResponse:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise AIProviderError("Prompt must not be empty")

        request: dict[str, str] = {
            "model": self.model,
            "input": clean_prompt,
        }
        if system_prompt and system_prompt.strip():
            request["instructions"] = system_prompt.strip()

        try:
            response = await self._client.responses.create(**request)
        except Exception as exc:
            raise AIProviderError(
                f"OpenAI request failed: {exc}"
            ) from exc

        text = (response.output_text or "").strip()
        if not text:
            raise AIProviderError("OpenAI returned no text")

        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
        )
'@ | Set-Content -Encoding UTF8 'src\c_backend\ai\openai_provider.py'

@'
from c_backend.ai.base import (
    AIProvider,
    AIProviderConfigurationError,
)
from c_backend.ai.gemini_provider import GeminiProvider
from c_backend.ai.openai_provider import OpenAIProvider
from c_backend.config import Settings, get_settings


def get_ai_provider(
    settings: Settings | None = None,
) -> AIProvider:
    current = settings or get_settings()

    if current.ai_provider == "gemini":
        return GeminiProvider(
            api_key=current.gemini_api_key,
            model=current.gemini_model,
        )

    if current.ai_provider == "openai":
        return OpenAIProvider(
            api_key=current.openai_api_key,
            model=current.openai_model,
        )

    raise AIProviderConfigurationError(
        f"Unsupported AI provider: {current.ai_provider}"
    )
'@ | Set-Content -Encoding UTF8 'src\c_backend\ai\factory.py'

@'
from c_backend.ai.base import (
    AIProvider,
    AIProviderConfigurationError,
    AIProviderError,
    AIResponse,
)
from c_backend.ai.factory import get_ai_provider

__all__ = [
    "AIProvider",
    "AIProviderConfigurationError",
    "AIProviderError",
    "AIResponse",
    "get_ai_provider",
]
'@ | Set-Content -Encoding UTF8 'src\c_backend\ai\__init__.py'

@'
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_db: str = Field(validation_alias="POSTGRES_DB")
    postgres_user: str = Field(validation_alias="POSTGRES_USER")
    postgres_password: str = Field(validation_alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(validation_alias="POSTGRES_PORT")

    celery_broker_url: str = Field(
        validation_alias="CELERY_BROKER_URL"
    )

    whatsapp_verify_token: str | None = Field(
        default=None,
        validation_alias="WHATSAPP_VERIFY_TOKEN",
    )

    whatsapp_app_secret: str | None = Field(
        default=None,
        validation_alias="WHATSAPP_APP_SECRET",
    )

    whatsapp_allowed_senders_raw: str = Field(
        default="",
        validation_alias="WHATSAPP_ALLOWED_SENDERS",
    )

    whatsapp_access_token: str | None = Field(
        default=None,
        validation_alias="WHATSAPP_ACCESS_TOKEN",
    )

    whatsapp_phone_number_id: str | None = Field(
        default=None,
        validation_alias="WHATSAPP_PHONE_NUMBER_ID",
    )

    ai_provider: Literal["gemini", "openai"] = Field(
        default="gemini",
        validation_alias="AI_PROVIDER",
    )

    gemini_api_key: str | None = Field(
        default=None,
        validation_alias="GEMINI_API_KEY",
    )

    gemini_model: str = Field(
        default="gemini-3.8-flash",
        validation_alias="GEMINI_MODEL",
    )

    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )

    openai_model: str | None = Field(
        default=None,
        validation_alias="OPENAI_MODEL",
    )

    @property
    def whatsapp_allowed_senders(self) -> set[str]:
        return {
            sender.strip()
            for sender in self.whatsapp_allowed_senders_raw.split(",")
            if sender.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
'@ | Set-Content -Encoding UTF8 'src\c_backend\config.py'

@'
POSTGRES_DB=c
POSTGRES_USER=c_user
POSTGRES_PASSWORD=change-me
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432

CELERY_BROKER_URL=redis://127.0.0.1:6379/0

WHATSAPP_VERIFY_TOKEN=change-me
WHATSAPP_APP_SECRET=change-me
WHATSAPP_ALLOWED_SENDERS=96170123456
WHATSAPP_ACCESS_TOKEN=change-me
WHATSAPP_PHONE_NUMBER_ID=change-me

# AI provider selection
# Development/free testing: Gemini
# Production later: OpenAI
AI_PROVIDER=gemini
GEMINI_API_KEY=change-me
GEMINI_MODEL=gemini-3.8-flash
OPENAI_API_KEY=change-me
OPENAI_MODEL=change-me
'@ | Set-Content -Encoding UTF8 '.env.example'

@'
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from c_backend.ai.base import (
    AIProviderConfigurationError,
    AIProviderError,
    AIResponse,
)
from c_backend.ai import factory as factory_module
from c_backend.ai import gemini_provider as gemini_module
from c_backend.ai import openai_provider as openai_module


def _settings(provider: str) -> SimpleNamespace:
    return SimpleNamespace(
        ai_provider=provider,
        gemini_api_key="gemini-test-key",
        gemini_model="gemini-test-model",
        openai_api_key="openai-test-key",
        openai_model="openai-test-model",
    )


def test_factory_selects_gemini(monkeypatch):
    sentinel = object()
    constructor = Mock(return_value=sentinel)
    monkeypatch.setattr(
        factory_module,
        "GeminiProvider",
        constructor,
    )

    result = factory_module.get_ai_provider(_settings("gemini"))

    assert result is sentinel
    constructor.assert_called_once_with(
        api_key="gemini-test-key",
        model="gemini-test-model",
    )


def test_factory_selects_openai(monkeypatch):
    sentinel = object()
    constructor = Mock(return_value=sentinel)
    monkeypatch.setattr(
        factory_module,
        "OpenAIProvider",
        constructor,
    )

    result = factory_module.get_ai_provider(_settings("openai"))

    assert result is sentinel
    constructor.assert_called_once_with(
        api_key="openai-test-key",
        model="openai-test-model",
    )


def test_factory_rejects_unknown_provider():
    with pytest.raises(
        AIProviderConfigurationError,
        match="Unsupported AI provider",
    ):
        factory_module.get_ai_provider(_settings("unknown"))


@pytest.mark.anyio
async def test_gemini_provider_generates_text(monkeypatch):
    generate_content = AsyncMock(
        return_value=SimpleNamespace(text="Gemini answer")
    )
    fake_client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(
                generate_content=generate_content
            )
        )
    )
    client_constructor = Mock(return_value=fake_client)
    monkeypatch.setattr(
        gemini_module.genai,
        "Client",
        client_constructor,
    )

    provider = gemini_module.GeminiProvider(
        api_key="secret-test-key",
        model="gemini-test-model",
    )
    result = await provider.generate_text(
        "Hello",
        system_prompt="You are C.",
    )

    assert result == AIResponse(
        text="Gemini answer",
        provider="gemini",
        model="gemini-test-model",
    )
    call = generate_content.await_args.kwargs
    assert call["model"] == "gemini-test-model"
    assert call["contents"] == "Hello"
    assert call["config"] is not None


@pytest.mark.anyio
async def test_openai_provider_generates_text(monkeypatch):
    create = AsyncMock(
        return_value=SimpleNamespace(output_text="OpenAI answer")
    )
    fake_client = SimpleNamespace(
        responses=SimpleNamespace(create=create)
    )
    client_constructor = Mock(return_value=fake_client)
    monkeypatch.setattr(
        openai_module,
        "AsyncOpenAI",
        client_constructor,
    )

    provider = openai_module.OpenAIProvider(
        api_key="secret-test-key",
        model="openai-test-model",
    )
    result = await provider.generate_text(
        "Hello",
        system_prompt="You are C.",
    )

    assert result == AIResponse(
        text="OpenAI answer",
        provider="openai",
        model="openai-test-model",
    )
    create.assert_awaited_once_with(
        model="openai-test-model",
        input="Hello",
        instructions="You are C.",
    )


def test_gemini_provider_requires_key():
    with pytest.raises(
        AIProviderConfigurationError,
        match="GEMINI_API_KEY",
    ):
        gemini_module.GeminiProvider(
            api_key=None,
            model="gemini-test-model",
        )


def test_openai_provider_requires_model():
    with pytest.raises(
        AIProviderConfigurationError,
        match="OPENAI_MODEL",
    ):
        openai_module.OpenAIProvider(
            api_key="openai-test-key",
            model=None,
        )


@pytest.mark.anyio
async def test_provider_rejects_empty_prompt(monkeypatch):
    fake_client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock())
    )
    monkeypatch.setattr(
        openai_module,
        "AsyncOpenAI",
        Mock(return_value=fake_client),
    )

    provider = openai_module.OpenAIProvider(
        api_key="openai-test-key",
        model="openai-test-model",
    )

    with pytest.raises(AIProviderError, match="Prompt must not be empty"):
        await provider.generate_text("   ")
'@ | Set-Content -Encoding UTF8 'tests\test_ai_providers.py'

$syncPath = 'C_PROJECT_SYNC.md'
if (Test-Path $syncPath) {
    $sync = Get-Content $syncPath -Raw
    $sync = $sync.Replace(
        'Current branch: feat/gateway-hardening',
        'Current branch: feat/ai-provider-abstraction'
    )

    if ($sync -notmatch 'AI PROVIDER ABSTRACTION CHECKPOINT') {
        $sync += @'


AI PROVIDER ABSTRACTION CHECKPOINT

Branch: feat/ai-provider-abstraction

WHAT CHANGED

- Added one AIProvider contract shared by all model vendors.
- Added GeminiProvider for free development/testing.
- Added OpenAIProvider for later production use.
- Provider selection is configuration-driven with AI_PROVIDER.
- Gemini default development model is gemini-3.8-flash.
- OpenAI model remains configuration-only until production model selection.
- Added provider factory and provider-isolation tests.

ARCHITECTURE

C / future LangGraph
-> AIProvider
   -> GeminiProvider [development/free testing]
   -> OpenAIProvider [production later]

IMPORTANT

No OpenAI paid API call is required during development.
The webhook and worker must not depend on provider-specific SDK APIs.
Provider-specific code stays behind the AIProvider boundary.

NEXT

- Add a real GEMINI_API_KEY locally only; never commit it.
- Live-test Gemini through the provider abstraction.
- Then connect text message processing to the AI provider inside the worker/orchestration layer.
- LangGraph comes after the provider boundary is live-verified.
'@
    }

    Set-Content -Encoding UTF8 $syncPath $sync
}

Write-Host ''
Write-Host 'Running full test suite...'
uv run pytest -v
if ($LASTEXITCODE -ne 0) {
    throw 'Tests failed. Changes were NOT committed or pushed.'
}

Write-Host ''
Write-Host 'Tests passed. Committing and pushing provider abstraction...'
.\git-sync.ps1 'feat: add provider-agnostic AI interface'
if ($LASTEXITCODE -ne 0) {
    throw 'git-sync failed.'
}

Write-Host ''
Write-Host 'DONE: AI provider abstraction is implemented, tested, committed, and pushed.'
Write-Host 'Next step: add GEMINI_API_KEY locally and perform a live Gemini call.'
