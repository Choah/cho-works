import re

from fastapi.testclient import TestClient

from cho_works.db import connect
from cho_works.services import EntryService, ProjectService, SummaryPromptService, WorkItemService
from cho_works.web import create_app


class FakeDailyRefiner:
    def refine(self, raw_text: str) -> str:
        return "LLM 정리 결과"


def test_web_startup_creates_database(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh" / "cho.sqlite3"
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(db_path))

    with TestClient(create_app()):
        pass

    assert db_path.exists()


def test_web_dashboard_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Cho Works" in response.text
    assert "parrot" in response.text
    assert "/static/img/parrot-companion.png" in response.text
    assert 'rel="icon"' in response.text
    assert "/static/img/parrot-icon-32.png" in response.text
    assert "/static/img/parrot-icon-180.png" in response.text
    assert "/static/img/parrot-icon-192.png" in response.text
    assert 'list="project-options"' in response.text
    assert 'name="status"' in response.text
    assert 'name="priority"' in response.text
    assert 'name="completed_at"' in response.text
    assert 'data-open-date-picker="true"' in response.text
    assert 'id="nav-links"' in response.text
    assert 'draggable="true"' in response.text
    assert "choWorksNavOrder" in response.text
    assert 'data-side-dock-target="true"' in response.text
    assert 'data-side-panel-close="true"' in response.text
    assert 'id="side-panel-frame"' in response.text
    assert "choWorksSidePanel" in response.text
    assert "side-panel-open" in response.text
    assert "nav-dragging" in response.text
    assert "옆 창으로 열기" in response.text
    assert "메뉴 분리" not in response.text
    assert "합치기" not in response.text
    assert '<a class="brand-trigger" href="/" data-easter-egg-trigger="true">' in response.text
    assert 'aria-label="Cho Works"' not in response.text
    assert 'title="Cho Works"' not in response.text
    assert 'id="easter-egg-modal"' in response.text
    assert "choWorksEasterEgg" in response.text
    assert "비밀 응원 모드" in response.text
    assert "11번" in response.text


