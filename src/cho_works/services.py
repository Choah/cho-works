from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pathlib import Path

from cho_works.config import DEFAULT_TIMEZONE, database_path
from cho_works.db import connect, init_db
from cho_works.models import CompetencyReview, DueReminder, PetState, Project, Summary, WorkEntry, WorkItem
from cho_works.notifications import notify
from cho_works.parsing import parse_entry_text
from cho_works.periods import parse_date, period_key, period_range
from cho_works.report_context import build_report_context
from cho_works.report_schema import WORK_REPORT_SCHEMA_VERSION, WorkReport, render_report_markdown
from cho_works.summarizers import DeterministicSummarizer, choose_summarizer, validate_report_evidence


def _now() -> str:
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).replace(microsecond=0).isoformat()


def _today() -> date:
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()


def initialize_workspace() -> Path:
    init_db()
    SummaryPromptService().ensure_defaults()
    return database_path()


def _entry_from_row(row) -> WorkEntry:
    return WorkEntry(
        id=row["id"],
        work_date=row["work_date"],
        raw_text=row["raw_text"],
        refined_text=row["refined_text"],
        project=row["project"],
        source=row["source"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _summary_from_row(row) -> Summary:
    return Summary(
        period_type=row["period_type"],
        period_key=row["period_key"],
        title=row["title"],
        body=row["body"],
        source_entry_ids=json.loads(row["source_entry_ids_json"]),
    )


def _competency_review_from_row(row) -> CompetencyReview:
    return CompetencyReview(
        id=row["id"],
        month_key=row["month_key"],
        work_problem_solving=row["work_problem_solving"],
        work_efficiency=row["work_efficiency"],
        work_expertise=row["work_expertise"],
        people_communication=row["people_communication"],
        people_collaboration=row["people_collaboration"],
        people_trust=row["people_trust"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _project_from_row(row) -> Project:
    return Project(
        id=row["id"],
        key=row["key"],
        name=row["name"],
        status=row["status"],
        summary=row["summary"],
        goal=row["goal"],
        work_content=_row_get(row, "work_content"),
        target_users=_row_get(row, "target_users"),
        core_features=_row_get(row, "core_features"),
        additional_features=_row_get(row, "additional_features"),
        execution_stage=_row_get(row, "execution_stage"),
        qualitative_effect=_row_get(row, "qualitative_effect"),
        quantitative_effect=_row_get(row, "quantitative_effect"),
        deliverables=_row_get(row, "deliverables"),
        owner=row["owner"],
        color=row["color"],
        start_date=row["start_date"],
        target_date=row["target_date"],
        health=row["health"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _work_item_from_row(row) -> WorkItem:
    return WorkItem(
        id=row["id"],
        project_id=row["project_id"],
        key=row["key"],
        title=row["title"],
        description=row["description"],
        item_type=row["item_type"],
        status=row["status"],
        priority=row["priority"],
        outcome=row["outcome"],
        impact=row["impact"],
        due_date=row["due_date"],
        completed_at=row["completed_at"],
        source_entry_id=row["source_entry_id"],
        source_entry_item_id=row["source_entry_item_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        source_work_date=_row_get(row, "source_work_date"),
    )


def _row_get(row, key: str):
    return row[key] if key in row.keys() else None


class ProjectService:
    def __init__(self) -> None:
        init_db()

    def create_project(
        self,
        key: str,
        name: str,
        status: str = "active",
        summary: str | None = None,
        goal: str | None = None,
        work_content: str | None = None,
        target_users: str | None = None,
        core_features: str | None = None,
        additional_features: str | None = None,
        execution_stage: str | None = None,
        qualitative_effect: str | None = None,
        quantitative_effect: str | None = None,
        deliverables: str | None = None,
        owner: str | None = None,
        color: str = "#2f6f5e",
        start_date: str | None = None,
        target_date: str | None = None,
        health: str = "green",
    ) -> Project:
        key = _clean_project_text(key)
        name = _clean_project_text(name)
        normalized = _project_key(key)
        summary = _clean_optional_project_detail(summary)
        goal = _clean_optional_project_detail(goal)
        work_content = _clean_optional_project_detail(work_content)
        target_users = _clean_optional_project_detail(target_users)
        core_features = _clean_optional_project_detail(core_features)
        additional_features = _clean_optional_project_detail(additional_features)
        execution_stage = _clean_optional_project_detail(execution_stage)
        qualitative_effect = _clean_optional_project_detail(qualitative_effect)
        quantitative_effect = _clean_optional_project_detail(quantitative_effect)
        deliverables = _clean_optional_project_detail(deliverables)
        timestamp = _now()
        with connect() as conn:
            existing = self._find_project_row(conn, key)
            if not existing and name:
                existing = self._find_project_row(conn, name)
            if existing:
                normalized = existing["key"]
                summary = _value_or_existing(summary, existing, "summary")
                goal = _value_or_existing(goal, existing, "goal")
                work_content = _value_or_existing(work_content, existing, "work_content")
                target_users = _value_or_existing(target_users, existing, "target_users")
                core_features = _value_or_existing(core_features, existing, "core_features")
                additional_features = _value_or_existing(additional_features, existing, "additional_features")
                execution_stage = _value_or_existing(execution_stage, existing, "execution_stage")
                qualitative_effect = _value_or_existing(qualitative_effect, existing, "qualitative_effect")
                quantitative_effect = _value_or_existing(quantitative_effect, existing, "quantitative_effect")
                deliverables = _value_or_existing(deliverables, existing, "deliverables")
            aliases = {key, normalized, name}
            if existing:
                aliases.update({existing["key"], existing["name"]})
            conn.execute(
                """
                insert into projects(
                    key, name, status, summary, goal, work_content, target_users,
                    core_features, additional_features, execution_stage,
                    qualitative_effect, quantitative_effect, deliverables, owner, color,
                    start_date, target_date, health, created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(key) do update set
                    name = excluded.name,
                    status = excluded.status,
                    summary = excluded.summary,
                    goal = excluded.goal,
                    work_content = excluded.work_content,
                    target_users = excluded.target_users,
                    core_features = excluded.core_features,
                    additional_features = excluded.additional_features,
                    execution_stage = excluded.execution_stage,
                    qualitative_effect = excluded.qualitative_effect,
                    quantitative_effect = excluded.quantitative_effect,
                    deliverables = excluded.deliverables,
                    owner = excluded.owner,
                    color = excluded.color,
                    start_date = excluded.start_date,
                    target_date = excluded.target_date,
                    health = excluded.health,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized,
                    name,
                    status,
                    summary,
                    goal,
                    work_content,
                    target_users,
                    core_features,
                    additional_features,
                    execution_stage,
                    qualitative_effect,
                    quantitative_effect,
                    deliverables,
                    owner,
                    color,
                    start_date,
                    target_date,
                    health,
                    timestamp,
                    timestamp,
                ),
            )
            self._canonicalize_references(conn, normalized, aliases)
            row = conn.execute("select * from projects where key = ?", (normalized,)).fetchone()
        return _project_from_row(row)

    def ensure_project(self, name_or_key: str | None) -> Project | None:
        name_or_key = _clean_project_text(name_or_key)
        if not name_or_key:
            return None
        existing = self.find_by_key_or_name(name_or_key)
        if existing:
            return existing
        key = _project_key(name_or_key)
        return self.create_project(key=key, name=name_or_key)

    def find_by_key_or_name(self, name_or_key: str) -> Project | None:
        name_or_key = _clean_project_text(name_or_key)
        with connect() as conn:
            row = self._find_project_row(conn, name_or_key)
        return _project_from_row(row) if row else None

    def get_by_key(self, key: str) -> Project | None:
        with connect() as conn:
            row = conn.execute(
                "select * from projects where key = ?",
                (_project_key(key),),
            ).fetchone()
        return _project_from_row(row) if row else None

    def list_projects(self) -> list[Project]:
        self._backfill_legacy_projects()
        self._merge_duplicate_projects()
        with connect() as conn:
            rows = conn.execute(
                """
                select * from projects
                where status != 'archived'
                order by status, key
                """
            ).fetchall()
        return [_project_from_row(row) for row in rows]

    def _backfill_legacy_projects(self) -> None:
        timestamp = _now()
        with connect() as conn:
            rows = conn.execute(
                """
                select distinct project from entries
                where project is not null and project != ''
                union
                select distinct i.project
                from entry_items i
                join entries e on e.id = i.entry_id
                where i.project is not null and i.project != ''
                  and (e.project is null or e.project = '')
                """
            ).fetchall()
            for row in rows:
                raw_project = row["project"]
                raw_project = _clean_project_text(raw_project)
                normalized = _project_key(raw_project)
                existing = self._find_project_row(conn, raw_project)
                key = existing["key"] if existing else normalized
                if not existing:
                    conn.execute(
                        """
                        insert into projects(key, name, created_at, updated_at)
                        values (?, ?, ?, ?)
                        on conflict(key) do nothing
                        """,
                        (key, raw_project, timestamp, timestamp),
                    )
                self._canonicalize_references(conn, key, {row["project"], key})

    def _find_project_row(self, conn, name_or_key: str | None):
        text = _clean_project_text(name_or_key)
        if not text:
            return None
        candidates = {
            _project_key(text),
            _project_key(_strip_project_suffix(text)),
        }
        rows = conn.execute("select * from projects order by id").fetchall()
        for row in rows:
            if candidates & _project_alias_keys(row):
                return row
        return None

    def _merge_duplicate_projects(self) -> None:
        with connect() as conn:
            rows = conn.execute("select * from projects order by id").fetchall()
            aliases: dict[str, int] = {}
            canonical_rows: dict[int, object] = {}
            for row in rows:
                duplicate_of: int | None = None
                for alias in _project_alias_keys(row):
                    if alias in aliases:
                        duplicate_of = aliases[alias]
                        break
                if duplicate_of is not None and duplicate_of != row["id"]:
                    canonical = canonical_rows[duplicate_of]
                    self._merge_project_row(conn, canonical, row)
                    continue
                canonical_rows[row["id"]] = row
                for alias in _project_alias_keys(row):
                    aliases[alias] = row["id"]

    def _merge_project_row(self, conn, canonical, duplicate) -> None:
        duplicate_aliases = {duplicate["key"], duplicate["name"], _strip_project_suffix(duplicate["name"])}
        self._canonicalize_references(conn, canonical["key"], duplicate_aliases)
        conn.execute(
            "update work_items set project_id = ? where project_id = ?",
            (canonical["id"], duplicate["id"]),
        )
        conn.execute("delete from projects where id = ?", (duplicate["id"],))

    def _canonicalize_references(self, conn, canonical_key: str, aliases: set[str | None]) -> None:
        values = [alias for alias in aliases if alias]
        if not values:
            return
        placeholders = ",".join("?" for _ in values)
        conn.execute(
            f"update entries set project = ? where project in ({placeholders})",
            [canonical_key, *values],
        )
        conn.execute(
            f"update entry_items set project = ? where project in ({placeholders})",
            [canonical_key, *values],
        )


class WorkItemService:
    STATUSES = ["todo", "in_progress", "blocked", "review", "done", "dropped"]

    def __init__(self) -> None:
        init_db()

    def create_item(
        self,
        project_id: int,
        title: str,
        description: str | None = None,
        item_type: str = "task",
        status: str = "todo",
        priority: str = "medium",
        outcome: str | None = None,
        impact: str | None = None,
        due_date: str | None = None,
        completed_at: str | None = None,
        tags: list[str] | None = None,
        source_entry_id: int | None = None,
        source_entry_item_id: int | None = None,
    ) -> WorkItem:
        timestamp = _now()
        with connect() as conn:
            project = conn.execute("select key from projects where id = ?", (project_id,)).fetchone()
            if not project:
                raise ValueError("프로젝트를 찾을 수 없습니다.")
            key = self._next_key(conn, project["key"])
            cursor = conn.execute(
                """
                insert into work_items(
                    project_id, key, title, description, item_type, status,
                    priority, outcome, impact, due_date, completed_at,
                    tags_json, source_entry_id, source_entry_item_id,
                    created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    key,
                    title,
                    description,
                    item_type,
                    status,
                    priority,
                    outcome,
                    impact,
                    due_date,
                    completed_at,
                    json.dumps(tags or [], ensure_ascii=False),
                    source_entry_id,
                    source_entry_item_id,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "select * from work_items where id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return _work_item_from_row(row)

    def list_items(
        self,
        project_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[WorkItem]:
        clauses: list[str] = []
        params: list[object] = []
        if project_key:
            clauses.append("p.key = ?")
            params.append(_project_key(project_key))
        if status:
            clauses.append("w.status = ?")
            params.append(status)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        params.append(limit)
        with connect() as conn:
            rows = conn.execute(
                f"""
                select w.*, e.work_date as source_work_date
                from work_items w
                join projects p on p.id = w.project_id
                left join entries e on e.id = w.source_entry_id
                {where}
                order by w.id
                limit ?
                """,
                params,
            ).fetchall()
        return [_work_item_from_row(row) for row in rows]

    def list_items_for_entry(self, entry_id: int) -> list[WorkItem]:
        with connect() as conn:
            rows = conn.execute(
                """
                select w.*, e.work_date as source_work_date
                from work_items w
                left join entries e on e.id = w.source_entry_id
                where w.source_entry_id = ?
                order by w.source_entry_item_id, w.id
                """,
                (entry_id,),
            ).fetchall()
        return [_work_item_from_row(row) for row in rows]

    def items_by_entry_ids(self, entry_ids: list[int]) -> dict[int, list[WorkItem]]:
        if not entry_ids:
            return {}
        placeholders = ",".join("?" for _ in entry_ids)
        with connect() as conn:
            rows = conn.execute(
                f"""
                select w.*, e.work_date as source_work_date
                from work_items w
                left join entries e on e.id = w.source_entry_id
                where w.source_entry_id in ({placeholders})
                order by w.source_entry_id, w.source_entry_item_id, w.id
                """,
                entry_ids,
            ).fetchall()
        grouped: dict[int, list[WorkItem]] = {entry_id: [] for entry_id in entry_ids}
        for row in rows:
            grouped.setdefault(row["source_entry_id"], []).append(_work_item_from_row(row))
        return grouped

    def board(self) -> dict[str, list[WorkItem]]:
        EntryService().refresh_derived_items()
        return {status: self.list_items(status=status, limit=200) for status in self.STATUSES}

    def get_item(self, item_id: int) -> WorkItem | None:
        with connect() as conn:
            row = conn.execute(
                """
                select w.*, e.work_date as source_work_date
                from work_items w
                left join entries e on e.id = w.source_entry_id
                where w.id = ?
                """,
                (item_id,),
            ).fetchone()
        return _work_item_from_row(row) if row else None

    def update_item(
        self,
        item_id: int,
        title: str,
        status: str,
        priority: str,
        item_type: str,
        due_date: str | None = None,
        completed_at: str | None = None,
        description: str | None = None,
    ) -> WorkItem:
        existing = self.get_item(item_id)
        if not existing:
            raise ValueError("업무 카드를 찾을 수 없습니다.")
        title = title.strip()
        if not title:
            raise ValueError("업무 제목을 입력해주세요.")
        if status not in self.STATUSES:
            raise ValueError("지원하지 않는 상태입니다.")
        due_date = _clean_optional_date(due_date, "목표일")
        completed_at = _clean_optional_date(completed_at, "완료일")
        if status == "done" and not completed_at:
            completed_at = existing.completed_at or _today().isoformat()
        if status != "done" and not completed_at:
            completed_at = None
        outcome = title if status == "done" else None
        timestamp = _now()
        with connect() as conn:
            conn.execute(
                """
                update work_items
                set title = ?,
                    description = ?,
                    item_type = ?,
                    status = ?,
                    priority = ?,
                    outcome = ?,
                    due_date = ?,
                    completed_at = ?,
                    updated_at = ?
                where id = ?
                """,
                (
                    title,
                    description or None,
                    item_type,
                    status,
                    priority,
                    outcome,
                    due_date,
                    completed_at,
                    timestamp,
                    item_id,
                ),
            )
        updated = self.get_item(item_id)
        if not updated:
            raise ValueError("업무 카드를 다시 불러오지 못했습니다.")
        return updated

    def create_from_entry_item(
        self,
        project: Project,
        entry_id: int,
        entry_item_id: int,
        content: str,
        item_type: str,
        tags: list[str],
    ) -> WorkItem:
        status = _status_for_item_type(item_type)
        priority = "high" if status == "blocked" else "medium"
        completed_at = _now() if status == "done" else None
        return self.create_item(
            project_id=project.id,
            title=content,
            description=content,
            item_type=item_type,
            status=status,
            priority=priority,
            outcome=content if status == "done" else None,
            completed_at=completed_at,
            tags=tags,
            source_entry_id=entry_id,
            source_entry_item_id=entry_item_id,
        )

    def update_from_entry_item(
        self,
        work_item_id: int,
        project_id: int,
        content: str,
        item_type: str,
        source_entry_item_id: int,
    ) -> WorkItem:
        timestamp = _now()
        with connect() as conn:
            current = conn.execute(
                """
                select title, description, item_type, status, outcome, completed_at
                from work_items
                where id = ?
                """,
                (work_item_id,),
            ).fetchone()
            old_auto_status = _status_for_item_type(current["item_type"]) if current else None
            should_sync_status = bool(current and current["status"] == old_auto_status)
            has_auto_text = bool(current and current["title"] == current["description"])
            new_title = content if has_auto_text else current["title"]
            new_description = content if has_auto_text else current["description"]
            new_item_type = item_type if should_sync_status and has_auto_text else current["item_type"]
            new_status = _status_for_item_type(item_type) if should_sync_status else current["status"]
            completed_at = (
                _now()
                if should_sync_status and new_status == "done"
                else None
                if should_sync_status
                else current["completed_at"]
            )
            outcome = (
                content
                if should_sync_status and new_status == "done"
                else None
                if should_sync_status
                else current["outcome"]
            )
            conn.execute(
                """
                update work_items
                set project_id = ?,
                    title = ?,
                    description = ?,
                    item_type = ?,
                    status = ?,
                    outcome = ?,
                    completed_at = ?,
                    source_entry_item_id = ?,
                    updated_at = ?
                where id = ?
                """,
                (
                    project_id,
                    new_title,
                    new_description,
                    new_item_type,
                    new_status,
                    outcome,
                    completed_at,
                    source_entry_item_id,
                    timestamp,
                    work_item_id,
                ),
            )
            row = conn.execute(
                "select * from work_items where id = ?",
                (work_item_id,),
            ).fetchone()
        return _work_item_from_row(row)

    def delete_items(self, item_ids: list[int]) -> None:
        if not item_ids:
            return
        placeholders = ",".join("?" for _ in item_ids)
        with connect() as conn:
            conn.execute(
                f"delete from work_items where id in ({placeholders})",
                item_ids,
            )

    def _next_key(self, conn, project_key: str) -> str:
        pattern = f"{project_key}-%"
        row = conn.execute(
            """
            select key from work_items
            where key like ?
            order by id desc
            limit 1
            """,
            (pattern,),
        ).fetchone()
        if not row:
            return f"{project_key}-1"
        _, number = row["key"].rsplit("-", 1)
        return f"{project_key}-{int(number) + 1}"


class DailyWorkRefiner:
    def refine(self, raw_text: str) -> str:
        return refine_daily_work_text(raw_text)


class OpenAIDailyWorkRefiner:
    def __init__(self, fallback: DailyWorkRefiner | None = None) -> None:
        self.fallback = fallback or DailyWorkRefiner()

    def refine(self, raw_text: str) -> str:
        try:
            from cho_works.llm_client import OpenAIDailyWorkClient

            model = os.environ.get("CHO_WORKS_OPENAI_MODEL", "gpt-4o-mini")
            prompt_text = SummaryPromptService().get_prompt("day")
            refined = OpenAIDailyWorkClient(model=model).refine(raw_text, prompt_text)
        except Exception:
            return self.fallback.refine(raw_text)
        return refined or self.fallback.refine(raw_text)


def choose_daily_refiner(explicit: DailyWorkRefiner | None = None) -> DailyWorkRefiner:
    if explicit is not None:
        return explicit
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIDailyWorkRefiner()
    return DailyWorkRefiner()


class EntryService:
    def __init__(self, daily_refiner: DailyWorkRefiner | None = None) -> None:
        init_db()
        self.daily_refiner = choose_daily_refiner(daily_refiner)

    def add_entry(
        self,
        work_date: str,
        raw_text: str,
        project: str | None = None,
        source: str = "cli",
    ) -> WorkEntry:
        parsed, resolved_project, item_project_keys = self._prepare_details(work_date, raw_text, project)
        refined_text = self.daily_refiner.refine(raw_text)
        timestamp = _now()
        with connect() as conn:
            cursor = conn.execute(
                """
                insert into entries(work_date, raw_text, refined_text, project, source, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (work_date, raw_text, refined_text, resolved_project, source, timestamp, timestamp),
            )
            entry_id = int(cursor.lastrowid)
            item_rows = self._insert_details(conn, entry_id, work_date, parsed, item_project_keys, timestamp)
            row = conn.execute("select * from entries where id = ?", (entry_id,)).fetchone()
        self._sync_project_items(entry_id, resolved_project, item_rows)
        return _entry_from_row(row)

    def get_entry(self, entry_id: int) -> WorkEntry | None:
        with connect() as conn:
            row = conn.execute("select * from entries where id = ?", (entry_id,)).fetchone()
        return _entry_from_row(row) if row else None

    def update_entry(
        self,
        entry_id: int,
        work_date: str,
        raw_text: str,
        project: str | None = None,
    ) -> WorkEntry:
        if not self.get_entry(entry_id):
            raise ValueError("기록을 찾을 수 없습니다.")
        parsed, resolved_project, item_project_keys = self._prepare_details(work_date, raw_text, project)
        refined_text = self.daily_refiner.refine(raw_text)
        timestamp = _now()
        existing_work_items = self._work_items_for_entry(entry_id)
        with connect() as conn:
            conn.execute(
                """
                update entries
                set work_date = ?, raw_text = ?, refined_text = ?, project = ?, updated_at = ?
                where id = ?
                """,
                (work_date, raw_text, refined_text, resolved_project, timestamp, entry_id),
            )
            conn.execute("delete from kpi_observations where entry_id = ?", (entry_id,))
            conn.execute("delete from entry_items where entry_id = ?", (entry_id,))
            item_rows = self._insert_details(conn, entry_id, work_date, parsed, item_project_keys, timestamp)
            row = conn.execute("select * from entries where id = ?", (entry_id,)).fetchone()
        self._sync_project_items(entry_id, resolved_project, item_rows, existing_work_items)
        return _entry_from_row(row)

    def refresh_derived_items(self) -> None:
        entries = self.list_entries(limit=1000)
        for entry in entries:
            try:
                parsed, resolved_project, item_project_keys = self._prepare_details(
                    entry.work_date,
                    entry.raw_text,
                    entry.project,
                )
            except ValueError:
                continue
            timestamp = _now()
            refined_text = self.daily_refiner.refine(entry.raw_text)
            existing_work_items = self._work_items_for_entry(entry.id)
            with connect() as conn:
                conn.execute(
                    "update entries set refined_text = ?, updated_at = ? where id = ?",
                    (refined_text, timestamp, entry.id),
                )
                conn.execute("delete from kpi_observations where entry_id = ?", (entry.id,))
                conn.execute("delete from entry_items where entry_id = ?", (entry.id,))
                item_rows = self._insert_details(
                    conn,
                    entry.id,
                    entry.work_date,
                    parsed,
                    item_project_keys,
                    timestamp,
                )
            self._sync_project_items(entry.id, resolved_project, item_rows, existing_work_items)

    def _prepare_details(
        self,
        work_date: str,
        raw_text: str,
        project: str | None,
    ):
        try:
            parse_date(work_date)
        except ValueError as exc:
            raise ValueError("날짜 형식은 YYYY-MM-DD여야 합니다.") from exc
        parsed = parse_entry_text(raw_text)
        project_service = ProjectService()
        project_candidate = project or (parsed.projects[0] if parsed.projects else None)
        project_record = project_service.ensure_project(project_candidate)
        resolved_project = project_record.key if project_record else None
        item_project_keys: list[str | None] = []
        for item in parsed.items:
            item_candidate = resolved_project if project else (item.project or resolved_project)
            item_project_record = project_service.ensure_project(item_candidate)
            item_project_keys.append(item_project_record.key if item_project_record else None)
        return parsed, resolved_project, item_project_keys

    def _insert_details(
        self,
        conn,
        entry_id: int,
        work_date: str,
        parsed,
        item_project_keys: list[str | None],
        timestamp: str,
    ):
        item_rows = []
        for item, item_project in zip(parsed.items, item_project_keys, strict=True):
            cursor = conn.execute(
                """
                insert into entry_items(entry_id, item_type, content, project, tags_json, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    item.item_type,
                    item.content,
                    item_project,
                    json.dumps(item.tags, ensure_ascii=False),
                    timestamp,
                ),
            )
            item_rows.append((int(cursor.lastrowid), item, item_project))
        for kpi in parsed.kpis:
            conn.execute(
                """
                insert into kpi_observations(entry_id, work_date, name, value, unit, confidence, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    work_date,
                    kpi.name,
                    kpi.value,
                    kpi.unit,
                    kpi.confidence,
                    timestamp,
                ),
            )
        return item_rows

    def _sync_project_items(
        self,
        entry_id: int,
        project: str | None,
        item_rows,
        existing_work_items: list[WorkItem] | None = None,
    ) -> None:
        items = WorkItemService()
        existing = existing_work_items or []
        reused_ids: list[int] = []
        for index, (entry_item_id, parsed_item, item_project) in enumerate(item_rows):
            item_project = item_project or project
            if not item_project:
                continue
            project_record = ProjectService().ensure_project(item_project)
            if not project_record:
                continue
            if index < len(existing):
                work_item = existing[index]
                items.update_from_entry_item(
                    work_item.id,
                    project_record.id,
                    parsed_item.content,
                    parsed_item.item_type,
                    entry_item_id,
                )
                reused_ids.append(work_item.id)
                continue
            items.create_from_entry_item(
                project_record,
                entry_id,
                entry_item_id,
                parsed_item.content,
                parsed_item.item_type,
                parsed_item.tags,
            )
        stale_ids = [item.id for item in existing[len(item_rows):]]
        if stale_ids:
            WorkItemService().delete_items(stale_ids)

    def _work_items_for_entry(self, entry_id: int) -> list[WorkItem]:
        with connect() as conn:
            rows = conn.execute(
                """
                select *
                from work_items
                where source_entry_id = ?
                order by source_entry_item_id, id
                """,
                (entry_id,),
            ).fetchall()
        return [_work_item_from_row(row) for row in rows]

    def list_entries(
        self,
        start: str | None = None,
        end: str | None = None,
        project: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkEntry]:
        init_db()
        where, params = self._entry_filter(start=start, end=end, project=project)
        params.append(limit)
        params.append(offset)
        with connect() as conn:
            rows = conn.execute(
                f"""
                select * from entries
                {where}
                order by work_date desc, id desc
                limit ?
                offset ?
                """,
                params,
            ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def count_entries(
        self,
        start: str | None = None,
        end: str | None = None,
        project: str | None = None,
    ) -> int:
        init_db()
        where, params = self._entry_filter(start=start, end=end, project=project)
        with connect() as conn:
            row = conn.execute(
                f"""
                select count(*) as count
                from entries
                {where}
                """,
                params,
            ).fetchone()
        return int(row["count"])

    def recent_entry_cards(self, limit: int = 10, offset: int = 0) -> list[dict]:
        return [
            {
                "entry": entry,
                "refined_text": entry.refined_text or refine_daily_work_text(entry.raw_text),
            }
            for entry in self.list_entries(limit=limit, offset=offset)
        ]

    def _entry_filter(
        self,
        start: str | None = None,
        end: str | None = None,
        project: str | None = None,
    ) -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        if start:
            clauses.append("work_date >= ?")
            params.append(start)
        if end:
            clauses.append("work_date <= ?")
            params.append(end)
        if project:
            project_terms = _project_lookup_terms(project)
            placeholders = ",".join("?" for _ in project_terms)
            clauses.append(f"project in ({placeholders})")
            params.extend(project_terms)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        return where, params

    def search(self, query: str, limit: int = 20) -> list[WorkEntry]:
        init_db()
        pattern = f"%{query}%"
        with connect() as conn:
            direct_rows = conn.execute(
                """
                select distinct e.*
                from entries e
                left join entry_items i on i.entry_id = e.id
                left join kpi_observations k on k.entry_id = e.id
                where e.raw_text like ?
                   or coalesce(e.project, '') like ?
                   or coalesce(i.content, '') like ?
                   or coalesce(i.tags_json, '') like ?
                   or coalesce(k.name, '') like ?
                order by e.work_date desc, e.id desc
                limit ?
                """,
                (pattern, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
            ids = [row["id"] for row in direct_rows]
            summary_rows = conn.execute(
                """
                select source_entry_ids_json
                from summaries
                where title like ? or body like ?
                order by generated_at desc
                """,
                (pattern, pattern),
            ).fetchall()
            for row in summary_rows:
                ids.extend(json.loads(row["source_entry_ids_json"]))
            ids = _dedupe_ints(ids)[:limit]
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                select * from entries
                where id in ({placeholders})
                order by work_date desc, id desc
                """,
                ids,
            ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def projects(self) -> list[str]:
        return [project.key for project in ProjectService().list_projects()]


SUMMARY_PROMPT_LABELS = {
    "day": "일별",
    "week": "주별",
    "month": "월별",
    "quarter": "분기별",
    "year": "년별",
    "project": "프로젝트별",
}

DEFAULT_SUMMARY_PROMPTS = {
    "day": (
        "일별 입력 기록을 바탕으로 실제 수행 업무와 성과가 드러나도록 정리한다.\n\n"
        "목표:\n"
        "- 단순 나열이 아니라 목적, 진행 내용, 산출물, 성과, 이슈, 다음 액션을 구분한다.\n"
        "- 비슷하거나 반복되는 표현은 하나로 묶고 중복 내용은 제거한다.\n"
        "- 모호한 표현은 자연스럽게 다듬되 입력에 없는 사실은 만들지 않는다.\n"
        "- 중요도와 기여도가 드러나도록 정리한다.\n"
        "- 가능하면 무엇을 했는지보다 어떤 문제를 해결했고 어떤 결과를 만들었는지 중심으로 작성한다.\n\n"
        "출력 형식:\n"
        "## 1. 오늘의 핵심 요약\n"
        "## 2. 주요 업무\n"
        "## 3. 오늘의 성과\n"
        "## 4. 이슈 및 리스크\n"
        "## 5. 다음 액션\n"
        "## 6. 성과평가용 문장 후보\n\n"
        "작성 기준:\n"
        "- 과장하지 않는다.\n"
        "- 입력 기록에 근거해서만 작성한다.\n"
        "- 습니다체를 피하고 업무 보고에 바로 붙일 수 있는 짧은 명사형/서술형으로 쓴다. "
        "예: 작성. 개발. 정리. 검토."
    ),
    "week": (
        "이번 주 기록을 중복 없이 묶어 핵심 업무, 상위 성과, 결정, 리스크, 다음 액션으로 정리한다. "
        "완료 작업은 한 작업에 남기고, 여러 작업이 만든 결과가 있을 때만 성과로 묶는다. "
        "습니다체를 피하고 짧은 명사형/서술형으로 쓴다. 예: 작성. 개발. 정리. 검토."
    ),
    "month": (
        "이번 달 기록에서 여러 작업이 만든 상위 성과가 있는지 뽑아낸다. "
        "프로젝트별 산출물, 개선 효과, 성과 근거, 반복 이슈, 다음 달 액션을 중복 없이 정리한다. "
        "단일 완료 작업은 성과가 아니라 한 작업으로 둔다. 습니다체를 피한다."
    ),
    "quarter": (
        "이번 분기 기록을 전략적 상위 성과와 프로젝트 흐름 중심으로 정리한다. 월별 반복 표현은 줄이고, "
        "성과/리스크/의사결정/다음 분기 액션을 분명히 나눈다. 습니다체를 피한다."
    ),
    "year": (
        "올해 기록을 연간 성과 리뷰처럼 정리한다. 프로젝트별 주요 성과, 성과 근거, 성장한 역량, "
        "반복 리스크, 다음 해 개선 방향을 중복 없이 작성한다. 습니다체를 피한다."
    ),
    "project": (
        "해당 프로젝트의 누적 기록을 프로젝트 리포트처럼 정리한다. 목표 대비 진척, 완료한 산출물, "
        "결정사항, 리스크, 다음 액션을 근거 기록 기반으로 작성한다. 습니다체를 피한다."
    ),
}

LEGACY_SUMMARY_PROMPTS = {
    "day": (
        (
            "입력한 하루 기록의 말을 다듬어 한 업무가 무엇인지 정리한다. "
            "원문을 그대로 복사하지 말고 업무 보고 문장으로 자연스럽게 바꾼다. "
            "무엇을 진행했는지, 산출물이나 다음 액션이 있으면 짧게 덧붙인다."
        ),
        "하루 기록을 그대로 복사하지 말고 업무 보고 문장으로 다듬는다. "
        "무엇을 했는지, 어떤 성과나 산출물이 있었는지, 다음 액션이 무엇인지 짧게 정리한다.",
    ),
    "month": (
        (
            "이번 달 기록에서 어떤 성과가 있었는지 뽑아낸다. "
            "프로젝트별 완료 산출물, 개선 효과, KPI 후보, 반복 이슈, 다음 달 액션을 중복 없이 정리한다."
        ),
        "이번 달 기록을 누적 성과 중심으로 정리한다. 프로젝트별 진척, KPI 후보, 반복 이슈, "
        "다음 달로 넘길 액션을 중복 없이 요약한다.",
    ),
}


class SummaryPromptService:
    PERIODS = ["day", "week", "month", "quarter", "year", "project"]

    def __init__(self) -> None:
        init_db()

    def list_prompts(self) -> list[dict]:
        self.ensure_defaults()
        with connect() as conn:
            rows = conn.execute(
                """
                select period_type, prompt_text, updated_at
                from summary_prompts
                order by case period_type
                    when 'day' then 1
                    when 'week' then 2
                    when 'month' then 3
                    when 'quarter' then 4
                    when 'year' then 5
                    when 'project' then 6
                    else 99
                end
                """
            ).fetchall()
        return [
            {
                "period_type": row["period_type"],
                "label": SUMMARY_PROMPT_LABELS.get(row["period_type"], row["period_type"]),
                "prompt_text": row["prompt_text"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_prompt(self, period_type: str) -> str:
        if period_type not in self.PERIODS:
            return ""
        self.ensure_defaults()
        with connect() as conn:
            row = conn.execute(
                "select prompt_text from summary_prompts where period_type = ?",
                (period_type,),
            ).fetchone()
        return row["prompt_text"] if row else DEFAULT_SUMMARY_PROMPTS[period_type]

    def set_prompt(self, period_type: str, prompt_text: str) -> None:
        if period_type not in self.PERIODS:
            raise ValueError("지원하지 않는 프롬프트 유형입니다.")
        text = prompt_text.strip()
        if not text:
            raise ValueError("프롬프트를 입력해주세요.")
        timestamp = _now()
        with connect() as conn:
            conn.execute(
                """
                insert into summary_prompts(period_type, prompt_text, created_at, updated_at)
                values (?, ?, ?, ?)
                on conflict(period_type) do update set
                    prompt_text = excluded.prompt_text,
                    updated_at = excluded.updated_at
                """,
                (period_type, text, timestamp, timestamp),
            )

    def ensure_defaults(self) -> None:
        timestamp = _now()
        with connect() as conn:
            for period_type in self.PERIODS:
                conn.execute(
                    """
                    insert into summary_prompts(period_type, prompt_text, created_at, updated_at)
                    values (?, ?, ?, ?)
                    on conflict(period_type) do nothing
                    """,
                    (
                        period_type,
                        DEFAULT_SUMMARY_PROMPTS[period_type],
                        timestamp,
                        timestamp,
                    ),
                )
                for legacy_prompt in LEGACY_SUMMARY_PROMPTS.get(period_type, ()):
                    conn.execute(
                        """
                        update summary_prompts
                        set prompt_text = ?, updated_at = ?
                        where period_type = ? and prompt_text = ?
                        """,
                        (
                            DEFAULT_SUMMARY_PROMPTS[period_type],
                            timestamp,
                            period_type,
                            legacy_prompt,
                        ),
                    )


COMPETENCY_WORK_FIELDS = (
    ("work_problem_solving", "문제해결"),
    ("work_efficiency", "업무효율성"),
    ("work_expertise", "전문기술/지식"),
)

COMPETENCY_PEOPLE_FIELDS = (
    ("people_communication", "커뮤니케이션"),
    ("people_collaboration", "협업"),
    ("people_trust", "상호존중/신뢰"),
)

COMPETENCY_SECTIONS = (
    ("Work", COMPETENCY_WORK_FIELDS),
    ("People", COMPETENCY_PEOPLE_FIELDS),
)


class CompetencyReviewService:
    def __init__(self) -> None:
        init_db()

    def normalize_month(self, month_key: str | None) -> str:
        text = (month_key or "").strip()
        if not text:
            today = _today()
            return f"{today.year}-{today.month:02d}"
        anchor = f"{text}-01" if re.fullmatch(r"\d{4}-\d{2}", text) else text
        try:
            parsed = parse_date(anchor)
        except ValueError as exc:
            raise ValueError("월은 YYYY-MM 형식으로 입력해주세요.") from exc
        return f"{parsed.year}-{parsed.month:02d}"

    def upsert_month(
        self,
        month_key: str,
        work_problem_solving: str | None = None,
        work_efficiency: str | None = None,
        work_expertise: str | None = None,
        people_communication: str | None = None,
        people_collaboration: str | None = None,
        people_trust: str | None = None,
    ) -> CompetencyReview:
        month_key = self.normalize_month(month_key)
        values = {
            "work_problem_solving": _clean_optional_project_detail(work_problem_solving),
            "work_efficiency": _clean_optional_project_detail(work_efficiency),
            "work_expertise": _clean_optional_project_detail(work_expertise),
            "people_communication": _clean_optional_project_detail(people_communication),
            "people_collaboration": _clean_optional_project_detail(people_collaboration),
            "people_trust": _clean_optional_project_detail(people_trust),
        }
        timestamp = _now()
        with connect() as conn:
            conn.execute(
                """
                insert into competency_reviews(
                    month_key, work_problem_solving, work_efficiency, work_expertise,
                    people_communication, people_collaboration, people_trust, created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(month_key) do update set
                    work_problem_solving = excluded.work_problem_solving,
                    work_efficiency = excluded.work_efficiency,
                    work_expertise = excluded.work_expertise,
                    people_communication = excluded.people_communication,
                    people_collaboration = excluded.people_collaboration,
                    people_trust = excluded.people_trust,
                    updated_at = excluded.updated_at
                """,
                (
                    month_key,
                    values["work_problem_solving"],
                    values["work_efficiency"],
                    values["work_expertise"],
                    values["people_communication"],
                    values["people_collaboration"],
                    values["people_trust"],
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "select * from competency_reviews where month_key = ?",
                (month_key,),
            ).fetchone()
        return _competency_review_from_row(row)

    def get_month(self, month_key: str | None) -> CompetencyReview | None:
        normalized = self.normalize_month(month_key)
        with connect() as conn:
            row = conn.execute(
                "select * from competency_reviews where month_key = ?",
                (normalized,),
            ).fetchone()
        return _competency_review_from_row(row) if row else None

    def list_for_period(self, period_type: str, anchor: str | date | None = None) -> list[CompetencyReview]:
        anchor_date = self._anchor_date(anchor)
        start, end = period_range(period_type, anchor_date)
        start_key = f"{start.year}-{start.month:02d}"
        end_key = f"{end.year}-{end.month:02d}"
        with connect() as conn:
            rows = conn.execute(
                """
                select * from competency_reviews
                where month_key between ? and ?
                order by month_key
                """,
                (start_key, end_key),
            ).fetchall()
        return [_competency_review_from_row(row) for row in rows]

    def summarize(self, period_type: str, anchor: str | date | None = None) -> dict:
        if period_type not in {"month", "quarter", "year"}:
            raise ValueError("역량 평가는 월/분기/연 단위만 지원합니다.")
        anchor_date = self._anchor_date(anchor)
        reviews = self.list_for_period(period_type, anchor_date)
        return {
            "period_type": period_type,
            "period_key": period_key(period_type, anchor_date),
            "title": self._title(period_type, anchor_date),
            "reviews": reviews,
            "sections": self._sections(reviews),
        }

    def _anchor_date(self, anchor: str | date | None) -> date:
        if anchor is None:
            today = _today()
            return date(today.year, today.month, 1)
        if isinstance(anchor, date):
            return anchor
        return parse_date(f"{self.normalize_month(anchor)}-01")

    def _title(self, period_type: str, anchor: date) -> str:
        if period_type == "month":
            return f"{anchor.year}년 {anchor.month}월 역량 평가"
        if period_type == "quarter":
            quarter = ((anchor.month - 1) // 3) + 1
            return f"{anchor.year}년 {quarter}분기 역량 평가"
        return f"{anchor.year}년 연간 역량 평가"

    def _sections(self, reviews: list[CompetencyReview]) -> list[dict]:
        sections = []
        for title, fields in COMPETENCY_SECTIONS:
            items = []
            for field, label in fields:
                entries = [
                    {"month": review.month_key, "text": getattr(review, field)}
                    for review in reviews
                    if getattr(review, field)
                ]
                if entries:
                    items.append({"field": field, "label": label, "entries": entries})
            sections.append({"title": title, "items": items})
        return sections


class SummaryService:
    def __init__(self, summarizer=None) -> None:
        init_db()
        self.summarizer = summarizer

    def get_or_generate(self, period_type: str, target: str | None = None) -> Summary:
        entries, key, _, _, _ = self._scope(period_type, target)
        source_ids = sorted(entry.id for entry in entries)
        existing = self._get_row(period_type, key)
        if existing and not self._should_refresh_generated_summary(existing, source_ids):
            return _summary_from_row(existing)
        return self.generate(period_type, target)

    def generate(self, period_type: str, target: str | None = None) -> Summary:
        entries, key, title, start_date, end_date = self._scope(period_type, target)
        source_ids = sorted(entry.id for entry in entries)
        prompt_text = SummaryPromptService().get_prompt(period_type)
        context = build_report_context(
            period_type,
            key,
            title,
            entries,
            project=target if period_type == "project" else None,
            start_date=start_date,
            end_date=end_date,
            prompt_text=prompt_text,
        )
        report = self._build_report(context)
        body = render_report_markdown(report)
        summary = Summary(
            period_type=period_type,
            period_key=key,
            title=title,
            body=body,
            source_entry_ids=source_ids,
        )
        self._save(summary, report)
        return summary

    def update_summary(self, period_type: str, period_key: str, title: str, body: str) -> Summary:
        title = title.strip()
        body = body.strip()
        if not title:
            raise ValueError("보고서 제목을 입력해주세요.")
        if not body:
            raise ValueError("보고서 내용을 입력해주세요.")
        existing = self._get(period_type, period_key)
        if not existing:
            raise ValueError("수정할 보고서를 찾을 수 없습니다.")
        with connect() as conn:
            conn.execute(
                """
                update summaries
                set title = ?,
                    body = ?,
                    generated_at = ?,
                    report_json = null,
                    schema_version = null,
                    generation_mode = 'edited',
                    model = null,
                    error = null
                where period_type = ? and period_key = ?
                """,
                (title, body, _now(), period_type, period_key),
            )
        updated = self._get(period_type, period_key)
        if not updated:
            raise ValueError("수정한 보고서를 다시 불러오지 못했습니다.")
        return updated

    def source_entries(self, period_type: str, target: str | None = None) -> list[WorkEntry]:
        entries, _, _, _, _ = self._scope(period_type, target)
        return entries

    def entries_by_ids(self, entry_ids: list[int]) -> list[WorkEntry]:
        if not entry_ids:
            return []
        placeholders = ",".join("?" for _ in entry_ids)
        with connect() as conn:
            rows = conn.execute(
                f"""
                select *
                from entries
                where id in ({placeholders})
                order by work_date desc, id desc
                """,
                entry_ids,
            ).fetchall()
        by_id = {_entry_from_row(row).id: _entry_from_row(row) for row in rows}
        return [by_id[entry_id] for entry_id in entry_ids if entry_id in by_id]

    def _get(self, period_type: str, period_key: str) -> Summary | None:
        row = self._get_row(period_type, period_key)
        return _summary_from_row(row) if row else None

    def _get_row(self, period_type: str, period_key: str):
        with connect() as conn:
            row = conn.execute(
                """
                select *
                from summaries
                where period_type = ? and period_key = ?
                """,
                (period_type, period_key),
            ).fetchone()
        return row

    def _should_refresh_generated_summary(self, row, source_ids: list[int]) -> bool:
        if row["generation_mode"] == "edited":
            return False
        try:
            saved_source_ids = sorted(json.loads(row["source_entry_ids_json"]))
        except (TypeError, json.JSONDecodeError):
            return True
        if saved_source_ids != source_ids:
            return True
        return row["schema_version"] != WORK_REPORT_SCHEMA_VERSION

    def _scope(self, period_type: str, target: str | None = None):
        if period_type == "project":
            if not target:
                raise ValueError("프로젝트 요약에는 --project 값이 필요합니다.")
            entries = EntryService().list_entries(project=target, limit=500)
            title = f"프로젝트 {target} 요약"
            return entries, target, title, None, None
        if period_type not in {"day", "week", "month", "quarter", "year"}:
            raise ValueError("지원하지 않는 기간입니다. day, week, month, quarter, year, project 중 하나를 사용하세요.")
        anchor = target or _today().isoformat()
        try:
            start, end = period_range(period_type, anchor)
        except ValueError as exc:
            raise ValueError("날짜 형식은 YYYY-MM-DD여야 합니다.") from exc
        entries = EntryService().list_entries(start.isoformat(), end.isoformat(), limit=500)
        key = period_key(period_type, anchor)
        title = _summary_title(period_type, key, parse_date(anchor))
        return entries, key, title, start.isoformat(), end.isoformat()

    def _build_report(self, context) -> WorkReport:
        summarizer = choose_summarizer(self.summarizer)
        try:
            report = summarizer.summarize(context)
            report = WorkReport.model_validate(
                report.model_dump(warnings=False) if isinstance(report, WorkReport) else report
            )
            validate_report_evidence(report, context)
            return report
        except Exception as exc:
            fallback = DeterministicSummarizer().summarize(context)
            return WorkReport.model_validate(
                fallback.model_copy(
                    update={
                        "generation": {
                            "mode": "fallback",
                            "model": None,
                            "fallback_reason": str(exc),
                        }
                    }
                ).model_dump(warnings=False)
            )

    def _build_body(self, entries: list[WorkEntry]) -> str:
        if not entries:
            return "기록이 없습니다."
        entry_ids = [entry.id for entry in entries]
        lines = ["핵심 요약", ""]
        lines.append("날짜/프로젝트")
        for entry in sorted(entries, key=lambda item: (item.work_date, item.id)):
            project = f" [{entry.project}]" if entry.project else ""
            lines.append(f"- {entry.work_date}{project}: {entry.raw_text}")
        grouped = self._items_grouped(entry_ids)
        section_labels = [
            ("outcome", "완료 작업"),
            ("decision", "결정"),
            ("meeting", "회의/논의"),
            ("task", "업무"),
            ("blocker", "이슈/블로커"),
        ]
        for item_type, label in section_labels:
            items = grouped.get(item_type, [])
            if not items:
                continue
            lines.append("")
            lines.append(label)
            for item in items:
                project = f" [{item['project']}]" if item["project"] else ""
                lines.append(f"- {item['work_date']}{project}: {item['content']}")
        metrics = self._metrics_for(entry_ids)
        if metrics:
            lines.append("")
            lines.append("KPI 후보")
            for metric in metrics:
                value = metric["value"]
                if float(value).is_integer():
                    value = int(value)
                lines.append(f"- {metric['name']}: {value}{metric['unit']}")
        return "\n".join(lines)

    def _metrics_for(self, entry_ids: list[int]) -> list[dict]:
        if not entry_ids:
            return []
        placeholders = ",".join("?" for _ in entry_ids)
        with connect() as conn:
            rows = conn.execute(
                f"""
                select name, value, unit
                from kpi_observations
                where entry_id in ({placeholders})
                order by work_date, id
                """,
                entry_ids,
            ).fetchall()
        return [dict(row) for row in rows]

    def _items_for(self, entry_ids: list[int], item_type: str) -> list[str]:
        if not entry_ids:
            return []
        placeholders = ",".join("?" for _ in entry_ids)
        with connect() as conn:
            rows = conn.execute(
                f"""
                select content
                from entry_items
                where entry_id in ({placeholders}) and item_type = ?
                order by id
                """,
                [*entry_ids, item_type],
            ).fetchall()
        return [row["content"] for row in rows]

    def _items_grouped(self, entry_ids: list[int]) -> dict[str, list[dict]]:
        if not entry_ids:
            return {}
        placeholders = ",".join("?" for _ in entry_ids)
        with connect() as conn:
            rows = conn.execute(
                f"""
                select i.item_type, i.content, i.project, e.work_date
                from entry_items i
                join entries e on e.id = i.entry_id
                where i.entry_id in ({placeholders})
                order by e.work_date, i.id
                """,
                entry_ids,
            ).fetchall()
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["item_type"], []).append(dict(row))
        return grouped

    def _save(self, summary: Summary, report: WorkReport | None = None) -> None:
        report_json = report.model_dump_json() if report else None
        schema_version = report.schema_version if report else None
        generation_mode = report.generation.mode if report else None
        model = report.generation.model if report else None
        error = report.generation.fallback_reason if report else None
        with connect() as conn:
            conn.execute(
                """
                insert into summaries(
                    period_type, period_key, title, body, source_entry_ids_json,
                    generated_at, report_json, schema_version, generation_mode,
                    model, error
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(period_type, period_key) do update set
                    title = excluded.title,
                    body = excluded.body,
                    source_entry_ids_json = excluded.source_entry_ids_json,
                    generated_at = excluded.generated_at,
                    report_json = excluded.report_json,
                    schema_version = excluded.schema_version,
                    generation_mode = excluded.generation_mode,
                    model = excluded.model,
                    error = excluded.error
                """,
                (
                    summary.period_type,
                    summary.period_key,
                    summary.title,
                    summary.body,
                    json.dumps(summary.source_entry_ids),
                    _now(),
                    report_json,
                    schema_version,
                    generation_mode,
                    model,
                    error,
                ),
            )


class ReminderService:
    def __init__(self) -> None:
        init_db()

    def set_config(
        self,
        reminder_type: str,
        time_local: str,
        enabled: bool = True,
        days_of_week: list[int] | None = None,
    ) -> None:
        _parse_time(time_local)
        timestamp = _now()
        days = days_of_week if days_of_week is not None else [0, 1, 2, 3, 4]
        with connect() as conn:
            conn.execute(
                """
                insert into reminder_configs(
                    reminder_type, time_local, enabled, days_of_week_json,
                    created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?)
                on conflict(reminder_type) do update set
                    time_local = excluded.time_local,
                    enabled = excluded.enabled,
                    days_of_week_json = excluded.days_of_week_json,
                    updated_at = excluded.updated_at
                """,
                (
                    reminder_type,
                    time_local,
                    1 if enabled else 0,
                    json.dumps(days),
                    timestamp,
                    timestamp,
                ),
            )

    def due(self, now_iso: str | None = None) -> list[DueReminder]:
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
        today = now.date().isoformat()
        with connect() as conn:
            configs = conn.execute(
                "select * from reminder_configs where enabled = 1 order by time_local"
            ).fetchall()
            due: list[DueReminder] = []
            for config in configs:
                days = json.loads(config["days_of_week_json"])
                if now.weekday() not in days:
                    continue
                scheduled_dt = datetime.combine(
                    now.date(),
                    _parse_time(config["time_local"]),
                    tzinfo=now.tzinfo,
                )
                scheduled_for = scheduled_dt.isoformat()
                if now < scheduled_dt:
                    continue
                exists = conn.execute(
                    """
                    select 1 from reminder_events
                    where reminder_type = ? and scheduled_for = ?
                      and status in ('delivered', 'acknowledged', 'skipped', 'missed')
                    """,
                    (config["reminder_type"], scheduled_for),
                ).fetchone()
                if exists:
                    continue
                due.append(
                    DueReminder(
                        reminder_type=config["reminder_type"],
                        scheduled_for=scheduled_for,
                        message=_reminder_message(config["reminder_type"], today),
                    )
                )
        return due

    def deliver_due(self, now_iso: str | None = None) -> list[DueReminder]:
        due = self.due(now_iso)
        for reminder in due:
            notify("Cho Works", reminder.message)
            self.mark_delivered(reminder)
        return due

    def mark_delivered(self, reminder: DueReminder) -> None:
        self._record_event(
            reminder.reminder_type,
            reminder.scheduled_for,
            "delivered",
            delivered_at=_now(),
        )

    def acknowledge(self, reminder: DueReminder) -> None:
        self._record_event(
            reminder.reminder_type,
            reminder.scheduled_for,
            "acknowledged",
            acknowledged_at=_now(),
        )

    def skip(self, reminder: DueReminder) -> None:
        self._record_event(reminder.reminder_type, reminder.scheduled_for, "skipped")

    def _record_event(
        self,
        reminder_type: str,
        scheduled_for: str,
        status: str,
        delivered_at: str | None = None,
        acknowledged_at: str | None = None,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """
                insert into reminder_events(
                    reminder_type, scheduled_for, status, delivered_at,
                    acknowledged_at, created_at
                )
                values (?, ?, ?, ?, ?, ?)
                """,
                (reminder_type, scheduled_for, status, delivered_at, acknowledged_at, _now()),
            )


class PetService:
    def __init__(self) -> None:
        init_db()

    def refresh(self, today: str | None = None) -> PetState:
        anchor = parse_date(today or _today().isoformat())
        streak = self._streak(anchor)
        care_points = streak * 10
        mood = "focused" if streak >= 5 else "happy" if streak >= 2 else "calm"
        message = _pet_message(streak)
        unlocked_items = ["작은 노트"] if streak >= 3 else []
        state = PetState(
            streak_days=streak,
            care_points=care_points,
            mood=mood,
            message=message,
            unlocked_items=unlocked_items,
        )
        with connect() as conn:
            conn.execute(
                """
                insert into pet_state(
                    id, streak_days, care_points, mood, message,
                    unlocked_items_json, updated_at
                )
                values (1, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    streak_days = excluded.streak_days,
                    care_points = excluded.care_points,
                    mood = excluded.mood,
                    message = excluded.message,
                    unlocked_items_json = excluded.unlocked_items_json,
                    updated_at = excluded.updated_at
                """,
                (
                    state.streak_days,
                    state.care_points,
                    state.mood,
                    state.message,
                    json.dumps(state.unlocked_items, ensure_ascii=False),
                    _now(),
                ),
            )
        return state

    def _streak(self, anchor: date) -> int:
        with connect() as conn:
            rows = conn.execute("select distinct work_date from entries").fetchall()
        dates = {parse_date(row["work_date"]) for row in rows}
        streak = 0
        cursor = anchor
        while cursor in dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak


def _summary_title(period_type: str, key: str, anchor: date) -> str:
    if period_type == "day":
        return f"{anchor.year}년 {anchor.month}월 {anchor.day}일 일별 요약"
    if period_type == "week":
        start, end = period_range("week", anchor)
        return (
            f"{anchor.year}년 {anchor.month}월 {_week_of_month(anchor)}주차 주간 요약 "
            f"({_month_day_label(start)}-{_month_day_label(end)})"
        )
    if period_type == "month":
        return f"{anchor.year}년 {anchor.month}월 월간 요약"
    if period_type == "quarter":
        quarter = ((anchor.month - 1) // 3) + 1
        return f"{anchor.year}년 {quarter}분기 요약"
    if period_type == "year":
        return f"{anchor.year}년 연간 요약"
    raise ValueError(f"unsupported period type: {period_type}")


def _week_of_month(anchor: date) -> int:
    week_start, _ = period_range("week", anchor)
    first_of_month = date(anchor.year, anchor.month, 1)
    first_week_start, _ = period_range("week", first_of_month)
    return ((week_start - first_week_start).days // 7) + 1


def _month_day_label(day: date) -> str:
    return f"{day.month:02d}.{day.day:02d}"


def refine_daily_work_text(raw_text: str) -> str:
    parts = []
    for line in raw_text.replace("&", "및").splitlines():
        cleaned = _clean_daily_line(line)
        if cleaned:
            parts.append(_finish_daily_sentence(cleaned))
    if not parts:
        cleaned = _clean_daily_line(raw_text.replace("&", "및"))
        return _finish_daily_sentence(cleaned) if cleaned else raw_text
    return "\n".join(parts)


def _clean_project_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _clean_optional_project_detail(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _value_or_existing(value: str | None, row, key: str) -> str | None:
    return value if value is not None else _row_get(row, key)


def _strip_project_suffix(value: str | None) -> str:
    text = _clean_project_text(value)
    suffix = " 프로젝트"
    if text.endswith(suffix):
        return text[: -len(suffix)].strip()
    return text


def _project_alias_keys(row) -> set[str]:
    return {
        _project_key(row["key"]),
        _project_key(row["name"]),
        _project_key(_strip_project_suffix(row["name"])),
    }


def _clean_daily_line(value: str) -> str:
    text = value.strip()
    while text.startswith(("-", "*", "·")):
        text = text[1:].strip()
    text = text.replace("&", "및")
    return " ".join(text.split())


def _finish_daily_sentence(value: str) -> str:
    replacements = (
        ("지금 작성하고 있어", "작성"),
        ("지금 정리하고 있어", "정리"),
        ("지금 개발하고 있어", "개발"),
        ("지금 검토하고 있어", "검토"),
        ("작성하고 있어", "작성"),
        ("정리하고 있어", "정리"),
        ("개발하고 있어", "개발"),
        ("검토하고 있어", "검토"),
        ("진행하고 있어", "진행"),
        ("작성하고 있습니다", "작성"),
        ("정리하고 있습니다", "정리"),
        ("개발하고 있습니다", "개발"),
        ("검토하고 있습니다", "검토"),
        ("진행하고 있습니다", "진행"),
        ("작성했습니다", "작성"),
        ("정리했습니다", "정리"),
        ("개발했습니다", "개발"),
        ("검토했습니다", "검토"),
        ("진행했습니다", "진행"),
    )
    text = value.strip().rstrip(".!?")
    for source, target in replacements:
        if text.endswith(source):
            text = text[: -len(source)] + target
            break
    return f"{text.strip()}."


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _clean_optional_date(value: str | None, label: str) -> str | None:
    text = value.strip() if value else ""
    if not text:
        return None
    try:
        return parse_date(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{label} 형식은 YYYY-MM-DD여야 합니다.") from exc


def _reminder_message(reminder_type: str, today: str) -> str:
    labels = {
        "morning_plan": "오전 계획을 짧게 남겨볼까요.",
        "afternoon_check": "오후 진행 상황을 한 줄로 점검해볼까요.",
        "end_of_day": "퇴근 전 회고를 남길 시간입니다.",
    }
    return labels.get(reminder_type, f"{today} 기록 체크포인트입니다.")


def _pet_message(streak: int) -> str:
    if streak >= 5:
        return "이번 주 기록 흐름이 안정적이에요."
    if streak >= 2:
        return "짧게라도 남기면 흐름이 이어져요."
    if streak == 1:
        return "오늘 기록 완료. 수고했어요."
    return "오늘도 짧게 기록해볼까요."


def _project_key(value: str) -> str:
    key = value.strip().upper().replace(" ", "-")
    if key.endswith("-프로젝트"):
        key = key.removesuffix("-프로젝트")
    if key.endswith("프로젝트"):
        key = key.removesuffix("프로젝트")
    return "".join(ch for ch in key if ch.isalnum() or ch == "-") or "WORK"


def _project_lookup_terms(value: str) -> list[str]:
    terms = [value, _project_key(value)]
    project = ProjectService().find_by_key_or_name(value)
    if project:
        terms.extend([project.key, project.name])
    deduped: list[str] = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return deduped


def _status_for_item_type(item_type: str) -> str:
    if item_type in {"outcome", "decision"}:
        return "done"
    if item_type == "blocker":
        return "blocked"
    if item_type == "meeting":
        return "review"
    if item_type == "next_action":
        return "todo"
    return "todo"


def _dedupe_ints(values: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
