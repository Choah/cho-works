from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


WORK_REPORT_SCHEMA_VERSION = "1.2"


class ReportPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    start_date: str
    end_date: str


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    project: str | None = None
    date: str | None = None
    evidence_entry_ids: list[int] = Field(default_factory=list)
    confidence: float = 0.75


class KpiEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    unit: str
    direction: Literal["up", "down", "flat", "unknown"] = "unknown"
    context: str
    evidence_entry_ids: list[int] = Field(default_factory=list)
    confidence: float = 0.75


class Coverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_count: int
    date_count: int
    projects: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GenerationInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["deterministic", "llm", "fallback"]
    model: str | None = None
    fallback_reason: str | None = None


class WorkReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = WORK_REPORT_SCHEMA_VERSION
    report_type: Literal["day", "week", "month", "quarter", "year", "project"]
    period: ReportPeriod
    project: str | None = None
    source_entry_ids: list[int]
    executive_summary: str
    work_done: list[EvidenceItem] = Field(default_factory=list)
    outcomes: list[EvidenceItem] = Field(default_factory=list)
    kpis: list[KpiEvidence] = Field(default_factory=list)
    decisions: list[EvidenceItem] = Field(default_factory=list)
    blockers: list[EvidenceItem] = Field(default_factory=list)
    meetings: list[EvidenceItem] = Field(default_factory=list)
    next_actions: list[EvidenceItem] = Field(default_factory=list)
    risks: list[EvidenceItem] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    coverage: Coverage
    generation: GenerationInfo

    @classmethod
    def empty(
        cls,
        report_type: str,
        period: ReportPeriod | dict,
        project: str | None,
        source_entry_ids: list[int],
        fallback_reason: str | None = None,
    ) -> "WorkReport":
        return cls(
            report_type=report_type,
            period=period,
            project=project,
            source_entry_ids=source_entry_ids,
            executive_summary="기록이 없습니다.",
            coverage={
                "entry_count": len(source_entry_ids),
                "date_count": 0,
                "projects": [project] if project else [],
                "warnings": [],
            },
            generation={
                "mode": "fallback" if fallback_reason else "deterministic",
                "model": None,
                "fallback_reason": fallback_reason,
            },
        )


def render_report_markdown(report: WorkReport) -> str:
    lines = [
        f"# {report.period.label} 리포트",
        "",
        "## Executive Summary / 핵심 요약",
        report.executive_summary,
        "",
    ]
    _append_evidence(lines, "Work Done / 한 작업", report.work_done)
    _append_evidence(lines, "Outcomes / 성과", report.outcomes)
    _append_kpis(lines, report.kpis)
    _append_evidence(lines, "Project Progress / 프로젝트 진행", _project_progress(report))
    _append_evidence(lines, "Decisions / 결정", report.decisions)
    _append_evidence(lines, "Risks And Blockers / 리스크와 이슈/블로커", [*report.risks, *report.blockers])
    _append_evidence(lines, "Next Actions / 다음 액션", report.next_actions)
    lines.extend(["## Source Entries / 원본 기록", _source_line(report.source_entry_ids)])
    if report.coverage.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in report.coverage.warnings)
    return "\n".join(lines).strip()


def _append_evidence(lines: list[str], title: str, items: list[EvidenceItem]) -> None:
    lines.append(f"## {title}")
    if not items:
        lines.extend(["- 없음", ""])
        return
    for item in items:
        project = f" [{item.project}]" if item.project and not _title_has_project(item.title, item.project) else ""
        source = _source_line(item.evidence_entry_ids)
        if _same_text(item.title, item.description):
            lines.append(f"-{project} {item.description} ({source})")
        else:
            lines.append(f"-{project} {item.title} - {item.description} ({source})")
    lines.append("")


def _append_kpis(lines: list[str], kpis: list[KpiEvidence]) -> None:
    lines.append("## KPI Evidence / KPI 근거 / KPI 후보")
    if not kpis:
        lines.extend(["- 없음", ""])
        return
    for kpi in kpis:
        value = int(kpi.value) if float(kpi.value).is_integer() else kpi.value
        source = _source_line(kpi.evidence_entry_ids)
        lines.append(f"- {kpi.name}: {value}{kpi.unit} - {kpi.context} ({source})")
    lines.append("")


def _project_progress(report: WorkReport) -> list[EvidenceItem]:
    projects = report.coverage.projects
    progress: list[EvidenceItem] = []
    for project in projects:
        project_items = {
            "작업": [item for item in report.work_done if item.project == project],
            "성과": [item for item in report.outcomes if item.project == project],
            "결정": [item for item in report.decisions if item.project == project],
            "블로커": [item for item in report.blockers if item.project == project],
            "다음 액션": [item for item in report.next_actions if item.project == project],
        }
        counts = [f"{label} {len(items)}건" for label, items in project_items.items() if items]
        evidence_ids: list[int] = []
        for items in project_items.values():
            for item in items:
                evidence_ids.extend(item.evidence_entry_ids)
        if not counts:
            continue
        progress.append(
            EvidenceItem(
                title=project,
                description=", ".join(counts),
                project=project,
                evidence_entry_ids=_dedupe_ids(evidence_ids),
                confidence=0.75,
            )
        )
    return progress


def _source_line(ids: list[int]) -> str:
    if not ids:
        return "source: none"
    return "source: " + ", ".join(f"#{entry_id}" for entry_id in ids)


def _same_text(left: str, right: str) -> bool:
    return _normalize_text(left) == _normalize_text(right)


def _title_has_project(title: str, project: str) -> bool:
    return _normalize_text(title).startswith(_normalize_text(project))


def _normalize_text(value: str) -> str:
    return " ".join(value.rstrip(".!?").split()).casefold()


def _dedupe_ids(values: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
