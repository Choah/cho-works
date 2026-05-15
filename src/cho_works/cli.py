from __future__ import annotations

from typing import Annotated

import typer

from cho_works.config import current_date_iso
from cho_works.services import (
    EntryService,
    PetService,
    ProjectService,
    ReminderService,
    SummaryService,
    WorkItemService,
    initialize_workspace,
)

app = typer.Typer(help="Cho Works personal work-log assistant.")
project_app = typer.Typer(help="프로젝트를 관리합니다.")
item_app = typer.Typer(help="업무 아이템을 관리합니다.")
app.add_typer(project_app, name="project")
app.add_typer(item_app, name="item")


@app.command()
def init() -> None:
    db_path = initialize_workspace()
    typer.echo("Cho Works 준비 완료")
    typer.echo(f"SQLite DB: {db_path}")


@app.command()
def add(
    text: Annotated[str, typer.Argument(help="업무 기록 원문")],
    work_date: Annotated[
        str | None,
        typer.Option("--date", "-d", help="기록 날짜 YYYY-MM-DD"),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="대표 프로젝트명"),
    ] = None,
) -> None:
    target_date = work_date or current_date_iso()
    try:
        entry = EntryService().add_entry(target_date, text, project=project, source="cli")
    except ValueError as exc:
        _exit_with_error(str(exc))
        return
    typer.echo(f"기록 저장 완료: #{entry.id} {entry.work_date}")


@app.command("list")
def list_entries(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    project: Annotated[str | None, typer.Option("--project", "-p")] = None,
) -> None:
    entries = EntryService().list_entries(project=project, limit=limit)
    if not entries:
        typer.echo("기록이 없습니다.")
        return
    for entry in entries:
        prefix = f"{entry.work_date}"
        if entry.project:
            prefix += f" [{entry.project}]"
        typer.echo(f"{prefix} #{entry.id} {entry.raw_text}")


@app.command()
def search(query: Annotated[str, typer.Argument(help="검색어")]) -> None:
    entries = EntryService().search(query)
    if not entries:
        typer.echo("검색 결과가 없습니다.")
        return
    for entry in entries:
        project = f" [{entry.project}]" if entry.project else ""
        typer.echo(f"{entry.work_date}{project} #{entry.id} {entry.raw_text}")


@app.command()
def summary(
    period: Annotated[
        str,
        typer.Argument(help="day, week, month, quarter, year, project"),
    ],
    target_date: Annotated[
        str | None,
        typer.Option("--date", "-d", help="기준 날짜 YYYY-MM-DD"),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="프로젝트 요약 대상"),
    ] = None,
) -> None:
    target = project if period == "project" else target_date
    try:
        result = SummaryService().generate(period, target)
    except ValueError as exc:
        _exit_with_error(str(exc))
        return
    typer.echo(result.title)
    typer.echo(result.body)


@app.command()
def projects() -> None:
    project_rows = ProjectService().list_projects()
    if not project_rows:
        typer.echo("프로젝트가 없습니다.")
        return
    for project in project_rows:
        typer.echo(f"{project.key} {project.name} · {project.status} · {project.health}")


@project_app.command("add")
def project_add(
    key: Annotated[str, typer.Argument(help="프로젝트 키 예: API")],
    name: Annotated[str, typer.Argument(help="프로젝트 이름")],
    goal: Annotated[str | None, typer.Option("--goal", help="성과 목표")] = None,
    target_date: Annotated[str | None, typer.Option("--target-date")] = None,
) -> None:
    project = ProjectService().create_project(
        key=key,
        name=name,
        goal=goal,
        target_date=target_date,
    )
    typer.echo(f"프로젝트 저장: {project.key} {project.name}")


@project_app.command("list")
def project_list() -> None:
    projects()


@item_app.command("list")
def item_list(
    project: Annotated[str | None, typer.Option("--project", "-p")] = None,
    status: Annotated[str | None, typer.Option("--status", "-s")] = None,
) -> None:
    items = WorkItemService().list_items(project_key=project, status=status)
    if not items:
        typer.echo("업무 아이템이 없습니다.")
        return
    for item in items:
        typer.echo(f"{item.key} [{item.status}] {item.title}")


@app.command()
def reminders(
    reminder_type: Annotated[
        str | None,
        typer.Option("--type", "-t", help="morning_plan, afternoon_check, end_of_day"),
    ] = None,
    time_local: Annotated[
        str | None,
        typer.Option("--time", help="로컬 시간 HH:MM"),
    ] = None,
    enabled: Annotated[bool, typer.Option("--enabled/--disabled")] = True,
) -> None:
    service = ReminderService()
    if reminder_type and time_local:
        try:
            service.set_config(reminder_type, time_local, enabled=enabled)
        except ValueError:
            _exit_with_error("알림 시간은 HH:MM 형식이어야 합니다.")
            return
        typer.echo(f"알림 설정 저장: {reminder_type} {time_local}")
        return
    due = service.deliver_due()
    if not due:
        typer.echo("지금 처리할 알림이 없습니다.")
        return
    for reminder in due:
        typer.echo(f"{reminder.scheduled_for} {reminder.message}")


@app.command()
def pet() -> None:
    state = PetService().refresh()
    typer.echo(f"펫 상태: {state.mood}")
    typer.echo(f"연속 기록: {state.streak_days}일")
    typer.echo(f"케어 포인트: {state.care_points}")
    typer.echo(state.message)


@app.command()
def refresh() -> None:
    EntryService().refresh_derived_items()
    typer.echo("파생 데이터 재정리 완료")


@app.command()
def web(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8787,
) -> None:
    import uvicorn

    uvicorn.run("cho_works.web:create_app", factory=True, host=host, port=port)


def main() -> None:
    app()


def _exit_with_error(message: str) -> None:
    typer.echo(f"오류: {message}")
    raise typer.Exit(1)
