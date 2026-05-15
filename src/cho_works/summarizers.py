from __future__ import annotations

import os
from typing import Protocol

from cho_works.report_context import ReportContext
from cho_works.report_schema import EvidenceItem, KpiEvidence, WorkReport


HIGH_LEVEL_REPORT_TYPES = {"week", "month", "quarter", "year"}


class Summarizer(Protocol):
    def summarize(self, context: ReportContext) -> WorkReport:
        ...


class DeterministicSummarizer:
    def summarize(self, context: ReportContext) -> WorkReport:
        source_ids = context.source_entry_ids
        projects = _projects(context)
        work_done = _work_done_items(context)
        outcomes = _outcome_items(context, work_done)
        decisions = _items(context, "decision")
        blockers = _items(context, "blocker")
        meetings = _items(context, "meeting")
        next_actions = _items(context, "next_action")
        kpis = [
            KpiEvidence(
                name=row["name"],
                value=row["value"],
                unit=row["unit"],
                direction="unknown",
                context=f"{row['name']} {_format_value(row['value'])}{row['unit']}",
                evidence_entry_ids=[row["entry_id"]],
                confidence=row["confidence"],
            )
            for row in context.kpis
        ]
        summary = _executive_summary(context, work_done, outcomes, blockers, decisions, next_actions)
        warnings = [] if context.entries else ["해당 범위에 기록이 없습니다."]
        return WorkReport(
            report_type=context.report_type,
            period=context.period,
            project=context.project,
            source_entry_ids=source_ids,
            executive_summary=summary,
            work_done=work_done,
            outcomes=outcomes,
            kpis=kpis,
            decisions=decisions,
            blockers=blockers,
            meetings=meetings,
            next_actions=next_actions,
            risks=[],
            themes=projects,
            coverage={
                "entry_count": len(context.entries),
                "date_count": len({entry.work_date for entry in context.entries}),
                "projects": projects,
                "warnings": warnings,
            },
            generation={
                "mode": "deterministic",
                "model": None,
                "fallback_reason": None,
            },
        )


class OpenAIReportSummarizer:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("CHO_WORKS_OPENAI_MODEL", "gpt-4o-mini")

    def summarize(self, context: ReportContext) -> WorkReport:
        from cho_works.llm_client import OpenAIReportClient

        return OpenAIReportClient(model=self.model).summarize(context)


def choose_summarizer(explicit: Summarizer | None = None) -> Summarizer:
    if explicit is not None:
        return explicit
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIReportSummarizer()
    return DeterministicSummarizer()


def validate_report_evidence(report: WorkReport, context: ReportContext) -> None:
    if not context.validate_evidence(report.source_entry_ids):
        raise ValueError("Report source ids are outside the source context.")
    for collection in [
        report.work_done,
        report.outcomes,
        report.decisions,
        report.blockers,
        report.meetings,
        report.next_actions,
        report.risks,
        report.kpis,
    ]:
        for item in collection:
            if not item.evidence_entry_ids:
                raise ValueError("LLM report evidence items must cite at least one source entry id.")
            if not context.validate_evidence(item.evidence_entry_ids):
                raise ValueError("LLM report cited entry ids outside the source context.")


def _is_high_level_report(context: ReportContext) -> bool:
    return context.report_type in HIGH_LEVEL_REPORT_TYPES


def _work_done_items(context: ReportContext) -> list[EvidenceItem]:
    if _is_high_level_report(context):
        return _items_for_types(context, {"task", "outcome"})
    return _items(context, "task")


def _outcome_items(context: ReportContext, work_done: list[EvidenceItem]) -> list[EvidenceItem]:
    if _is_high_level_report(context):
        return _synthesized_outcomes(context, work_done)
    return _items(context, "outcome")


def _items(context: ReportContext, item_type: str) -> list[EvidenceItem]:
    return _items_for_types(context, {item_type})


