from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MockWhatsAppTextEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(pattern=r"^\d{6,20}$")
    type: Literal["text"]
    text: str = Field(min_length=1, max_length=4096)
    timestamp: datetime


class NormalizedMessage(BaseModel):
    external_id: str
    channel: Literal["whatsapp"]
    sender_id: str
    content_type: Literal["text"]
    content: str
    received_at: datetime
