from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedItem:
    item_type: str
    content: str
    project: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedKpi:
    name: str
    value: float
    unit: str
    confidence: float = 0.75


@dataclass(frozen=True)
class ParsedEntry:
    items: list[ParsedItem]
    kpis: list[ParsedKpi]
    tags: list[str]
    projects: list[str]


@dataclass(frozen=True)
class WorkEntry:
    id: int
    work_date: str
    raw_text: str
    refined_text: str | None
    project: str | None
    source: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Project:
    id: int
    key: str
    name: str
    status: str
    summary: str | None
    goal: str | None
    work_content: str | None
    target_users: str | None
    core_features: str | None
    additional_features: str | None
    execution_stage: str | None
    qualitative_effect: str | None
    quantitative_effect: str | None
    deliverables: str | None
    owner: str | None
    color: str
    start_date: str | None
    target_date: str | None
    health: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class WorkItem:
    id: int
    project_id: int
    key: str
    title: str
    description: str | None
    item_type: str
    status: str
    priority: str
    outcome: str | None
    impact: str | None
    due_date: str | None
    completed_at: str | None
    source_entry_id: int | None
    source_entry_item_id: int | None
    created_at: str
    updated_at: str
    source_work_date: str | None = None


@dataclass(frozen=True)
class Summary:
    period_type: str
    period_key: str
    title: str
    body: str
    source_entry_ids: list[int]


@dataclass(frozen=True)
class CompetencyReview:
    id: int
    month_key: str
    work_problem_solving: str | None
    work_efficiency: str | None
    work_expertise: str | None
    people_communication: str | None
    people_collaboration: str | None
    people_trust: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DueReminder:
    reminder_type: str
    scheduled_for: str
    message: str


@dataclass(frozen=True)
class PetState:
    streak_days: int
    care_points: int
    mood: str
    message: str
    unlocked_items: list[str]
