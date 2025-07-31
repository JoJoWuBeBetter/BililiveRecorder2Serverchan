# database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 使用 SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/transcription_tasks.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # connect_args 是 SQLite 特有的，用于允许多线程访问
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def create_db_and_tables():
    """在应用启动时创建数据库表"""
    Base.metadata.create_all(bind=engine)
