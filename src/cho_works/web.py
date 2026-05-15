from __future__ import annotations

import re
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date as date_type
from datetime import timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

import typer
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cho_works.config import current_date_iso
from cho_works.db import connect
from cho_works.models import WorkEntry
from cho_works.periods import parse_date, period_range
from cho_works.services import (
    CompetencyReviewService,
    EntryService,
    PetService,
    ProjectService,
    ReminderService,
    SummaryPromptService,
    SummaryService,
    WorkItemService,
    initialize_workspace,
    refine_daily_work_text,
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["refine_work"] = refine_daily_work_text
web_cli = typer.Typer(help="Run Cho Works local web app.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_workspace()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Cho Works", lifespan=lifespan)
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )

    @app.get("/")
    def index(request: Request, recent_page: int = 1):
        today = current_date_iso()
        entry_service = EntryService()
        recent_per_page = 5
        recent_page = max(1, recent_page)
        recent_total = entry_service.count_entries()
        recent_total_pages = max(1, (recent_total + recent_per_page - 1) // recent_per_page)
        recent_page = min(recent_page, recent_total_pages)
        recent_offset = (recent_page - 1) * recent_per_page
        entry_cards = entry_service.recent_entry_cards(limit=recent_per_page, offset=recent_offset)
        pet = PetService().refresh(today=today)
        due = ReminderService().due()
        projects = ProjectService().list_projects()
        board = WorkItemService().board()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": "Cho Works",
                "today": today,
                "entry_cards": entry_cards,
                "recent_pagination": {
                    "page": recent_page,
                    "total_pages": recent_total_pages,
                    "pages": range(1, recent_total_pages + 1),
                },
                "pet": pet,
                "due_reminders": due,
                "projects": projects,
                "board": board,
                "status_labels": STATUS_LABELS,
                "type_labels": ITEM_TYPE_LABELS,
                "priorities": ["low", "medium", "high"],
            },
        )

    @app.post("/entries")
    def create_entry(
        work_date: Annotated[str, Form()],
        raw_text: Annotated[str, Form()],
        project: Annotated[str | None, Form()] = None,
        status: Annotated[str | None, Form()] = None,
        priority: Annotated[str | None, Form()] = None,
        item_type: Annotated[str | None, Form()] = None,
        completed_at: Annotated[str | None, Form()] = None,
    ):
        try:
            entry = EntryService().add_entry(work_date, raw_text, project=project or None, source="web")
            _apply_entry_work_item_fields(
                entry.id,
                status=status,
                priority=priority,
                item_type=item_type,
                completed_at=completed_at,
            )
        except ValueError as exc:
            return _bad_request(str(exc))
        return RedirectResponse("/", status_code=303)

    @app.get("/entries/{entry_id}/edit")
    def edit_entry(request: Request, entry_id: int):
        entry = EntryService().get_entry(entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
        work_items = WorkItemService().list_items_for_entry(entry_id)
        primary_item = work_items[0] if work_items else None
        return templates.TemplateResponse(
            request,
            "entry_edit.html",
            {
                "title": "기록 수정",
                "entry": entry,
                "projects": ProjectService().list_projects(),
                "work_items": work_items,
                "primary_item": primary_item,
                "status_labels": STATUS_LABELS,
                "type_labels": ITEM_TYPE_LABELS,
                "priorities": ["low", "medium", "high"],
            },
        )

    @app.post("/entries/{entry_id}")
    def update_entry(
        entry_id: int,
        work_date: Annotated[str, Form()],
        raw_text: Annotated[str, Form()],
        project: Annotated[str | None, Form()] = None,
        status: Annotated[str | None, Form()] = None,
        priority: Annotated[str | None, Form()] = None,
        item_type: Annotated[str | None, Form()] = None,
        completed_at: Annotated[str | None, Form()] = None,
    ):
        try:
            entry = EntryService().update_entry(entry_id, work_date, raw_text, project=project or None)
            _apply_entry_work_item_fields(
                entry.id,
                status=status,
                priority=priority,
                item_type=item_type,
                completed_at=completed_at,
            )
        except ValueError as exc:
            return _bad_request(str(exc))
        return RedirectResponse("/entries", status_code=303)

    @app.get("/entries")
    def entries(request: Request):
        entry_rows = EntryService().list_entries(limit=100)
        return templates.TemplateResponse(
            request,
            "entries.html",
            {
                "title": "기록",
                "entries": entry_rows,
                "entry_work_items": WorkItemService().items_by_entry_ids([entry.id for entry in entry_rows]),
                "status_labels": STATUS_LABELS,
                "type_labels": ITEM_TYPE_LABELS,
            },
        )

    @app.get("/search")
    def search(request: Request, q: str = ""):
        entries = EntryService().search(q) if q else []
        return templates.TemplateResponse(
            request,
            "entries.html",
            {
                "title": f"검색: {q}" if q else "검색",
                "entries": entries,
                "query": q,
                "entry_work_items": WorkItemService().items_by_entry_ids([entry.id for entry in entries]),
                "status_labels": STATUS_LABELS,
                "type_labels": ITEM_TYPE_LABELS,
            },
        )

    @app.get("/summary/{period}")
    def summary(
        request: Request,
        period: str,
        date: str | None = None,
        project: str | None = None,
        refresh: bool = False,
    ):
        target = project if period == "project" else date
        summary_service = SummaryService()
        try:
            result = summary_service.generate(period, target) if refresh else summary_service.get_or_generate(period, target)
            source_entries = summary_service.entries_by_ids(result.source_entry_ids)
        except ValueError as exc:
            return _bad_request(str(exc))
        report_sections = _report_sections(result.body)
        return templates.TemplateResponse(
            request,
            "summary.html",
            {
                "title": result.title,
                "summary": result,
                "source_entries": source_entries,
                "report_sections": report_sections,
                "report_metrics": _report_metrics(source_entries, report_sections),
                "summary_nav": _summary_period_nav(period, date),
                "edit_url": _summary_edit_url(period, date=date, project=project),
                "refresh_url": _summary_url(period, date=date, project=project, refresh=True),
            },
        )

    @app.get("/summary/{period}/edit")
    def edit_summary(request: Request, period: str, date: str | None = None, project: str | None = None):
        target = project if period == "project" else date
        try:
            result = SummaryService().get_or_generate(period, target)
        except ValueError as exc:
            return _bad_request(str(exc))
        return templates.TemplateResponse(
            request,
            "summary_edit.html",
            {
                "title": "보고서 수정",
                "period": period,
                "summary": result,
                "return_url": _summary_url(period, date=date, project=project),
            },
        )

    @app.post("/summary/{period}/edit")
    def update_summary(
        period: str,
        period_key: Annotated[str, Form()],
        title: Annotated[str, Form()],
        body: Annotated[str, Form()],
        return_url: Annotated[str | None, Form()] = None,
    ):
        try:
            SummaryService().update_summary(period, period_key, title, body)
        except ValueError as exc:
            return _bad_request(str(exc))
        return RedirectResponse(return_url or f"/summary/{period}", status_code=303)

    @app.get("/prompts")
    def prompts(request: Request):
        return templates.TemplateResponse(
            request,
            "prompts.html",
            {
                "title": "요약 프롬프트",
                "prompts": SummaryPromptService().list_prompts(),
            },
        )

    @app.post("/prompts/{period_type}")
    def update_prompt(period_type: str, prompt_text: Annotated[str, Form()]):
        try:
            SummaryPromptService().set_prompt(period_type, prompt_text)
        except ValueError as exc:
            return _bad_request(str(exc))
        return RedirectResponse("/prompts", status_code=303)

    @app.get("/reminders")
    def reminders(request: Request):
        due = ReminderService().due()
        return templates.TemplateResponse(
            request,
            "reminders.html",
            {
                "title": "알림",
                "due_reminders": due,
            },
        )

    @app.post("/reminders")
    def set_reminder(
        reminder_type: Annotated[str, Form()],
        time_local: Annotated[str, Form()],
        enabled: Annotated[bool, Form()] = True,
    ):
        ReminderService().set_config(reminder_type, time_local, enabled=enabled)
        return RedirectResponse("/reminders", status_code=303)

    @app.get("/competency")
    def competency(request: Request, month: str | None = None):
        service = CompetencyReviewService()
        try:
            selected_month = service.normalize_month(month)
        except ValueError as exc:
            return _bad_request(str(exc))
        return templates.TemplateResponse(
            request,
            "competency.html",
            {
                "title": "역량 평가",
                "selected_month": selected_month,
                "review": service.get_month(selected_month),
                "summaries": [
                    {"label": "월간", "summary": service.summarize("month", selected_month)},
                    {"label": "분기", "summary": service.summarize("quarter", selected_month)},
                    {"label": "연간", "summary": service.summarize("year", selected_month)},
                ],
                "prev_month_url": f"/competency?month={_shift_month(selected_month, -1)}",
                "next_month_url": f"/competency?month={_shift_month(selected_month, 1)}",
            },
        )

    @app.post("/competency")
    def update_competency(
        month_key: Annotated[str, Form()],
        work_problem_solving: Annotated[str | None, Form()] = None,
        work_efficiency: Annotated[str | None, Form()] = None,
        work_expertise: Annotated[str | None, Form()] = None,
        people_communication: Annotated[str | None, Form()] = None,
        people_collaboration: Annotated[str | None, Form()] = None,
        people_trust: Annotated[str | None, Form()] = None,
    ):
        try:
            review = CompetencyReviewService().upsert_month(
                month_key=month_key,
                work_problem_solving=work_problem_solving,
                work_efficiency=work_efficiency,
                work_expertise=work_expertise,
                people_communication=people_communication,
                people_collaboration=people_collaboration,
                people_trust=people_trust,
            )
        except ValueError as exc:
            return _bad_request(str(exc))
        return RedirectResponse(f"/competency?month={review.month_key}", status_code=303)

    @app.get("/projects")
    def projects(request: Request):
        project_rows = ProjectService().list_projects()
        entry_service = EntryService()
        work_items = WorkItemService()
        project_cards = []
        for project in project_rows:
            entries = entry_service.list_entries(project=project.key, limit=500)
            items = work_items.list_items(project_key=project.key, limit=500)
            project_cards.append(
                {
                    "project": project,
                    "entry_count": len(entries),
                    "item_count": len(items),
                    "last_date": entries[0].work_date if entries else None,
                }
            )
        return templates.TemplateResponse(
            request,
            "projects.html",
            {
                "title": "프로젝트",
                "projects": project_rows,
                "project_cards": project_cards,
            },
        )

    @app.post("/projects")
    def create_project(
        key: Annotated[str, Form()],
        name: Annotated[str, Form()],
        summary: Annotated[str | None, Form()] = None,
        goal: Annotated[str | None, Form()] = None,
        work_content: Annotated[str | None, Form()] = None,
        target_users: Annotated[str | None, Form()] = None,
        core_features: Annotated[str | None, Form()] = None,
        additional_features: Annotated[str | None, Form()] = None,
        execution_stage: Annotated[str | None, Form()] = None,
        qualitative_effect: Annotated[str | None, Form()] = None,
        quantitative_effect: Annotated[str | None, Form()] = None,
        deliverables: Annotated[str | None, Form()] = None,
        target_date: Annotated[str | None, Form()] = None,
        return_to: Annotated[str | None, Form()] = None,
    ):
        ProjectService().create_project(
            key=key,
            name=name,
            summary=summary or None,
            goal=goal or None,
            work_content=work_content or None,
            target_users=target_users or None,
            core_features=core_features or None,
            additional_features=additional_features or None,
            execution_stage=execution_stage or None,
            qualitative_effect=qualitative_effect or None,
            quantitative_effect=quantitative_effect or None,
            deliverables=deliverables or None,
            target_date=target_date or None,
        )
        return RedirectResponse(return_to or "/projects", status_code=303)

    @app.get("/projects/{project_key}")
    def project_detail(request: Request, project_key: str):
        project_service = ProjectService()
        project = project_service.get_by_key(project_key)
        if not project:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
        entries = EntryService().list_entries(project=project.key, limit=300)
        grouped_entries: dict[str, list] = {}
        for entry in entries:
            grouped_entries.setdefault(entry.work_date, []).append(entry)
        items = WorkItemService().list_items(project_key=project.key, limit=200)
        entry_work_items = WorkItemService().items_by_entry_ids([entry.id for entry in entries])
        return templates.TemplateResponse(
            request,
            "project_detail.html",
            {
                "title": project.name,
                "project": project,
                "entry_groups": grouped_entries.items(),
                "entry_work_items": entry_work_items,
                "items": items,
                "status_labels": STATUS_LABELS,
                "type_labels": ITEM_TYPE_LABELS,
            },
        )

    @app.get("/board")
    def board(request: Request):
        return templates.TemplateResponse(
            request,
            "board.html",
            {
                "title": "보드",
                "board": WorkItemService().board(),
                "status_labels": {
                    "todo": "예정",
                    "in_progress": "진행중",
                    "blocked": "막힘",
                    "review": "검토",
                    "done": "완료",
                    "dropped": "보류",
                },
                "type_labels": ITEM_TYPE_LABELS,
            },
        )

    @app.get("/work-items/{item_id}/edit")
    def edit_work_item(request: Request, item_id: int):
        item = WorkItemService().get_item(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="업무 카드를 찾을 수 없습니다.")
        return templates.TemplateResponse(
            request,
            "work_item_edit.html",
            {
                "title": "업무 카드 수정",
                "item": item,
                "status_labels": STATUS_LABELS,
                "type_labels": ITEM_TYPE_LABELS,
                "priorities": ["low", "medium", "high"],
            },
        )

    @app.post("/work-items/{item_id}")
    def update_work_item(
        item_id: int,
        title: Annotated[str, Form()],
        description: Annotated[str | None, Form()] = None,
        status: Annotated[str, Form()] = "todo",
        priority: Annotated[str, Form()] = "medium",
        item_type: Annotated[str, Form()] = "task",
        due_date: Annotated[str | None, Form()] = None,
        completed_at: Annotated[str | None, Form()] = None,
        return_to: Annotated[str | None, Form()] = None,
    ):
        try:
            WorkItemService().update_item(
                item_id,
                title=title,
                status=status,
                priority=priority,
                item_type=item_type,
                due_date=due_date,
                completed_at=completed_at,
                description=description,
            )
        except ValueError as exc:
            return _bad_request(str(exc))
        return RedirectResponse(_safe_return_to(return_to) or "/board", status_code=303)

    return app


def _bad_request(message: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang=\"ko\"><body><h1>오류</h1><p>{message}</p></body></html>",
        status_code=400,
    )


def _safe_return_to(return_to: str | None) -> str | None:
    if not return_to:
        return None
    if return_to.startswith("/") and not return_to.startswith("//") and "\n" not in return_to and "\r" not in return_to:
        return return_to
    return None


def _apply_entry_work_item_fields(
    entry_id: int,
    status: str | None = None,
    priority: str | None = None,
    item_type: str | None = None,
    completed_at: str | None = None,
) -> None:
    if status is None and priority is None and item_type is None and completed_at is None:
        return
    service = WorkItemService()
    for item in service.list_items_for_entry(entry_id):
        service.update_item(
            item.id,
            title=item.title,
            description=item.description,
            status=status or item.status,
            priority=priority or item.priority,
            item_type=item_type or item.item_type,
            completed_at=completed_at if completed_at is not None else item.completed_at,
        )


REPORT_HEADINGS = {
    "핵심 요약",
    "한 작업",
    "성과",
    "성과 근거",
    "프로젝트 진행",
    "결정",
    "리스크와 이슈/블로커",
    "다음 액션",
    "Warnings",
}

ITEM_TYPE_LABELS = {
    "outcome": "완료 작업",
    "decision": "결정",
    "meeting": "회의/논의",
    "task": "업무",
    "blocker": "이슈/블로커",
}

STATUS_LABELS = {
    "todo": "할 일",
    "in_progress": "진행 중",
    "blocked": "막힘",
    "review": "검토",
    "done": "완료",
    "dropped": "보류",
}


def _summary_url(
    period: str,
    date: str | None = None,
    project: str | None = None,
    refresh: bool = False,
) -> str:
    params = {}
    if period == "project" and project:
        params["project"] = project
    elif date:
        params["date"] = date
    if refresh:
        params["refresh"] = "1"
    suffix = f"?{urlencode(params)}" if params else ""
    return f"/summary/{period}{suffix}"


def _summary_edit_url(period: str, date: str | None = None, project: str | None = None) -> str:
    params = {}
    if period == "project" and project:
        params["project"] = project
    elif date:
        params["date"] = date
    suffix = f"?{urlencode(params)}" if params else ""
    return f"/summary/{period}/edit{suffix}"


def _summary_period_nav(period: str, anchor_value: str | None = None) -> dict | None:
    if period == "project":
        return None
    anchor = parse_date(anchor_value or current_date_iso())
    start, end = period_range(period, anchor)
    prev_start, _ = period_range(period, start - timedelta(days=1))
    next_start, _ = period_range(period, end + timedelta(days=1))
    prev_label, next_label = {
        "day": ("전날", "다음날"),
        "week": ("전주", "다음주"),
        "month": ("전월", "다음월"),
        "quarter": ("전분기", "다음분기"),
        "year": ("전년", "다음년"),
    }[period]
    return {
        "prev_label": prev_label,
        "next_label": next_label,
        "prev_url": _summary_url(period, date=prev_start.isoformat()),
        "next_url": _summary_url(period, date=next_start.isoformat()),
        "range_label": _summary_range_label(start, end),
    }


def _summary_range_label(start: date_type, end: date_type) -> str:
    if start == end:
        return start.strftime("%Y.%m.%d")
    if start.year == end.year:
        return f"{start.year}.{start.month:02d}.{start.day:02d}-{end.month:02d}.{end.day:02d}"
    return f"{start.strftime('%Y.%m.%d')}-{end.strftime('%Y.%m.%d')}"


def _shift_month(month_key: str, months: int) -> str:
    anchor = parse_date(f"{month_key}-01")
    month_index = anchor.year * 12 + (anchor.month - 1) + months
    year, month_zero = divmod(month_index, 12)
    return f"{year}-{month_zero + 1:02d}"


def _report_sections(body: str) -> list[dict]:
    sections: list[dict] = []
    current: dict | None = None
    for line in body.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("source:"):
            continue
        if text.startswith("#"):
            title = _clean_report_heading(text)
            if title.endswith("리포트") or title == "원본 기록":
                current = None
                continue
            current = {"title": title, "paragraphs": [], "item_rows": []}
            sections.append(current)
            continue
        title = _clean_report_heading(text)
        if title in REPORT_HEADINGS:
            current = {"title": title, "paragraphs": [], "item_rows": []}
            sections.append(current)
            continue
        if current is None:
            current = {"title": "핵심 요약", "paragraphs": [], "item_rows": []}
            sections.append(current)
        if text.startswith(("-", "*", "·")):
            item = _clean_report_item(text)
            if item:
                current["item_rows"].append(_report_item_row(current["title"], item))
        else:
            current["paragraphs"].append(_clean_report_item(text))
    return [
        section
        for section in sections
        if section["paragraphs"] or [item for item in section["item_rows"] if _report_item_text(item) != "없음"]
    ]


def _clean_report_heading(value: str) -> str:
    title = value.lstrip("#").strip()
    if "/" in title:
        title = title.split("/")[-1].strip()
    aliases = {
        "Executive Summary": "핵심 요약",
        "Work Done": "한 작업",
        "Outcomes": "성과",
        "완료/성과": "성과",
        "KPI Evidence": "성과 근거",
        "KPI 근거": "성과 근거",
        "KPI 후보": "성과 근거",
        "Project Progress": "프로젝트 진행",
        "Decisions": "결정",
        "Risks And Blockers": "리스크와 이슈/블로커",
        "Next Actions": "다음 액션",
        "Source Entries": "원본 기록",
    }
    return aliases.get(title, title)


def _clean_report_item(value: str) -> str:
    text = value.strip()
    while text.startswith(("-", "*", "·")):
        text = text[1:].strip()
    return re.sub(r"\s*\(source: [^)]+\)\s*$", "", text).strip()


def _report_item_row(section_title: str, text: str) -> dict:
    if section_title == "성과":
        outcome = _structured_outcome_item(text)
        if outcome:
            return outcome
    return {"text": text}


def _structured_outcome_item(text: str) -> dict | None:
    match = re.match(
        r"^(?P<title>.+?)\s+-\s+(?P<summary>작업\s+\d+건[^.]*\.)\s+근거 작업은\s+(?P<details>.+?)\.?$",
        text,
    )
    if not match:
        return None
    raw_details = match.group("details").strip()
    continued = raw_details.endswith(" 등")
    if continued:
        raw_details = raw_details[:-2].strip()
    details = [part.strip() for part in raw_details.split(" / ") if part.strip()]
    return {
        "title": match.group("title").strip(),
        "summary": match.group("summary").strip(),
        "details": details,
        "continued": continued,
    }


def _report_item_text(item) -> str:
    if isinstance(item, dict):
        return item.get("text") or item.get("title") or ""
    return str(item)


def _report_metrics(entries: list[WorkEntry], report_sections: list[dict] | None = None) -> dict:
    entry_ids = [entry.id for entry in entries]
    date_count = len({entry.work_date for entry in entries})
    projects = sorted({entry.project for entry in entries if entry.project})
    item_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    project_counts: Counter[str] = Counter(entry.project for entry in entries if entry.project)
    kpi_count = 0
    if entry_ids:
        placeholders = ",".join("?" for _ in entry_ids)
        with connect() as conn:
            item_rows = conn.execute(
                f"""
                select item_type, project
                from entry_items
                where entry_id in ({placeholders})
                """,
                entry_ids,
            ).fetchall()
            work_rows = conn.execute(
                f"""
                select status
                from work_items
                where source_entry_id in ({placeholders})
                """,
                entry_ids,
            ).fetchall()
            kpi_count = conn.execute(
                f"""
                select count(*) as count
                from kpi_observations
                where entry_id in ({placeholders})
                """,
                entry_ids,
            ).fetchone()["count"]
        item_counts.update(row["item_type"] for row in item_rows)
        project_counts.update(row["project"] for row in item_rows if row["project"])
        status_counts.update(row["status"] for row in work_rows)
    outcome_count = _report_section_item_count(report_sections, "성과")
    cards = [
        {"label": "기록", "value": f"{len(entries)}건"},
        {"label": "작업일", "value": f"{date_count}일"},
        {"label": "프로젝트", "value": f"{len(projects)}개"},
    ]
    if outcome_count:
        cards.append({"label": "성과", "value": f"{outcome_count}건"})
    cards.append({"label": "성과 근거", "value": f"{kpi_count}건"})
    return {
        "cards": cards,
        "project_counts": _counter_rows(project_counts),
        "item_counts": _counter_rows(item_counts, ITEM_TYPE_LABELS),
        "status_counts": _counter_rows(status_counts, STATUS_LABELS),
    }


def _report_section_item_count(report_sections: list[dict] | None, title: str) -> int:
    if not report_sections:
        return 0
    for section in report_sections:
        if section["title"] != title:
            continue
        return len(section["paragraphs"]) + len(
            [item for item in section["item_rows"] if _report_item_text(item) != "없음"]
        )
    return 0


def _counter_rows(counter: Counter[str], labels: dict[str, str] | None = None) -> list[dict]:
    total = sum(counter.values()) or 1
    return [
        {"label": (labels or {}).get(key, key), "count": count, "percent": round(count / total * 100)}
        for key, count in counter.most_common()
        if key
    ]


@web_cli.callback(invoke_without_command=True)
def run(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8787,
) -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)


def main() -> None:
    web_cli()
