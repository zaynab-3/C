import importlib.util
from pathlib import Path
from unittest.mock import Mock

from sqlalchemy.dialects import postgresql

from c_backend.models import Message


def test_existing_audio_migration_matches_model_and_downgrades_exactly(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "migrations/versions/150a3b507d28_add_inbound_media_and_transcription_.py"
    spec = importlib.util.spec_from_file_location("audio_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "cba3814f9172"
    operations = Mock()
    monkeypatch.setattr(migration, "op", operations)
    migration.upgrade()
    columns = [call.args[1] for call in operations.add_column.call_args_list]
    expected = {
        "media_id", "media_mime_type", "media_sha256", "media_filename", "media_is_voice",
        "transcript", "transcription_provider", "transcription_model", "transcribed_at",
    }
    assert {column.name for column in columns} == expected
    assert all(call.args[0] == "messages" for call in operations.add_column.call_args_list)
    for column in columns:
        model_column = Message.__table__.columns[column.name]
        assert column.nullable and model_column.nullable
        assert str(column.type.compile(dialect=postgresql.dialect())) == str(model_column.type.compile(dialect=postgresql.dialect()))
    migration.downgrade()
    assert [call.args for call in operations.drop_column.call_args_list] == [
        ("messages", column.name) for column in reversed(columns)
    ]
