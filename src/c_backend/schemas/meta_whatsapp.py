from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MetaText(BaseModel):
    model_config = ConfigDict(extra="ignore")

    body: str


class MetaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sender: str = Field(alias="from")
    id: str
    timestamp: str
    type: str
    text: MetaText | None = None


class MetaValue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    messaging_product: str
    messages: list[MetaMessage] | None = None


class MetaChange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: MetaValue
    field: str


class MetaEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    changes: list[MetaChange]


class MetaWhatsAppWebhook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    object: str
    entry: list[MetaEntry]


class MetaWebhookAck(BaseModel):
    status: Literal["accepted"]
    messages: int
    stored: int
    duplicates: int
    ignored: int
    queued: int
