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
