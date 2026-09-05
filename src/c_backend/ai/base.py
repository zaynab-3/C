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


@dataclass(frozen=True, slots=True)
class AITranscription:
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

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str,
    ) -> AITranscription:
        raise AIProviderError(
            f"Audio transcription is not supported by {self.name}"
        )
