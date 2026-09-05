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
