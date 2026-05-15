from cho_works.services import CompetencyReviewService, EntryService, ProjectService, SummaryService


class FakeDailyRefiner:
    def __init__(self) -> None:
        self.inputs = []

    def refine(self, raw_text: str) -> str:
        self.inputs.append(raw_text)
        return "LLM 정리 결과"


class FakeOpenAIRefiner:
    calls = []

    def refine(self, raw_text: str) -> str:
        self.calls.append(raw_text)
        return "OPENAI 정리 결과"


def test_entry_service_uses_daily_refiner_and_persists_result(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    refiner = FakeDailyRefiner()
    entries = EntryService(daily_refiner=refiner)

    created = entries.add_entry(
        "2026-05-08",
        "회의록 초안 작성하고 있어",
        project="DOC",
        source="test",
    )
    cards = EntryService().recent_entry_cards(limit=1)

    assert refiner.inputs == ["회의록 초안 작성하고 있어"]
    assert created.refined_text == "LLM 정리 결과"
    assert cards[0]["refined_text"] == "LLM 정리 결과"


def test_entry_service_uses_openai_daily_refiner_when_api_key_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    FakeOpenAIRefiner.calls = []
    monkeypatch.setattr("cho_works.services.OpenAIDailyWorkRefiner", FakeOpenAIRefiner)

    entry = EntryService().add_entry(
        "2026-05-08",
        "보고서 초안 작성하고 있어",
        project="DOC",
        source="test",
    )

    assert FakeOpenAIRefiner.calls == ["보고서 초안 작성하고 있어"]
    assert entry.refined_text == "OPENAI 정리 결과"


def test_entry_service_persists_entry_items_and_project_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    summaries = SummaryService()

    created = entries.add_entry(
        "2026-05-08",
        "A 프로젝트 배포 자동화 2건 개선 완료. 인증 이슈 해결.",
        project="A",
        source="test",
    )

    assert created.id > 0
    assert entries.search("자동화")[0].id == created.id

    summary = summaries.generate("project", "A")
    assert "A" in summary.title
    assert "배포 자동화" in summary.body
    assert summary.source_entry_ids == [created.id]


def test_summary_service_generates_month_and_quarter(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    summaries = SummaryService()

    entries.add_entry("2026-04-01", "A 프로젝트 장애 1건 해결 완료", source="test")
    entries.add_entry("2026-05-08", "B 프로젝트 리포트 2건 정리 완료", source="test")

    month = summaries.generate("month", "2026-05-08")
    quarter = summaries.generate("quarter", "2026-05-08")

    assert "2026년 5월 월간 요약" in month.title
    assert "리포트" in month.body
    assert "2026년 2분기 요약" in quarter.title
    assert "장애" in quarter.body
    assert "리포트" in quarter.body


def test_project_service_persists_evaluation_profile_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))

    project = ProjectService().create_project(
        key="AGENT",
        name="보고서 Agent",
        summary="업무 보고서 자동 정리 시스템",
        goal="업무 목표: 연말 평가에 활용 가능한 업무 근거 축적\n세부 목표:\n1) 리포트 자동화",
        work_content="[리포트 자동화]\n- 일별 기록 정리\n- 주간/월간 리포트 생성",
        target_users="업무 기록 작성자와 평가자",
        core_features="일별 기록 정리\n주간/월간 리포트 생성",
        additional_features="알림\n앵무새 상태 표시",
        execution_stage="MVP 검증 단계",
        qualitative_effect="업무 맥락 설명 품질 개선",
        quantitative_effect="주간 보고 작성 시간 단축",
        deliverables="웹 앱\nSQLite 데이터 구조\n리포트 템플릿",
    )

    assert project.summary == "업무 보고서 자동 정리 시스템"
    assert "세부 목표" in project.goal
    assert "[리포트 자동화]" in project.work_content
    assert "주간/월간 리포트 생성" in project.work_content
    assert project.target_users == "업무 기록 작성자와 평가자"
    assert "주간/월간 리포트 생성" in project.core_features
    assert project.additional_features == "알림\n앵무새 상태 표시"
    assert project.execution_stage == "MVP 검증 단계"
    assert project.qualitative_effect == "업무 맥락 설명 품질 개선"
    assert project.quantitative_effect == "주간 보고 작성 시간 단축"
    assert "리포트 템플릿" in project.deliverables


def test_competency_review_service_summarizes_month_quarter_and_year(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    service = CompetencyReviewService()

    may = service.upsert_month(
        month_key="2026-05",
        work_problem_solving="소통을 통해 시스템 흐름 및 프로젝트의 실질적인 업무 수요 파악",
        work_efficiency="프로젝트 긴급도와 중요도 기준으로 우선순위 선정 및 납기 내 완수",
        work_expertise="코딩어시스턴트 운영 자동화 구조 설계",
        people_communication="현업 요청사항을 정리하고 이해관계자와 공유",
    )
    service.upsert_month(
        month_key="2026-06",
        people_collaboration="개발환경 이슈 해결 과정에서 관련 부서와 협업",
        people_trust="상호존중 기반으로 지원 요청을 빠르게 처리",
    )

    month = service.summarize("month", "2026-05")
    quarter = service.summarize("quarter", "2026-06")
    year = service.summarize("year", "2026-12")

    assert may.month_key == "2026-05"
    assert month["title"] == "2026년 5월 역량 평가"
    assert "소통을 통해 시스템 흐름" in month["sections"][0]["items"][0]["entries"][0]["text"]
    assert quarter["title"] == "2026년 2분기 역량 평가"
    assert "협업" in [item["label"] for item in quarter["sections"][1]["items"]]
    assert year["title"] == "2026년 연간 역량 평가"
    assert {review.month_key for review in year["reviews"]} == {"2026-05", "2026-06"}


def test_search_finds_entries_through_generated_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    summaries = SummaryService()

    created = entries.add_entry(
        "2026-05-08",
        "요약 검색 프로젝트에서 릴리즈 노트 1건 작성 완료",
        project="검색",
        source="test",
    )
    summaries.generate("day", "2026-05-08")

    results = entries.search("핵심 요약")

    assert [entry.id for entry in results] == [created.id]


def test_summary_groups_items_by_type(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    summaries = SummaryService()

    entries.add_entry(
        "2026-05-08",
        "A 프로젝트 API 오류 3건 수정 완료. B 회의에서 배포 일정 결정. 인증 장애로 배포 지연.",
        source="test",
    )

    summary = summaries.generate("day", "2026-05-08")

    assert "성과" in summary.body
    assert "결정" in summary.body
    assert "이슈/블로커" in summary.body
    assert "KPI 후보" in summary.body


def test_summary_separates_general_work_from_outcomes_and_next_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    summaries = SummaryService()

    entries.add_entry(
        "2026-05-08",
        "샘플, 화면 이미지 & 기능 정리\n일정표 스케줄 지금 작성하고 있어",
        project="샘플-AGENT",
        source="test",
    )

    summary = summaries.generate("day", "2026-05-08")

    assert "한 작업" in summary.body
    assert "[샘플-AGENT] 샘플, 화면 이미지 & 기능 정리." in summary.body
    assert "샘플, 화면 이미지 & 기능 정리.: 샘플, 화면 이미지 & 기능 정리." not in summary.body
    assert "[샘플-AGENT] 일정표 스케줄 지금 작성하고 있어." in summary.body
    assert "[샘플-AGENT] 일정표 스케줄 지금 작성하고 있어.: 일정표 스케줄 지금 작성하고 있어." not in summary.body
    assert "성과 2건" not in summary.body
    assert "다음 액션/업무" not in summary.body