def _items_for_types(context: ReportContext, item_types: set[str]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    seen: set[str] = set()
    for row in context.items:
        if row["item_type"] not in item_types:
            continue
        description = _polish_content(row["content"])
        key = " ".join(description.split()).casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            EvidenceItem(
                title=_title(description),
                description=description,
                project=row["project"],
                date=row["work_date"],
                evidence_entry_ids=[row["entry_id"]],
                confidence=0.8,
            )
        )
    return items


def _synthesized_outcomes(context: ReportContext, work_done: list[EvidenceItem]) -> list[EvidenceItem]:
    grouped: dict[str, list[EvidenceItem]] = {}
    fallback_project = context.project or "전체"
    for item in work_done:
        grouped.setdefault(item.project or fallback_project, []).append(item)

    outcomes: list[EvidenceItem] = []
    for project, items in grouped.items():
        if not _should_synthesize_outcome(items):
            continue
        evidence_ids = _dedupe(entry_id for item in items for entry_id in item.evidence_entry_ids)
        outcomes.append(
            EvidenceItem(
                title=f"{project} 성과",
                description=_outcome_description(items),
                project=None if project == "전체" else project,
                date=None,
                evidence_entry_ids=evidence_ids,
                confidence=0.7,
            )
        )
    return outcomes


def _should_synthesize_outcome(items: list[EvidenceItem]) -> bool:
    if len(items) >= 2:
        return True
    return False


def _outcome_description(items: list[EvidenceItem]) -> str:
    highlights = [_compact_sentence(item.description) for item in items[:3]]
    joined = _join_korean(highlights)
    suffix = " 등" if len(items) > len(highlights) else ""
    return f"작업 {len(items)}건 기반 주요 진행 내용 구체화. 근거 작업은 {joined}{suffix}."


def _compact_sentence(value: str) -> str:
    return value.strip().rstrip(".!?")


def _join_korean(values: list[str]) -> str:
    if not values:
        return "관련 작업"
    if len(values) == 1:
        return values[0]
    return " / ".join(values)


def _projects(context: ReportContext) -> list[str]:
    values = [entry.project for entry in context.entries if entry.project]
    values.extend(row["project"] for row in context.items if row["project"])
    return _dedupe(values)


def _executive_summary(
    context: ReportContext,
    work_done: list[EvidenceItem],
    outcomes: list[EvidenceItem],
    blockers: list[EvidenceItem],
    decisions: list[EvidenceItem],
    next_actions: list[EvidenceItem],
) -> str:
    entries = context.entries
    if not entries:
        return "기록 없음."
    label = {
        "day": "일별 기록",
        "week": "주간 기록",
        "month": "월간 기록",
        "quarter": "분기 기록",
        "year": "연간 기록",
        "project": "프로젝트 기록",
    }.get(context.report_type, "기록")
    parts = []
    if work_done:
        parts.append(f"작업 {len(work_done)}건")
    if outcomes:
        parts.append(f"성과 {len(outcomes)}건")
    if decisions:
        parts.append(f"결정 {len(decisions)}건")
    if blockers:
        parts.append(f"리스크/블로커 {len(blockers)}건")
    if next_actions:
        parts.append(f"다음 액션 {len(next_actions)}건")
    if not parts:
        parts.append(f"기록 {len(entries)}건")
    project_text = ""
    projects = _projects(context)
    if projects:
        project_text = f" 주요 프로젝트: {', '.join(projects[:5])}."
    return f"{label}: " + ", ".join(parts) + f".{project_text}"


def _title(value: str) -> str:
    return value[:36] + ("..." if len(value) > 36 else "")


def _polish_content(value: str) -> str:
    text = value.strip()
    while text.startswith(("-", "*", "·")):
        text = text[1:].strip()
    if not text:
        return value.strip()
    if text.endswith((".", "!", "?", "다", "요")):
        return text
    return f"{text}."


def _dedupe(values) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _format_value(value) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)
