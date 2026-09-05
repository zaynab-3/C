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

        config = types.GenerateContentConfig(
            automatic_function_calling=(
                types.AutomaticFunctionCallingConfig(
                    disable=True,
                )
            ),
            system_instruction=(
                system_prompt.strip()
                if system_prompt and system_prompt.strip()
                else None
            ),
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
