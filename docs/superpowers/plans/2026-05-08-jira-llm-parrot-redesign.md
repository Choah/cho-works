# Jira LLM Parrot Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Jira-like projects/work items, standard structured reports, optional LLM summarization, and a visual parrot companion.

**Architecture:** Keep raw entries as source of truth. Add projects and work items above parsed entry items. Route summary generation through a canonical `WorkReport` schema with deterministic fallback and optional OpenAI provider.

**Tech Stack:** Python 3.12, SQLite, Typer, FastAPI, Jinja2, Pydantic, OpenAI Python SDK, pytest.

---

### Task 1: Standard Report Schema

**Files:**
- Create: `src/cho_works/report_schema.py`
- Create: `src/cho_works/report_context.py`
- Create: `src/cho_works/summarizers.py`
- Create: `src/cho_works/llm_client.py`
- Modify: `src/cho_works/services.py`
- Test: `tests/test_reports.py`

- [ ] Write failing tests for schema rendering, deterministic fallback, and fake LLM success.
- [ ] Implement `WorkReport`, markdown renderer, report context builder, deterministic summarizer, OpenAI adapter, and evidence validation.
- [ ] Persist structured JSON and generation metadata in `summaries`.
- [ ] Run `uv run pytest tests/test_reports.py -q`.

### Task 2: Projects And Work Items

**Files:**
- Modify: `src/cho_works/db.py`
- Modify: `src/cho_works/models.py`
- Modify: `src/cho_works/services.py`
- Test: `tests/test_projects_board.py`

- [ ] Write failing tests for project creation, automatic item creation from entries, and board grouping.
- [ ] Add `projects` and `work_items` tables.
- [ ] Add `ProjectService` and `WorkItemService`.
- [ ] Sync parsed entry items into work items when a project is present.
- [ ] Run `uv run pytest tests/test_projects_board.py -q`.

### Task 3: CLI And Web UI

**Files:**
- Modify: `src/cho_works/cli.py`
- Modify: `src/cho_works/web.py`
- Modify: `src/cho_works/templates/base.html`
- Modify: `src/cho_works/templates/index.html`
- Create: `src/cho_works/templates/projects.html`
- Create: `src/cho_works/templates/board.html`
- Test: `tests/test_cli.py`
- Test: `tests/test_web.py`

- [ ] Add `cho project add/list` and `cho item list`.
- [ ] Add `/projects` and `/board` routes.
- [ ] Add dashboard project/board metrics.
- [ ] Replace text-only pet status with a CSS parrot component.
- [ ] Run `uv run pytest tests/test_cli.py tests/test_web.py -q`.

### Task 4: Documentation And Verification

**Files:**
- Create: `AGENTS.md`
- Modify: `README.md`
- Test: full suite and local app smoke test.

- [ ] Document agent operating rules and product direction.
- [ ] Document project commands, standard reports, optional LLM setup, and parrot companion.
- [ ] Add test guard to prevent real API calls during tests.
- [ ] Run `uv run pytest -q`.
- [ ] Run CLI smoke commands.
- [ ] Run the web server and verify HTTP 200.

