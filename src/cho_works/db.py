from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from cho_works.config import database_path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            create table if not exists entries (
                id integer primary key autoincrement,
                work_date text not null,
                raw_text text not null,
                refined_text text,
                project text,
                source text not null default 'cli',
                created_at text not null,
                updated_at text not null
            );

            create table if not exists projects (
                id integer primary key autoincrement,
                key text not null unique,
                name text not null,
                status text not null default 'active',
                summary text,
                goal text,
                work_content text,
                target_users text,
                core_features text,
                additional_features text,
                execution_stage text,
                qualitative_effect text,
                quantitative_effect text,
                deliverables text,
                owner text,
                color text not null default '#2f6f5e',
                start_date text,
                target_date text,
                health text not null default 'green',
                kpi_targets_json text not null default '[]',
                created_at text not null,
                updated_at text not null,
                archived_at text
            );

            create table if not exists entry_items (
                id integer primary key autoincrement,
                entry_id integer not null references entries(id) on delete cascade,
                item_type text not null,
                content text not null,
                project text,
                tags_json text not null default '[]',
                created_at text not null
            );

            create table if not exists work_items (
                id integer primary key autoincrement,
                project_id integer not null references projects(id) on delete cascade,
                key text not null unique,
                title text not null,
                description text,
                item_type text not null default 'task',
                status text not null default 'todo',
                priority text not null default 'medium',
                outcome text,
                impact text,
                due_date text,
                completed_at text,
                tags_json text not null default '[]',
                source_entry_id integer references entries(id) on delete set null,
                source_entry_item_id integer references entry_items(id) on delete set null,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists kpi_observations (
                id integer primary key autoincrement,
                entry_id integer not null references entries(id) on delete cascade,
                work_date text not null,
                name text not null,
                value real not null,
                unit text not null,
                confidence real not null,
                created_at text not null
            );

            create table if not exists summaries (
                id integer primary key autoincrement,
                period_type text not null,
                period_key text not null,
                title text not null,
                body text not null,
                source_entry_ids_json text not null,
                generated_at text not null,
                report_json text,
                schema_version text,
                generation_mode text,
                model text,
                error text,
                unique(period_type, period_key)
            );

            create table if not exists summary_prompts (
                period_type text primary key,
                prompt_text text not null,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists competency_reviews (
                id integer primary key autoincrement,
                month_key text not null unique,
                work_problem_solving text,
                work_efficiency text,
                work_expertise text,
                people_communication text,
                people_collaboration text,
                people_trust text,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists reminder_configs (
                id integer primary key autoincrement,
                reminder_type text not null unique,
                time_local text not null,
                enabled integer not null default 1,
                days_of_week_json text not null default '[0, 1, 2, 3, 4]',
                snooze_minutes integer not null default 15,
                max_snoozes integer not null default 3,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists reminder_events (
                id integer primary key autoincrement,
                reminder_type text not null,
                scheduled_for text not null,
                status text not null,
                delivered_at text,
                acknowledged_at text,
                snooze_count integer not null default 0,
                failure_reason text,
                created_at text not null
            );

            create table if not exists pet_state (
                id integer primary key check (id = 1),
                streak_days integer not null default 0,
                care_points integer not null default 0,
                mood text not null default 'calm',
                message text not null default '오늘도 짧게 기록해볼까요.',
                unlocked_items_json text not null default '[]',
                updated_at text not null
            );
            """
        )
        _ensure_columns(
            conn,
            "entries",
            {
                "refined_text": "text",
            },
        )
        _ensure_columns(
            conn,
            "projects",
            {
                "target_users": "text",
                "work_content": "text",
                "core_features": "text",
                "additional_features": "text",
                "execution_stage": "text",
                "qualitative_effect": "text",
                "quantitative_effect": "text",
                "deliverables": "text",
            },
        )
        _ensure_columns(
            conn,
            "summaries",
            {
                "report_json": "text",
                "schema_version": "text",
                "generation_mode": "text",
                "model": "text",
                "error": "text",
            },
        )


def _ensure_columns(
    conn: sqlite3.Connection,
    table: str,
    columns: dict[str, str],
) -> None:
    existing = {
        row["name"]
        for row in conn.execute(f"pragma table_info({table})").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"alter table {table} add column {name} {definition}")
