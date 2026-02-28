# Repository Guidelines

Codex 所有回复必须使用中文。

## Project Structure & Module Organization
This repository is a FastAPI service for BililiveRecorder webhooks, transcription tasks, and settlement processing. `main.py` is the app entrypoint and registers routers from `api/routers/`. Database setup lives in `database.py`, with SQLAlchemy models in `models/`, CRUD helpers in `crud/`, request/response schemas in `schemas/`, and integration/business logic in `services/`. HTML views are in `templates/`. Put persistent local data under `data/`. Add tests in `tests/` using the existing `test_*.py` pattern.

## Build, Test, and Development Commands
Install dependencies with `pip install -r requirements.txt`.
Run locally with `python main.py` or `uvicorn main:app --reload --host 0.0.0.0 --port 18000`.
Run tests with `pytest`.
Start the containerized app with `docker compose up --build -d`.
The compose file expects `.env` and mounts `./data/transcription_tasks.db` into the container.

## Coding Style & Naming Conventions
Follow Python conventions: 4-space indentation, `snake_case` for modules/functions/variables, and `PascalCase` for classes, enums, and SQLAlchemy models. Keep type hints where practical; the codebase already uses them in config, services, and tests. Route modules belong in `api/routers/` and should stay thin: request parsing in routers, data access in `crud/`, and side effects or vendor integrations in `services/`. No formatter or linter config is committed, so keep imports tidy and follow PEP 8 manually.

## Testing Guidelines
Tests use `pytest`. Name new files `tests/test_<feature>.py` and test functions `test_<behavior>()`. Prefer isolated tests with in-memory SQLite for database logic, as shown in `tests/test_task_api.py`. Add or update tests whenever changing router behavior, sorting rules, database models, or settlement import or summary logic.

## Commit & Pull Request Guidelines
Recent history mixes concise Chinese summaries with Conventional Commit-style prefixes such as `feat(ui):` and `style(tasks):`. Use a short imperative subject, optionally with a scope, for example: `feat(settlement): add CSV validation`. Keep commits focused. In pull requests, describe the behavior change, note any new environment variables or schema changes, link the related issue, and include screenshots when updating `templates/` pages.

## Security & Configuration Tips
Do not commit real secrets in `.env`. `config.py` reads `SERVERCHAN_SEND_KEY`, Tencent Cloud credentials, `TUSHARE_TOKEN`, `VIDEO_DIRECTORY`, and `FFMPEG_PATH`; document any new settings in the PR. Treat files in `data/` as runtime artifacts, not source.

