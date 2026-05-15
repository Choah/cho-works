# Cho Works

Cho Works is a local-first work journal and KPI report assistant. It records daily work notes, creates Jira-like project cards, summarizes work by day/week/month/quarter/year/project, and runs as a small FastAPI web app backed by SQLite.

The app is designed for one person first. Your work data stays in a local SQLite file unless you explicitly deploy or copy that file somewhere else.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Easiest Use

Install the public GitHub version as a uv tool:

```bash
uv tool install git+https://github.com/Choah/cho-works
cho init
cho-web
```

Open:

```text
http://127.0.0.1:8787/
```

`cho init` creates the SQLite database if it does not exist. `cho-web` also initializes the database automatically on startup, so the web app works even if you skip `cho init`.

## Run From Source

```bash
git clone https://github.com/Choah/cho-works.git
cd cho-works
uv sync
cp .env.example .env
uv run cho init
uv run cho web
```

For another device on the same network:

```bash
uv run cho web --host 0.0.0.0 --port 8787
```

Then open `http://<server-ip>:8787/` from the other device.

## Daily Workflow

Add a work log from the CLI:

```bash
uv run cho add "API 프로젝트 오류 3건 수정 완료. 배포 일정표 정리." --project API
```

Use the web app for the normal workflow:

- Today: write daily work notes
- Projects: manage project cards
- Board: edit task status and completion dates
- Reports: day/week/month/quarter/year/project summaries
- Prompts: tune the report prompts from the browser
- Reminders: local reminder settings

## Data Location

Default database:

```text
~/.cho-works/cho_works.sqlite3
```

Cho Works automatically reads `.env` from the current working directory before it creates or opens the database. Start from the template:

```bash
cp .env.example .env
```

Use a custom path in `.env`:

```dotenv
CHO_WORKS_DB_PATH=/path/to/cho_works.sqlite3
```

Then run:

```bash
uv run cho init
uv run cho web
```

If you need the settings file somewhere else, set `CHO_WORKS_ENV_FILE=/path/to/.env` before running Cho Works.

The built-in `.env` reader intentionally supports simple settings only:

- `KEY=value`
- optional `export KEY=value`
- quoted single-line values
- no multiline values or advanced shell expansion
- existing shell environment variables take precedence over `.env`

The parent folder is created automatically. If the SQLite file is missing, Cho Works creates it on first CLI/web use.

Back up your data:

```bash
cp ~/.cho-works/cho_works.sqlite3 ./cho_works.backup.sqlite3
```

## Reports

Reports use one consistent structure:

- 핵심 요약
- 한 작업
- 성과
- 성과 근거
- 프로젝트 진행
- 결정
- 리스크와 이슈/블로커
- 다음 액션

The local summarizer is deterministic and source-grounded. A completed task is kept as work done; broader achievements are synthesized only when the source logs support them.

## Optional LLM Summaries

Cho Works works without an API key. To opt in to OpenAI structured summaries:

```bash
uv sync --extra llm
cp .env.example .env
# Edit .env:
# OPENAI_API_KEY=...
# CHO_WORKS_OPENAI_MODEL=gpt-4o-mini
uv run cho summary day
```

For uv tool installs, include the extra:

```bash
uv tool install "git+https://github.com/Choah/cho-works[llm]"
```

If the API key is missing, the API fails, or the model returns invalid evidence ids, Cho Works falls back to local deterministic reports.

When `OPENAI_API_KEY` is set, newly added daily records also use the LLM path for the `정리된 업무` text shown in the dashboard, entries, and project detail pages. To recalculate existing records after enabling LLM mode:

```bash
uv run cho refresh
```

## Deployment Notes

Simple local server:

```bash
uv run cho web --host 127.0.0.1 --port 8787
```

LAN server:

```bash
uv run cho web --host 0.0.0.0 --port 8787
```

Production-like process managers can run the same command. Keep the SQLite file on a persistent disk and set `CHO_WORKS_DB_PATH` explicitly.

Example:

```bash
export CHO_WORKS_DB_PATH="/srv/cho-works/cho_works.sqlite3"
uv run cho web --host 0.0.0.0 --port 8787
```

## Development

```bash
uv sync --dev
uv run pytest -q
uv build --wheel
```

The wheel includes the Jinja templates and parrot image assets used by the web app.

## Public Repo Hygiene

The repository does not include local SQLite data, `.cho-works/`, virtual environments, caches, or API keys. Runtime data is ignored by `.gitignore`.
