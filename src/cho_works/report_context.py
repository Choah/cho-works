from __future__ import annotations

import json
from dataclasses import dataclass

from cho_works.db import connect
from cho_works.models import WorkEntry
from cho_works.parsing import parse_entry_text
from cho_works.periods import parse_date
from cho_works.report_schema import ReportPeriod


@dataclass(frozen=True)
class ReportContext:
    report_type: str
    period: ReportPeriod
    project: str | None
    prompt_text: str
    entries: list[WorkEntry]
    items: list[dict]
    kpis: list[dict]

    @property
    def source_entry_ids(self) -> list[int]:
        return sorted(entry.id for entry in self.entries)

    def validate_evidence(self, ids: list[int]) -> bool:
        allowed = set(self.source_entry_ids)
        return all(entry_id in allowed for entry_id in ids)


def build_report_context(
    report_type: str,
    period_key: str,
    title: str,
    entries: list[WorkEntry],
    project: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    prompt_text: str = "",
) -> ReportContext:
    source_ids = [entry.id for entry in entries]
    period = ReportPeriod(
        key=period_key,
        label=title,
        start_date=start_date or _first_date(entries),
        end_date=end_date or _last_date(entries),
    )
    return ReportContext(
        report_type=report_type,
        period=period,
        project=project,
        prompt_text=prompt_text,
        entries=entries,
        items=_items_for(entries),
        kpis=_kpis_for(source_ids),
    )


def _items_for(entries: list[WorkEntry]) -> list[dict]:
    items = []
    for entry in sorted(entries, key=lambda item: (item.work_date, item.id)):
        parsed = parse_entry_text(entry.raw_text)
        for index, item in enumerate(parsed.items, start=1):
            items.append(
                {
                    "id": index,
                    "entry_id": entry.id,
                    "item_type": item.item_type,
                    "content": item.content,
                    "project": item.project or entry.project,
                    "tags_json": json.dumps(item.tags, ensure_ascii=False),
                    "work_date": entry.work_date,
                }
            )
    return items


def _kpis_for(entry_ids: list[int]) -> list[dict]:
    if not entry_ids:
        return []
    placeholders = ",".join("?" for _ in entry_ids)
    with connect() as conn:
        rows = conn.execute(
            f"""
            select id, entry_id, work_date, name, value, unit, confidence
            from kpi_observations
            where entry_id in ({placeholders})
            order by work_date, id
            """,
            entry_ids,
        ).fetchall()
    return [dict(row) for row in rows]


def _first_date(entries: list[WorkEntry]) -> str:
    if not entries:
        return ""
    return min(parse_date(entry.work_date) for entry in entries).isoformat()


def _last_date(entries: list[WorkEntry]) -> str:
    if not entries:
        return ""
    return max(parse_date(entry.work_date) for entry in entries).isoformat()
