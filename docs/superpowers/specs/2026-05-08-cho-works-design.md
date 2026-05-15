# Cho Works Design

## Goal

Build a local-first personal work-log assistant that receives daily work notes, organizes them into useful daily, weekly, monthly, quarterly, yearly, and project-level summaries, and helps the user maintain the habit through calm reminders and a small pet status system.

## Product Shape

Cho Works has two entry points:

- A CLI for fast capture, search, and summary generation.
- A local web app for reviewing today, recent activity, summaries, projects, reminders, and pet status.

Both entry points use the same service layer and SQLite database. The app is single-user, local-first, Korean-friendly, and designed for private work records rather than public reporting.

## MVP Scope

The first version must support:

- Free-form daily note capture.
- Optional metadata capture for date and project.
- Rule-based extraction of work items, blockers, decisions, outcomes, tags, and KPI-like numeric observations.
- Summary generation for day, week, month, quarter, year, and project.
- Search across raw entries, extracted items, projects, tags, and generated summaries.
- Reminder configuration and due-reminder detection.
- A small pet state that rewards consistent logging without judging productivity.
- CLI and web views over the same stored data.

The first version does not need cloud sync, user accounts, mobile app support, calendar integration, or LLM-backed summarization. The summarization module should be structured so an LLM provider can be added later.

## Architecture

The project uses Python 3.12, SQLite, Typer, FastAPI, Jinja2, and pytest.

The core package is split by responsibility:

- `cho_works.db`: SQLite connection, schema setup, and row helpers.
- `cho_works.models`: typed dataclasses used by services.
- `cho_works.parsing`: text parsing, item classification, tag/project/KPI extraction.
- `cho_works.services.entries`: create, list, and search work entries.
- `cho_works.services.summaries`: date-range and project summary generation.
- `cho_works.services.reminders`: reminder configs, reminder events, and due checks.
- `cho_works.services.pet`: pet state calculation from logging consistency.
- `cho_works.cli`: command-line interface.
- `cho_works.web.app`: local FastAPI application.

CLI and web handlers must stay thin. They call service functions and format the result.

## Data Model

SQLite tables:

- `entries`: raw work logs with `id`, `work_date`, `raw_text`, optional `project`, `source`, timestamps.
- `entry_items`: extracted units with `entry_id`, `item_type`, `content`, `project`, and `tags_json`.
- `kpi_observations`: numeric observations with `name`, `value`, `unit`, confidence, and source entry.
- `summaries`: generated period/project summaries with source entry ids.
- `reminder_configs`: local reminder settings.
- `reminder_events`: delivery, snooze, skip, miss, and acknowledgement history.
- `pet_state`: persisted pet progress, streak, care points, mood, and unlocked items.

All text is stored as UTF-8. Dates are stored as ISO `YYYY-MM-DD` strings. The default timezone is `Asia/Seoul`.

## Summary Behavior

Summaries are deterministic and source-grounded in the MVP:

- Daily summaries group work items, decisions, blockers, outcomes, and KPI observations for one date.
- Weekly, monthly, quarterly, and yearly summaries aggregate entries by date and project.
- Project summaries aggregate all entries and extracted items for a project.
- Every generated summary stores source entry ids to keep the result traceable.

The app should prefer concise Korean labels and output. It should not invent work that is not present in logs.

## Reminder Behavior

Reminders are calm checkpoints:

- Morning plan.
- Afternoon check.
- End-of-day review.

Each reminder config has a local time, enabled flag, days of week, snooze minutes, and max snoozes. The MVP detects due reminders while the CLI or web app runs. OS-level notification delivery is implemented as a best-effort adapter:

- macOS: `osascript display notification`.
- Linux: `notify-send` when available.
- Other environments: in-app/CLI due reminder output.

Reminder states are `scheduled`, `delivered`, `acknowledged`, `snoozed`, `skipped`, and `missed`.

## Pet Behavior

The pet system exists to reinforce the logging habit:

- Mood responds to recent logging consistency, not KPI performance.
- Care points increase when the user records or reviews work.
- Streaks are forgiving and should not shame the user for missed days.
- Korean pet messages are short and calm.

The pet appears in dashboard and summary views. It should not interrupt entry capture.

## Error Handling

The app should:

- Create the SQLite schema automatically.
- Return clear CLI errors for invalid dates or missing entries.
- Keep reminder notification failures non-fatal.
- Fall back to simple search when advanced SQLite search is unavailable.
- Never delete raw entries when summary generation or extraction fails.

## Testing

Tests cover:

- Text parsing and KPI extraction.
- Date period calculations for week, month, quarter, and year.
- Entry creation and extracted item persistence.
- Search behavior for Korean text, tags, projects, and summaries.
- Summary generation.
- Reminder due checks and state transitions.
- Pet state updates.
- CLI smoke behavior.
- Web route smoke behavior.

## Implementation Notes

The first implementation should use direct SQLite access through a small repository layer rather than an ORM. This keeps the MVP simple and transparent. The schema should be created idempotently at startup.

The default database path should be `~/.cho-works/cho_works.sqlite3`, overridable by `CHO_WORKS_DB_PATH` for tests and local development.

## Risks

- Korean search quality can be weak without language-specific tokenization, so substring search is required.
- Rule-based KPI extraction will miss nuance and should expose the raw source.
- Overactive reminders can become annoying, so defaults must be quiet.
- Pet mechanics can distract from the real goal if overbuilt.
- Summary quality depends on the user recording enough detail.

