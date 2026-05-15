# Cho Works Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first CLI and web app that captures daily work logs and summarizes them by day, week, month, quarter, year, and project.

**Architecture:** Use one shared Python service layer backed by SQLite. CLI commands and FastAPI routes call the same entry, summary, reminder, and pet services so behavior stays consistent.

**Tech Stack:** Python 3.12, SQLite, Typer, FastAPI, Jinja2, pytest, uv.

---

## File Structure

- Create: `pyproject.toml` for package metadata, dependencies, and pytest config.
- Create: `README.md` with local usage.
- Create: `.gitignore` for Python, local databases, and cache files.
- Create: `src/cho_works/config.py` for default timezone and database path resolution.
- Create: `src/cho_works/db.py` for SQLite connection and schema setup.
- Create: `src/cho_works/models.py` for dataclasses shared by services.
- Create: `src/cho_works/periods.py` for day, week, month, quarter, year date ranges.
- Create: `src/cho_works/parsing.py` for rule-based Korean-friendly extraction.
- Create: `src/cho_works/services.py` for entries, search, summaries, reminders, and pet updates.
- Create: `src/cho_works/notifications.py` for best-effort OS notification delivery.
- Create: `src/cho_works/cli.py` for Typer commands.
- Create: `src/cho_works/web.py` for FastAPI routes.
- Create: `src/cho_works/templates/*.html` for the local web UI.
- Create: `tests/` files for parser, periods, services, CLI, and web.

## Task 1: Project Skeleton And Database

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/cho_works/__init__.py`
- Create: `src/cho_works/config.py`
- Create: `src/cho_works/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing database test**

```python
def test_init_db_creates_core_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "cho.sqlite3"
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(db_path))

    from cho_works.db import connect, init_db

    init_db()
    with connect() as conn:
        names = {
            row["name"]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        }

    assert {
        "entries",
        "entry_items",
        "kpi_observations",
        "summaries",
        "reminder_configs",
        "reminder_events",
        "pet_state",
    }.issubset(names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -q`
Expected: fail because the package and database module do not exist.

- [ ] **Step 3: Implement skeleton and schema**

Create package metadata, config path helpers, SQLite connection helpers, and idempotent `init_db()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -q`
Expected: pass.

## Task 2: Parsing And Period Logic

**Files:**
- Create: `src/cho_works/models.py`
- Create: `src/cho_works/periods.py`
- Create: `src/cho_works/parsing.py`
- Test: `tests/test_periods.py`
- Test: `tests/test_parsing.py`

- [ ] **Step 1: Write failing period tests**

```python
from datetime import date
from cho_works.periods import period_range


def test_period_range_returns_quarter_bounds():
    assert period_range("quarter", date(2026, 5, 8)) == (
        date(2026, 4, 1),
        date(2026, 6, 30),
    )
```

- [ ] **Step 2: Write failing parser tests**

```python
from cho_works.parsing import parse_entry_text


def test_parse_entry_extracts_korean_work_items_and_kpis():
    parsed = parse_entry_text(
        "A 프로젝트 API 오류 3건 수정 완료. B 회의에서 배포 일정 결정. #backend"
    )

    assert parsed.items[0].item_type == "outcome"
    assert parsed.items[0].project == "A"
    assert parsed.items[1].item_type == "decision"
    assert parsed.kpis[0].value == 3
    assert parsed.kpis[0].unit == "건"
    assert "backend" in parsed.tags
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_periods.py tests/test_parsing.py -q`
Expected: fail because modules and functions are incomplete.

- [ ] **Step 4: Implement models, period ranges, and parsing**

Implement dataclasses for parsed items and KPI observations. Implement date ranges for `day`, `week`, `month`, `quarter`, and `year`. Implement lightweight sentence splitting, tag extraction, project extraction, item classification, and numeric KPI extraction.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_periods.py tests/test_parsing.py -q`
Expected: pass.

## Task 3: Entry, Search, And Summary Services

**Files:**
- Create: `src/cho_works/services.py`
- Test: `tests/test_services.py`

- [ ] **Step 1: Write failing service tests**

```python
from cho_works.services import EntryService, SummaryService


