"""add inbound media and transcription fields

Revision ID: 150a3b507d28
Revises: cba3814f9172
Create Date: 2026-09-05 20:18:28.011202

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '150a3b507d28'
down_revision: Union[str, Sequence[str], None] = 'cba3814f9172'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("messages", sa.Column("media_id", sa.String(255), nullable=True))
    op.add_column("messages", sa.Column("media_mime_type", sa.String(255), nullable=True))
    op.add_column("messages", sa.Column("media_sha256", sa.String(255), nullable=True))
    op.add_column("messages", sa.Column("media_filename", sa.String(512), nullable=True))
    op.add_column("messages", sa.Column("media_is_voice", sa.Boolean, nullable=True))
    op.add_column("messages", sa.Column("transcript", sa.Text, nullable=True))
    op.add_column("messages", sa.Column("transcription_provider", sa.String(50), nullable=True))
    op.add_column("messages", sa.Column("transcription_model", sa.String(255), nullable=True))
    op.add_column("messages", sa.Column("transcribed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("messages", "transcribed_at")
    op.drop_column("messages", "transcription_model")
    op.drop_column("messages", "transcription_provider")
    op.drop_column("messages", "transcript")
    op.drop_column("messages", "media_is_voice")
    op.drop_column("messages", "media_filename")
    op.drop_column("messages", "media_sha256")
    op.drop_column("messages", "media_mime_type")
    op.drop_column("messages", "media_id")
