import asyncio
import os
import sys
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.routers import task_api
from database import Base
from models.task import TranscriptionTask, TaskStatus


def test_batch_results_sorted_by_original_audio_path():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    batch_id = uuid.uuid4()

    db = TestingSessionLocal()

    # Insert tasks in reverse order to ensure sorting is applied by the API
    task_b = TranscriptionTask(
        id=uuid.uuid4(),
        batch_id=batch_id,
        original_audio_path="/audio/b.wav",
        status=TaskStatus.COMPLETED,
        transcription_result="result for b",
    )
    task_a = TranscriptionTask(
        id=uuid.uuid4(),
        batch_id=batch_id,
        original_audio_path="/audio/a.wav",
        status=TaskStatus.COMPLETED,
        transcription_result="result for a",
    )
    db.add_all([task_b, task_a])
    db.commit()

    try:
        result = asyncio.run(
            task_api.get_batch_transcription_results(batch_id=batch_id, db=db)
        )
    finally:
        db.close()

    assert result.status == TaskStatus.COMPLETED
    assert result.results == ["result for a", "result for b"]
    assert result.completed_count == 2
    assert result.total_count == 2