def test_embedded_view_hides_navigation_for_side_panel(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    response = client.get("/?embedded=1")

    assert response.status_code == 200
    assert '<body class="embedded">' in response.text


def test_web_can_create_entry_and_render_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    response = client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "웹에서 회고 1건 작성 완료",
            "project": "웹",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    summary = client.get("/summary/day?date=2026-05-08")
    assert summary.status_code == 200
    assert "보고서 개요" in summary.text
    assert "정리된 리포트" in summary.text
    assert "원본 일별 기록" not in summary.text
    assert "summary-source-table" not in summary.text
    assert "<pre>" not in summary.text


def test_web_can_create_entry_with_work_card_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    response = client.post(
        "/entries",
        data={
            "work_date": "2026-05-12",
            "raw_text": "WBS 스케줄 작성",
            "project": "기금심사-AGENT",
            "status": "done",
            "priority": "high",
            "item_type": "task",
            "completed_at": "2026-05-12",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    item = WorkItemService().list_items(project_key="기금심사-AGENT")[0]
    assert item.title == "WBS 스케줄 작성"
    assert item.status == "done"
    assert item.priority == "high"
    assert item.item_type == "task"
    assert item.completed_at == "2026-05-12"


def test_summary_source_table_lists_daily_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    client.post(
        "/entries",
        data={
            "work_date": "2026-05-07",
            "raw_text": "API 점검 완료",
            "project": "API",
        },
    )
    client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "샘플 일정표 스케줄 정리",
            "project": "샘플",
        },
    )

    summary = client.get("/summary/week?date=2026-05-08")

    assert summary.status_code == 200
    assert "처리량" in summary.text
    assert "기록 2건" in summary.text
    assert "작업일 2일" in summary.text
    assert "프로젝트 2개" in summary.text
    assert "원본 일별 기록" not in summary.text
    assert "summary-source-table" not in summary.text


def test_web_preserves_multiline_work_text_in_storage_and_views(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    raw_text = "-샘플, 화면 이미지\n- 기능 정리\n-일정표 스케줄"

    response = client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": raw_text,
            "project": "샘플",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert EntryService().list_entries()[0].raw_text == raw_text

    dashboard = client.get("/")
    entries = client.get("/entries")
    project = client.get("/projects/샘플")

    assert "white-space: pre-wrap" in dashboard.text
    assert "샘플, 화면 이미지." in entries.text
    assert "기능 정리." in project.text
    assert '<details class="raw-original">' in entries.text
    assert '<details class="raw-original">' in project.text
    assert f'class="raw-text">{raw_text}' in dashboard.text
    assert f'class="raw-text">{raw_text}' in entries.text
    assert f'class="raw-text">{raw_text}' in project.text


def test_dashboard_shows_refined_daily_work_text(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    EntryService().add_entry(
        "2026-05-08",
        "-샘플, 화면 이미지 & 기능 정리\n-일정표 스케줄 지금 작성하고 있어",
        project="샘플-Agent",
        source="test",
    )

    dashboard = client.get("/")

    assert dashboard.status_code == 200
    assert "정리된 업무" in dashboard.text
    assert "샘플, 화면 이미지 및 기능 정리." in dashboard.text
    assert "일정표 스케줄 작성." in dashboard.text
    assert '<details class="raw-original">' in dashboard.text
    assert "<summary>원본</summary>" in dashboard.text


def test_dashboard_recent_records_are_paginated_in_groups_of_five(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    for day in range(1, 13):
        EntryService().add_entry(
            f"2026-05-{day:02d}",
            f"pagination-entry-{day:02d}",
            project="샘플",
            source="test",
        )

    first_page = client.get("/")

    assert first_page.status_code == 200
    for day in range(8, 13):
        assert f"pagination-entry-{day:02d}" in first_page.text
    assert "pagination-entry-07" not in first_page.text
    assert 'href="/?recent_page=2"' in first_page.text
    assert 'href="/?recent_page=3"' in first_page.text
    assert re.search(r'href="/\?recent_page=1"\s+aria-current="page"\s+>1</a>', first_page.text)

    second_page = client.get("/?recent_page=2")

    assert second_page.status_code == 200
    for day in range(3, 8):
        assert f"pagination-entry-{day:02d}" in second_page.text
    assert "pagination-entry-08" not in second_page.text
    assert "pagination-entry-02" not in second_page.text
    assert re.search(r'href="/\?recent_page=2"\s+aria-current="page"\s+>2</a>', second_page.text)


def test_entries_table_shows_refined_work_and_collapsed_original(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    EntryService().add_entry(
        "2026-05-08",
        "-샘플, 화면 이미지 & 기능 정리\n-일정표 스케줄 지금 작성하고 있어",
        project="샘플-Agent",
        source="test",
    )

    entries = client.get("/entries")

    assert entries.status_code == 200
    assert "정리된 업무" in entries.text
    assert "샘플, 화면 이미지 및 기능 정리." in entries.text
    assert "일정표 스케줄 작성." in entries.text
    assert '<details class="raw-original">' in entries.text
    assert "<summary>원본</summary>" in entries.text


def test_entries_and_project_detail_use_persisted_refined_text(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    EntryService(daily_refiner=FakeDailyRefiner()).add_entry(
        "2026-05-08",
        "원본 업무 기록",
        project="DOC",
        source="test",
    )

    entries = client.get("/entries")
    detail = client.get("/projects/DOC")

    assert "LLM 정리 결과" in entries.text
    assert "LLM 정리 결과" in detail.text
    assert "원본 업무 기록" in entries.text
    assert "원본 업무 기록" in detail.text


def test_web_can_edit_entry_text_date_and_project(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    created = EntryService().add_entry(
        "2026-05-08",
        "초기 기록",
        project="샘플",
        source="test",
    )

    edit = client.get(f"/entries/{created.id}/edit")
    assert edit.status_code == 200
    assert "기록 수정" in edit.text
    assert "초기 기록" in edit.text

    response = client.post(
        f"/entries/{created.id}",
        data={
            "work_date": "2026-05-09",
            "raw_text": "수정된 기록\n- 일정표 정리",
            "project": "일정표",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    entries = EntryService().list_entries()
    assert len(entries) == 1
    assert entries[0].work_date == "2026-05-09"
    assert entries[0].raw_text == "수정된 기록\n- 일정표 정리"
    assert entries[0].project == "일정표"
    page = client.get("/entries")
    assert "수정된 기록" in page.text
    assert "초기 기록" not in page.text


def test_editing_entry_preserves_existing_work_item_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    created = EntryService().add_entry(
        "2026-05-08",
        "API 오류 1건 수정 완료",
        project="API",
        source="test",
    )
    original = WorkItemService().list_items(project_key="API")[0]
    with connect() as conn:
        conn.execute(
            """
            update work_items
            set status = 'review', priority = 'high', outcome = '수동 보존 상태'
            where id = ?
            """,
            (original.id,),
        )

    response = client.post(
        f"/entries/{created.id}",
        data={
            "work_date": "2026-05-08",
            "raw_text": "API 오류 2건 수정 완료",
            "project": "API",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated = WorkItemService().list_items(project_key="API")
    assert len(updated) == 1
    assert updated[0].id == original.id
    assert updated[0].key == original.key
    assert updated[0].title == "API 오류 2건 수정 완료"
    assert updated[0].status == "review"
    assert updated[0].priority == "high"
    assert updated[0].outcome == "수동 보존 상태"


def test_entry_edit_updates_linked_work_card_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    created = EntryService().add_entry(
        "2026-05-08",
        "보고서 Agent를 위한 문서 관리 체계에 대해서 좀더 다듬었어",
        project="샘플-AGENT",
        source="test",
    )
    item = WorkItemService().list_items(project_key="샘플-AGENT")[0]

    edit = client.get(f"/entries/{created.id}/edit")

    assert edit.status_code == 200
    assert "업무 카드 수정" in edit.text
    assert item.key in edit.text
    assert f'action="/entries/{created.id}"' in edit.text
    assert f'action="/work-items/{item.id}"' not in edit.text
    assert 'name="status"' in edit.text
    assert 'name="priority"' in edit.text
    assert 'name="completed_at"' in edit.text
    assert 'data-open-date-picker="true"' in edit.text
    assert "상세 수정" not in edit.text

    response = client.post(
        f"/entries/{created.id}",
        data={
            "work_date": "2026-05-08",
            "project": "샘플-AGENT",
            "raw_text": "문서 관리 체계 정리",
            "status": "done",
            "priority": "high",
            "item_type": "task",
            "completed_at": "2026-05-21",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/entries"
    updated = WorkItemService().get_item(item.id)
    assert updated is not None
    assert updated.title == "문서 관리 체계 정리"
    assert updated.description == "문서 관리 체계 정리"
    assert updated.status == "done"
    assert updated.priority == "high"
    assert updated.item_type == "task"
    assert updated.completed_at == "2026-05-21"

    board = client.get("/board")
    entries = client.get("/entries")

    assert "문서 관리 체계 정리" in board.text
    assert "완료일 2026-05-21" in board.text
    assert item.key in entries.text
    assert "완료" in entries.text
    assert "문서 관리 체계 정리" in entries.text


def test_board_refresh_preserves_work_card_text_edited_from_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    created = EntryService().add_entry(
        "2026-05-08",
        "원본 문장 그대로 생성된 업무 카드",
        project="샘플-AGENT",
        source="test",
    )
    item = WorkItemService().list_items(project_key="샘플-AGENT")[0]

    response = client.post(
        f"/work-items/{item.id}",
        data={
            "title": "사용자가 정리한 업무 카드 제목",
            "description": "기록 화면에서 다듬은 카드 설명",
            "status": "todo",
            "priority": "medium",
            "item_type": "task",
            "completed_at": "",
            "return_to": f"/entries/{created.id}/edit",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    board = client.get("/board")
    updated = WorkItemService().get_item(item.id)

    assert board.status_code == 200
    assert updated is not None
    assert updated.title == "사용자가 정리한 업무 카드 제목"
    assert updated.description == "기록 화면에서 다듬은 카드 설명"
    assert "사용자가 정리한 업무 카드 제목" in board.text
    assert "원본 문장 그대로 생성된 업무 카드" not in board.text


def test_web_prompt_settings_can_be_updated(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    page = client.get("/prompts")
    assert page.status_code == 200
    assert "요약 프롬프트" in page.text
    assert "일별" in page.text
    assert "주별" in page.text

    response = client.post(
        "/prompts/day",
        data={"prompt_text": "내 일별 기록을 업무 보고 문장으로 다듬어줘."},
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = client.get("/prompts")
    assert "내 일별 기록을 업무 보고 문장으로 다듬어줘." in updated.text


def test_default_summary_prompts_match_refinement_goals(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))

    prompts = {
        prompt["period_type"]: prompt["prompt_text"]
        for prompt in SummaryPromptService().list_prompts()
    }

    assert "오늘의 핵심 요약" in prompts["day"]
    assert "성과평가용 문장 후보" in prompts["day"]
    assert "습니다체" in prompts["day"]
    assert "명사형" in prompts["week"]
    assert "성과" in prompts["month"]
    assert "상위 성과" in prompts["month"]


def test_legacy_default_prompts_are_refreshed_to_current_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    SummaryPromptService().ensure_defaults()
    with connect() as conn:
        conn.execute(
            """
            update summary_prompts
            set prompt_text = ?
            where period_type = 'day'
            """,
            (
                "하루 기록을 그대로 복사하지 말고 업무 보고 문장으로 다듬는다. "
                "무엇을 했는지, 어떤 성과나 산출물이 있었는지, 다음 액션이 무엇인지 짧게 정리한다.",
            ),
        )
        conn.execute(
            """
            update summary_prompts
            set prompt_text = ?
            where period_type = 'month'
            """,
            (
                "이번 달 기록을 누적 성과 중심으로 정리한다. 프로젝트별 진척, KPI 후보, 반복 이슈, "
                "다음 달로 넘길 액션을 중복 없이 요약한다.",
            ),
        )

    prompts = {
        prompt["period_type"]: prompt["prompt_text"]
        for prompt in SummaryPromptService().list_prompts()
    }

    assert "오늘의 핵심 요약" in prompts["day"]
    assert "상위 성과" in prompts["month"]


def test_web_returns_bad_request_for_invalid_entry_date(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    response = client.post(
        "/entries",
        data={
            "work_date": "2026-99-99",
            "raw_text": "잘못된 날짜",
            "project": "",
        },
    )

    assert response.status_code == 400
    assert "날짜" in response.text


def test_web_returns_bad_request_for_unsupported_summary_period(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    response = client.get("/summary/decade")

    assert response.status_code == 400
    assert "지원하지 않는 기간" in response.text


def test_web_projects_and_board_render(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    create = client.post(
        "/projects",
        data={"key": "API", "name": "API 안정화", "goal": "오류를 줄인다"},
        follow_redirects=False,
    )
    assert create.status_code == 303

    projects = client.get("/projects")
    board = client.get("/board")

    assert projects.status_code == 200
    assert "API 안정화" in projects.text
    assert "오늘 기록하기" not in projects.text
    assert "일별 기록" not in projects.text
    assert "프로젝트 카드" in projects.text
    assert board.status_code == 200
    assert "예정" in board.text


def test_board_shows_work_item_status_dates_and_edit_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    created = EntryService().add_entry(
        "2026-05-08",
        "보고서 Agent를 위한 문서 관리 체계에 대해서 좀더 다듬었어",
        project="샘플-AGENT",
        source="test",
    )
    item = WorkItemService().list_items(project_key="샘플-AGENT")[0]

    board = client.get("/board")

    assert board.status_code == 200
    assert "compact-board" in board.text
    assert "compact-work-card" in board.text
    assert "board-lane-count" in board.text
    assert "예정" in board.text
    assert "기록일 2026-05-08" in board.text
    assert f"/work-items/{item.id}/edit" in board.text
    assert "업무" in board.text
    assert created.id == item.source_entry_id

    edit = client.get(f"/work-items/{item.id}/edit")
    assert edit.status_code == 200
    assert "업무 카드 수정" in edit.text
    assert "목표일" not in edit.text
    assert 'type="date" name="due_date"' not in edit.text
    assert 'type="date" name="completed_at"' in edit.text
    assert 'data-open-date-picker="true"' in edit.text

    response = client.post(
        f"/work-items/{item.id}",
        data={
            "title": "문서 관리 체계 정리",
            "description": "보고서 Agent 문서 구조를 정리한다.",
            "status": "done",
            "priority": "high",
            "item_type": "task",
            "completed_at": "2026-05-20",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated = client.get("/board")
    assert "완료" in updated.text
    assert "문서 관리 체계 정리" in updated.text
    assert "목표일" not in updated.text
    assert "완료일 2026-05-20" in updated.text


def test_projects_page_shows_clean_project_cards(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "API 장애율 3% 개선 완료",
            "project": "API",
        },
    )

    projects = client.get("/projects")

    assert projects.status_code == 200
    assert "프로젝트 카드" in projects.text
    assert "API" in projects.text
    assert "기록 1개" in projects.text
    assert "카드 1개" in projects.text
    assert "최근 2026-05-08" in projects.text
    assert "오늘 기록하기" not in projects.text
    assert "일별 기록" not in projects.text


def test_today_project_input_auto_saves_for_future_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    create = client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "파트너 API 장애 원인 분석 완료",
            "project": "파트너 API",
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    dashboard = client.get("/")
    projects = client.get("/projects")

    assert dashboard.status_code == 200
    assert '<option value="파트너-API">' in dashboard.text
    assert "파트너 API" in dashboard.text
    assert projects.status_code == 200
    assert "파트너 API" in projects.text

    detail = client.get("/projects/파트너-API")

    assert detail.status_code == 200
    assert "2026-05-08" in detail.text
    assert "파트너 API 장애 원인 분석 완료" in detail.text

    summary = client.get("/summary/project?project=파트너-API")

    assert summary.status_code == 200
    assert "파트너 API 장애 원인 분석 완료" in summary.text


def test_project_detail_groups_entries_by_day_and_links_project_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "API 오류율 12%에서 4%로 개선 완료",
            "project": "API",
        },
    )
    client.post(
        "/entries",
        data={
            "work_date": "2026-05-07",
            "raw_text": "API 배포 체크리스트 정리",
            "project": "API",
        },
    )

    detail = client.get("/projects/API")

    assert detail.status_code == 200
    assert "API" in detail.text
    assert "2026-05-08" in detail.text
    assert "2026-05-07" in detail.text
    assert "정리된 업무" in detail.text
    assert "API 오류율 12%에서 4%로 개선 완료" in detail.text
    assert '<details class="raw-original">' in detail.text
    assert "/summary/project?project=API" in detail.text
    assert "프로젝트 표준 요약" in detail.text


def test_period_summary_renders_report_cards_and_can_be_edited(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    EntryService().add_entry(
        "2026-05-08",
        "API 장애율 3% 개선 완료",
        project="API",
        source="test",
    )

    summary = client.get("/summary/week?date=2026-05-08")

    assert summary.status_code == 200
    assert "보고서 개요" in summary.text
    assert "처리량" in summary.text
    assert "정리된 리포트" in summary.text
    assert "report-section" in summary.text
    assert "처리 업무" not in summary.text
    assert "성과 근거" in summary.text
    assert "KPI 후보" not in summary.text
    assert "##" not in summary.text
    assert "<pre>" not in summary.text
    assert "수정" in summary.text

    edit = client.get("/summary/week/edit?date=2026-05-08")
    assert edit.status_code == 200
    assert "보고서 수정" in edit.text

    response = client.post(
        "/summary/week/edit",
        data={
            "period_key": "2026-W19",
            "title": "수정된 주간 보고서",
            "body": "핵심 요약\n수정된 성과 정리\n\n완료/성과\n- API 안정화 성과 1건",
            "return_url": "/summary/week?date=2026-05-08",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated = client.get("/summary/week?date=2026-05-08")
    assert "수정된 주간 보고서" in updated.text
    assert "수정된 성과 정리" in updated.text
    assert "API 안정화 성과 1건" in updated.text


def test_week_summary_uses_readable_week_title_and_period_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    EntryService().add_entry(
        "2026-05-11",
        "주간 제목 확인",
        project="기금심사-AGENT",
        source="test",
    )

    summary = client.get("/summary/week?date=2026-05-11")

    assert summary.status_code == 200
    assert "2026년 5월 3주차 주간 요약" in summary.text
    assert "05.11-05.17" in summary.text
    assert "2026-W20 주별 요약" not in summary.text
    assert "전주" in summary.text
    assert "/summary/week?date=2026-05-04" in summary.text
    assert "다음주" in summary.text
    assert "/summary/week?date=2026-05-18" in summary.text


def test_summary_outcomes_are_split_into_summary_and_evidence_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    EntryService().add_entry(
        "2026-05-11",
        "MVP, Agent 엔드이미지 & 기능 정리\nWBS 스케줄 지금 작성하고 있어",
        project="기금심사-AGENT",
        source="test",
    )
    EntryService().add_entry(
        "2026-05-12",
        "보고서 Agent를 위한 문서 관리 체계에 대해서 좀더 다듬었어\n현업한테 요청할 필요사항들 정리",
        project="기금심사-AGENT",
        source="test",
    )

    summary = client.get("/summary/week?date=2026-05-12")

    assert summary.status_code == 200
    assert 'class="report-item-card structured"' in summary.text
    assert "요약" in summary.text
    assert "작업 4건 기반 주요 진행 내용 구체화" in summary.text
    assert "근거 작업" in summary.text
    assert "MVP, Agent 엔드이미지 &amp; 기능 정리" in summary.text
    assert "WBS 스케줄 지금 작성하고 있어" in summary.text
    assert "보고서 Agent를 위한 문서 관리 체계" in summary.text


def test_period_summary_shows_general_work_card_without_fake_outcomes(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    EntryService().add_entry(
        "2026-05-08",
        "샘플, 화면 이미지 & 기능 정리 완료\n일정표 스케줄 지금 작성하고 있어",
        project="샘플-AGENT",
        source="test",
    )

    summary = client.get("/summary/week?date=2026-05-08")

    assert summary.status_code == 200
    assert "한 작업" in summary.text
    assert "샘플, 화면 이미지 &amp; 기능 정리 완료" in summary.text
    assert "일정표 스케줄 지금 작성하고 있어" in summary.text
    assert "샘플, 화면 이미지 &amp; 기능 정리.: 샘플, 화면 이미지" not in summary.text
    assert "완료/성과" not in summary.text
    assert "다음 액션" not in summary.text


def test_existing_project_display_name_selection_does_not_create_duplicate(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    ProjectService().create_project(key="API", name="API 안정화", goal="장애를 줄인다")

    response = client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "API 재시도 로직 배포 완료",
            "project": "API 안정화",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert [project.key for project in ProjectService().list_projects()] == ["API"]
    assert [item.key for item in WorkItemService().list_items(project_key="API")] == ["API-1"]
    detail = client.get("/projects/API")
    assert "API 재시도 로직 배포 완료" in detail.text


def test_existing_project_display_name_with_spaces_does_not_create_duplicate(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    ProjectService().create_project(key="API", name="API 안정화", goal="장애를 줄인다")

    response = client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "API 오류 재발 확인",
            "project": "  API 안정화  ",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert [project.key for project in ProjectService().list_projects()] == ["API"]
    assert [item.key for item in WorkItemService().list_items(project_key="API")] == ["API-1"]


def test_project_detail_keeps_entries_after_project_display_name_update(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "파트너 API 장애 원인 분석 완료",
            "project": "파트너 API",
        },
    )
    ProjectService().create_project(
        key="파트너-API",
        name="파트너 API 안정화",
        goal="파트너 연동 장애를 줄인다",
    )

    detail = client.get("/projects/파트너-API")
    summary = client.get("/summary/project?project=파트너-API")

    assert detail.status_code == 200
    assert "파트너 API 장애 원인 분석 완료" in detail.text
    assert summary.status_code == 200
    assert "파트너 API 장애 원인 분석 완료" in summary.text


def test_project_detail_does_not_include_other_projects_that_only_mention_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "API 장애율 3% 개선",
            "project": "API",
        },
    )
    client.post(
        "/entries",
        data={
            "work_date": "2026-05-08",
            "raw_text": "WEB 문서에 API 참고 링크 추가",
            "project": "WEB",
        },
    )

    detail = client.get("/projects/API")

    assert detail.status_code == 200
    assert "API 장애율 3% 개선" in detail.text
    assert "WEB 문서에 API 참고 링크 추가" not in detail.text


def test_legacy_display_name_project_backfill_uses_existing_project_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    ProjectService().create_project(key="API", name="API 안정화", goal="장애를 줄인다")
    with connect() as conn:
        conn.execute(
            """
            insert into entries(work_date, raw_text, project, source, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-08",
                "API 안정화 레거시 기록",
                "API 안정화",
                "test",
                "2026-05-08T10:00:00",
                "2026-05-08T10:00:00",
            ),
        )

    projects = client.get("/projects")
    detail = client.get("/projects/API")

    assert projects.status_code == 200
    assert [project.key for project in ProjectService().list_projects()] == ["API"]
    assert detail.status_code == 200
    assert "API 안정화 레거시 기록" in detail.text


def test_project_info_form_can_update_existing_project_by_display_name(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    ProjectService().create_project(key="API", name="API 안정화", goal="장애를 줄인다")

    response = client.post(
        "/projects",
        data={
            "key": "API 안정화",
            "name": "API 신뢰도 개선",
            "goal": "배포 신뢰도를 높인다",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    projects = ProjectService().list_projects()
    assert [project.key for project in projects] == ["API"]
    assert projects[0].name == "API 신뢰도 개선"


def test_project_detail_can_manage_evaluation_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())
    ProjectService().create_project(key="AGENT", name="보고서 Agent", goal="초기 목표")

    detail = client.get("/projects/AGENT")

    assert detail.status_code == 200
    assert "프로젝트 개요" in detail.text
    assert "프로젝트명" in detail.text
    assert "목표" in detail.text
    assert "업무 내용" in detail.text
    assert "대상" in detail.text
    assert "수행 단계" in detail.text
    assert "정성 효과" in detail.text
    assert "정량 효과" in detail.text
    assert "산출물" in detail.text

    response = client.post(
        "/projects",
        data={
            "key": "AGENT",
            "name": "코딩어시스턴트 AI 서비스 고도화",
            "summary": "업무 기록을 평가용 리포트로 정리하는 시스템",
            "goal": (
                "업무 목표: 사내 개발자 생산성 향상을 위한 코딩어시스턴트의 기술적 완성도 및 서비스 품질 고도화\n"
                "세부 목표:\n"
                "1) 사내 개발환경 최적화\n"
                "2) 운영 효율성 개선\n"
                "3) 코딩어시스턴트 기능 고도화\n"
                "4) 활용 설치 가이드 및 교육 체계화"
            ),
            "work_content": (
                "[사내 개발환경 최적화]\n"
                "- continue, cursor, roo code 코딩어시스턴트 플러그인 기능 및 지원 수준 비교 분석\n"
                "- 관리망 환경에서의 도구 현황 조사 및 기능 차이점 정리\n"
                "- 코딩어시스턴트 버전별 비교 분석\n\n"
                "[운영 효율성 개선]\n"
                "- user case 시나리오 기반 서비스별 장단점 및 개선점 도출\n"
                "- 내부 개발자 환경설정 및 구축\n"
                "  + WSL 설치 오류 원인 분석\n"
                "  + Mac IntelliJ Node.js 버전 이슈 해결\n"
                "- 로그 기반 사용현황 모니터링 자동화 개발\n\n"
                "[코딩어시스턴트 기능 고도화]\n"
                "- 문제 해결을 위한 프롬프트 고도화\n"
                "- 실제 개발 워크플로우에 적용 가능한 사용 사례 정의 및 문서화\n"
                "- 개발자들의 Best Prompt 수집 및 분석\n\n"
                "[활용 설치 가이드 및 교육 체계화]\n"
                "- 코딩어시스턴트 설치 가이드 작성"
            ),
            "target_users": "업무 기록 작성자와 평가자",
            "core_features": "일별 기록 정리\n주간/월간 리포트 생성",
            "additional_features": "알림\n앵무새 파트너",
            "execution_stage": "MVP 검증 및 개선",
            "qualitative_effect": "업무 맥락과 기여도 설명력 향상",
            "quantitative_effect": "보고서 작성 시간 단축",
            "deliverables": "웹 앱\n프로젝트 상세 카드\n리포트 템플릿",
            "return_to": "/projects/AGENT",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/projects/AGENT"

    updated = client.get("/projects/AGENT")

    assert "코딩어시스턴트 AI 서비스 고도화" in updated.text
    assert "업무 기록을 평가용 리포트로 정리하는 시스템" in updated.text
    assert "사내 개발자 생산성 향상" in updated.text
    assert "활용 설치 가이드 및 교육 체계화" in updated.text
    assert "[사내 개발환경 최적화]" in updated.text
    assert "관리망 환경에서의 도구 현황 조사" in updated.text
    assert "WSL 설치 오류 원인 분석" in updated.text
    assert "Best Prompt 수집 및 분석" in updated.text
    assert "코딩어시스턴트 설치 가이드 작성" in updated.text
    assert "업무 기록 작성자와 평가자" in updated.text
    assert "주간/월간 리포트 생성" in updated.text
    assert "앵무새 파트너" in updated.text
    assert "MVP 검증 및 개선" in updated.text
    assert "업무 맥락과 기여도 설명력 향상" in updated.text
    assert "보고서 작성 시간 단축" in updated.text
    assert "프로젝트 상세 카드" in updated.text


def test_competency_page_can_save_monthly_work_people_review(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    client = TestClient(create_app())

    page = client.get("/competency?month=2026-05")

    assert page.status_code == 200
    assert "역량 평가" in page.text
    assert "문제해결" in page.text
    assert "업무효율성" in page.text
    assert "전문기술/지식" in page.text
    assert "커뮤니케이션" in page.text
    assert "협업" in page.text
    assert "상호존중/신뢰" in page.text

    response = client.post(
        "/competency",
        data={
            "month_key": "2026-05",
            "work_problem_solving": "소통을 통해 시스템 흐름 및 프로젝트의 실질적인 업무 수요 파악",
            "work_efficiency": "프로젝트 긴급도와 중요도 기준으로 우선순위 선정 및 납기 내 완수",
            "work_expertise": "코딩어시스턴트 운영 자동화 구조 설계",
            "people_communication": "현업 요청사항을 정리하고 이해관계자와 공유",
            "people_collaboration": "개발환경 이슈 해결 과정에서 관련 부서와 협업",
            "people_trust": "상호존중 기반으로 지원 요청을 빠르게 처리",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/competency?month=2026-05"

    updated = client.get("/competency?month=2026-05")

    assert "2026년 5월 역량 평가" in updated.text
    assert "2026년 2분기 역량 평가" in updated.text
    assert "2026년 연간 역량 평가" in updated.text
    assert "소통을 통해 시스템 흐름" in updated.text
    assert "프로젝트 긴급도와 중요도" in updated.text
    assert "현업 요청사항" in updated.text
