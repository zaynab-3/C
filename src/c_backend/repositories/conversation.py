"""Bounded conversation context from the application's existing Message rows."""

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from c_backend.conversation import ConversationEntry
from c_backend.models import Message


async def load_recent_conversation(
    session: AsyncSession,
    current: Message,
    *,
    limit: int,
) -> list[ConversationEntry]:
    if not 0 <= limit <= 50:
        raise ValueError("Conversation history limit must be between 0 and 50")
    if limit == 0:
        return []

    result = await session.execute(
        select(
            Message.content_type,
            Message.content,
            Message.transcript,
            Message.generated_reply,
            Message.processed_at,
        )
        .where(
            Message.channel == current.channel,
            Message.sender_id == current.sender_id,
            Message.id != current.id,
            tuple_(Message.received_at, Message.created_at, Message.id)
            < (current.received_at, current.created_at, current.id),
        )
        .order_by(
            Message.received_at.desc(), Message.created_at.desc(), Message.id.desc(),
        )
        .limit(limit)
    )

    history: list[ConversationEntry] = []
    for row in reversed(result.all()):
        if row.content_type == "text":
            user_text = row.content
        elif row.content_type == "audio":
            user_text = row.transcript
        else:
            continue
        if user_text and user_text.strip():
            history.append(ConversationEntry(role="user", content=user_text))
        if (
            row.generated_reply
            and row.generated_reply.strip()
            and row.processed_at is not None
        ):
            history.append(
                ConversationEntry(role="assistant", content=row.generated_reply)
            )
    return history
