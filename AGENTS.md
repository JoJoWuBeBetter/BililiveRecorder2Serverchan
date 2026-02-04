# Repository Guidelines

## Project Structure & Module Organization
- `main.py` starts the FastAPI app and registers routers.
- `api/routers/` contains HTTP endpoints (webhook, COS, tasks, file browser).
- `services/` implements integrations (ServerChan, Tencent Cloud ASR/COS, ffmpeg).
- `crud/`, `models/`, and `schemas/` define persistence logic and Pydantic/SQLAlchemy models.
- `templates/` hosts HTML pages for the task console UI.
- `tests/` contains pytest tests (currently `test_task_api.py`).
- `database.py` configures SQLite storage at `data/transcription_tasks.db`.

## Build, Test, and Development Commands
- `python -m venv .venv` then `pip install -r requirements.txt` to set up dependencies.
- `python main.py` runs the app locally on port `18000` (see `main.py`).
- `uvicorn main:app --reload --host 0.0.0.0 --port 18000` for hot-reload during development.
- `pytest` runs the test suite.
- `docker compose up --build` builds and runs the container (exposes `18888` -> `8000`).

## Coding Style & Naming Conventions
- Use 4-space indentation and standard Python formatting (PEP 8 style).
- Modules use `snake_case.py`; classes use `UpperCamelCase`; functions and variables use `snake_case`.
- FastAPI routes live in `api/routers/*_api.py` and services in `services/*_service.py`.
- No formatter or linter is enforced in this repo; keep changes consistent with surrounding code.

## Testing Guidelines
- Framework: `pytest`.
- Name tests `test_*.py` and test functions `test_*`.
- Favor fast, isolated tests (see `tests/test_task_api.py` using in-memory SQLite).

## Commit & Pull Request Guidelines
- Use Conventional Commits with a scope when helpful, e.g. `feat(ui): add task console link` or `style(tasks): refresh layout`.
- PRs should include a clear summary, testing notes (`pytest`, manual checks), and screenshots for template/UI changes.
- Link related issues when applicable.

## Configuration & Secrets
- Required env vars include `SERVERCHAN_SEND_KEY` and Tencent Cloud credentials in `.env` or the environment.
- Do not commit `.env`, database `.db` files, or recorded media; they are gitignored.

## Agent-Specific Instructions
- Codex 回复使用中文；代码内注释和日志统一使用中文。

## Architecture Overview
- Webhooks from BililiveRecorder are accepted by FastAPI routes, stored in SQLite, and handed off to services for notification and transcription.
- The task console UI renders from `templates/` and calls JSON endpoints in `api/routers/` for updates.