def test_entry_service_persists_entry_items_and_project_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    summaries = SummaryService()

    created = entries.add_entry(
        "2026-05-08",
        "A 프로젝트 배포 자동화 2건 개선 완료. 인증 이슈 해결.",
        project="A",
        source="test",
    )

    assert created.id > 0
    assert entries.search("자동화")[0].id == created.id

    summary = summaries.generate("project", "A")
    assert "A" in summary.title
    assert "배포 자동화" in summary.body
    assert summary.source_entry_ids == [created.id]
```

- [ ] **Step 2: Run service test to verify it fails**

Run: `uv run pytest tests/test_services.py -q`
Expected: fail because services do not exist.

- [ ] **Step 3: Implement services**

Implement entry persistence, extracted item persistence, KPI persistence, substring search, period summary generation, and project summary generation.

- [ ] **Step 4: Run service tests**

Run: `uv run pytest tests/test_services.py -q`
Expected: pass.

## Task 4: Reminders, Notifications, And Pet State

**Files:**
- Create: `src/cho_works/notifications.py`
- Modify: `src/cho_works/services.py`
- Test: `tests/test_reminders_pet.py`

- [ ] **Step 1: Write failing reminder and pet tests**

```python
from cho_works.services import EntryService, PetService, ReminderService


def test_pet_rewards_logging_consistency(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    pet = PetService()

    entries.add_entry("2026-05-07", "정산 자동화 완료", source="test")
    entries.add_entry("2026-05-08", "장애 원인 분석 완료", source="test")

    state = pet.refresh(today="2026-05-08")

    assert state.streak_days == 2
    assert state.care_points >= 20
    assert state.mood in {"calm", "happy", "focused"}


def test_due_reminders_respect_enabled_configs(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    reminders = ReminderService()
    reminders.set_config("end_of_day", "18:00", enabled=True)

    due = reminders.due("2026-05-08T18:05:00")

    assert due[0].reminder_type == "end_of_day"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reminders_pet.py -q`
Expected: fail because reminder and pet services are missing.

- [ ] **Step 3: Implement reminder and pet services**

Implement reminder configs, due detection, event recording, pet streak calculation, care points, mood, and Korean message generation. Implement OS notification best-effort adapter with non-fatal failures.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_reminders_pet.py -q`
Expected: pass.

## Task 5: CLI And Web App

**Files:**
- Create: `src/cho_works/cli.py`
- Create: `src/cho_works/web.py`
- Create: `src/cho_works/templates/base.html`
- Create: `src/cho_works/templates/index.html`
- Create: `src/cho_works/templates/entries.html`
- Create: `src/cho_works/templates/summary.html`
- Test: `tests/test_cli.py`
- Test: `tests/test_web.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI tests**

```python
from typer.testing import CliRunner
from cho_works.cli import app


def test_cli_add_and_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    runner = CliRunner()

    add = runner.invoke(app, ["add", "A 프로젝트 문서 1건 정리 완료", "--date", "2026-05-08"])
    assert add.exit_code == 0

    summary = runner.invoke(app, ["summary", "day", "--date", "2026-05-08"])
    assert summary.exit_code == 0
    assert "2026-05-08" in summary.output
    assert "문서" in summary.output
```

- [ ] **Step 2: Write failing web tests**

```python
from fastapi.testclient import TestClient
from cho_works.web import create_app


def test_web_dashboard_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Cho Works" in response.text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py tests/test_web.py -q`
Expected: fail because CLI and web app are missing.

- [ ] **Step 4: Implement CLI and web routes**

Implement commands: `add`, `list`, `search`, `summary`, `projects`, `reminders`, `pet`, and `web`. Implement dashboard, entry creation, entry list, search, summary pages, reminder page, and pet status.

- [ ] **Step 5: Run full verification**

Run: `uv run pytest -q`
Expected: all tests pass.

Run: `uv run cho --help`
Expected: command list renders.

Run: `uv run cho-web --help`
Expected: web launcher help renders.

