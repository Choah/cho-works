from cho_works.services import EntryService, ProjectService, WorkItemService
from cho_works.db import connect


def test_project_service_creates_and_lists_jira_like_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    projects = ProjectService()

    project = projects.create_project(
        key="api",
        name="API 안정화",
        goal="장애를 줄이고 배포 신뢰도를 높인다",
        target_date="2026-06-30",
    )

    assert project.key == "API"
    assert project.status == "active"
    assert projects.list_projects()[0].name == "API 안정화"


def test_project_service_reuses_existing_project_aliases_and_merges_duplicates(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    projects = ProjectService()
    canonical = projects.create_project(key="API", name="API 안정화")
    duplicate = projects.create_project(key="API-안정화", name="API 안정화 프로젝트")
    WorkItemService().create_item(duplicate.id, "중복 프로젝트 작업", status="todo")

    updated = projects.create_project(key=" api 안정화 ", name="API 신뢰도 개선")
    rows = projects.list_projects()
    items = WorkItemService().list_items(project_key="API")

    assert updated.key == "API"
    assert [project.key for project in rows] == ["API"]
    assert rows[0].name == "API 신뢰도 개선"
    assert items[0].project_id == canonical.id


def test_project_service_merges_existing_duplicate_alias_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    canonical = ProjectService().create_project(key="API", name="API 안정화")
    with connect() as conn:
        cursor = conn.execute(
            """
            insert into projects(key, name, created_at, updated_at)
            values (?, ?, ?, ?)
            """,
            ("API-안정화", "API 안정화 프로젝트", "2026-05-08T10:00:00", "2026-05-08T10:00:00"),
        )
        duplicate_id = cursor.lastrowid
        conn.execute(
            """
            insert into work_items(
                project_id, key, title, item_type, status, priority,
                tags_json, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                duplicate_id,
                "API-안정화-1",
                "중복 프로젝트 작업",
                "task",
                "todo",
                "medium",
                "[]",
                "2026-05-08T10:00:00",
                "2026-05-08T10:00:00",
            ),
        )

    rows = ProjectService().list_projects()
    items = WorkItemService().list_items(project_key="API")

    assert [project.key for project in rows] == ["API"]
    assert [item.project_id for item in items] == [canonical.id]


def test_entry_creates_project_and_work_items_from_daily_log(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()

    entry = entries.add_entry(
        "2026-05-08",
        "API 프로젝트 오류 3건 수정 완료. 인증 장애로 배포 지연.",
        source="test",
    )
    items = WorkItemService().list_items(project_key="API")

    assert [item.key for item in items] == ["API-1", "API-2"]
    assert items[0].status == "done"
    assert items[1].status == "blocked"
    assert items[0].source_entry_id == entry.id


def test_general_work_entries_create_todo_items_with_source_date(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))

    EntryService().add_entry(
        "2026-05-08",
        "샘플, 화면 이미지 & 기능 정리. 일정표 스케줄 지금 작성하고 있어.",
        project="샘플-AGENT",
        source="test",
    )

    items = WorkItemService().list_items(project_key="샘플-AGENT")

    assert [item.status for item in items] == ["todo", "todo"]
    assert [item.item_type for item in items] == ["task", "task"]
    assert [item.source_work_date for item in items] == ["2026-05-08", "2026-05-08"]


def test_work_item_status_dates_and_title_can_be_updated(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    project = ProjectService().create_project(key="API", name="API 안정화")
    item = WorkItemService().create_item(project.id, "배포 체크리스트 작성", status="todo")

    updated = WorkItemService().update_item(
        item.id,
        title="배포 체크리스트 정리",
        status="in_progress",
        priority="high",
        item_type="task",
        due_date="2026-05-20",
        completed_at=None,
        description="배포 전 확인할 항목을 정리한다.",
    )

    assert updated.title == "배포 체크리스트 정리"
    assert updated.status == "in_progress"
    assert updated.priority == "high"
    assert updated.due_date == "2026-05-20"
    assert updated.completed_at is None


def test_multi_project_entry_creates_items_under_each_project(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()

    entries.add_entry(
        "2026-05-08",
        "A 프로젝트 API 오류 1건 수정 완료. B 프로젝트 문서 2건 정리 완료.",
        source="test",
    )

    a_items = WorkItemService().list_items(project_key="A")
    b_items = WorkItemService().list_items(project_key="B")

    assert [item.key for item in a_items] == ["A-1"]
    assert [item.key for item in b_items] == ["B-1"]
    assert "문서" in b_items[0].title


def test_project_list_backfills_legacy_entry_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    EntryService().add_entry(
        "2026-05-08",
        "레거시 프로젝트 업무 완료",
        project="LEGACY",
        source="test",
    )
    with connect() as conn:
        conn.execute("delete from work_items")
        conn.execute("delete from projects")

    projects = ProjectService().list_projects()

    assert [project.key for project in projects] == ["LEGACY"]


def test_work_item_board_groups_items_by_status(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    projects = ProjectService()
    project = projects.create_project(key="OPS", name="운영")
    items = WorkItemService()
    items.create_item(project.id, "배포 체크리스트 작성", status="todo")
    items.create_item(project.id, "장애 분석", status="blocked", priority="high")

    board = items.board()

    assert [item.title for item in board["todo"]] == ["배포 체크리스트 작성"]
    assert [item.title for item in board["blocked"]] == ["장애 분석"]
