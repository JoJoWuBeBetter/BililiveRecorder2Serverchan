# crud/task_crud.py
import uuid

from sqlalchemy.orm import Session

from models.task import TranscriptionTask
from schemas.task import TaskCreate


def get_task(db: Session, task_id: uuid.UUID):
    return db.get(TranscriptionTask, task_id)


def create_task(db: Session, task_data: TaskCreate) -> TranscriptionTask:
    db_task = TranscriptionTask(
        original_audio_path=task_data.local_audio_path,
        batch_id=task_data.batch_id
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def update_task(db: Session, task_id: uuid.UUID, updates: dict):
    # 直接使用get获取对象，然后更新属性
    task = db.get(TranscriptionTask, task_id)
    if task:
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)
        db.commit()
        db.refresh(task)
        return task
    return None


def get_tasks_by_batch_id(db: Session, batch_id: uuid.UUID):
    return db.query(TranscriptionTask).filter_by(batch_id=batch_id).all()
