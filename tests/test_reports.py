import json

from cho_works.db import connect
from cho_works.report_schema import WorkReport, render_report_markdown
from cho_works.services import EntryService, SummaryPromptService, SummaryService


def test_work_report_schema_renders_standard_sections():
    report = WorkReport(
        report_type="day",
        period={
            "key": "2026-05-08",
            "label": "2026-05-08",
            "start_date": "2026-05-08",
            "end_date": "2026-05-08",
        },
        project=None,
        source_entry_ids=[1],
        executive_summary="API 오류를 수정하고 배포 리스크를 줄였습니다.",
        outcomes=[
            {
                "title": "API 오류 수정",
                "description": "API 오류 3건을 수정했습니다.",
                "project": "A",
                "date": "2026-05-08",
                "evidence_entry_ids": [1],
                "confidence": 0.9,
            }
        ],
        kpis=[
            {
                "name": "API 오류 수정",
                "value": 3,
                "unit": "건",
                "direction": "up",
                "context": "API 오류 3건 수정",
                "evidence_entry_ids": [1],
                "confidence": 0.9,
            }
        ],
        decisions=[],
        blockers=[],
        meetings=[],
        next_actions=[],
        risks=[],
        themes=["안정화"],
        coverage={
            "entry_count": 1,
            "date_count": 1,
            "projects": ["A"],
            "warnings": [],
        },
        generation={
            "mode": "deterministic",
            "model": None,
            "fallback_reason": None,
        },
    )

    markdown = render_report_markdown(report)

    assert "## Executive Summary" in markdown
    assert "## KPI Evidence" in markdown
    assert "API 오류 수정" in markdown
    assert "성과 1건" in markdown


def test_summary_persists_structured_fallback_report(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    entries = EntryService()

    created = entries.add_entry(
        "2026-05-08",
        "A 프로젝트 API 오류 3건 수정 완료. B 회의에서 배포 일정 결정.",
        source="test",
    )
    summary = SummaryService().generate("day", "2026-05-08")

    with connect() as conn:
        row = conn.execute(
            "select report_json, generation_mode from summaries where period_type = 'day'"
        ).fetchone()

    payload = json.loads(row["report_json"])
    assert row["generation_mode"] == "deterministic"
    assert payload["source_entry_ids"] == [created.id]
    assert payload["kpis"][0]["value"] == 3
    assert "## Outcomes" in summary.body


def test_high_level_summary_keeps_tasks_in_work_done_and_synthesizes_grouped_project_outcome(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    entries = EntryService()

    first = entries.add_entry(
        "2026-05-08",
        "샘플 기능 정리 완료",
        project="샘플-AGENT",
        source="test",
    )
    second = entries.add_entry(
        "2026-05-09",
        "일정표 스케줄 작성하고 있어",
        project="샘플-AGENT",
        source="test",
    )

    SummaryService().generate("week", "2026-05-09")

    with connect() as conn:
        row = conn.execute("select report_json from summaries where period_type = 'week'").fetchone()
    payload = json.loads(row["report_json"])

    assert [item["description"] for item in payload["work_done"]] == [
        "샘플 기능 정리 완료.",
        "일정표 스케줄 작성하고 있어.",
    ]
    assert len(payload["outcomes"]) == 1
    outcome = payload["outcomes"][0]
    assert outcome["title"] == "샘플-AGENT 성과"
    assert "샘플 기능 정리 완료" in outcome["description"]
    assert "일정표 스케줄 작성하고 있어" in outcome["description"]
    assert "상위 성과로 정리" not in outcome["description"]
    assert payload["next_actions"] == []
    assert payload["source_entry_ids"] == [first.id, second.id]


def test_week_month_quarter_year_summaries_group_period_work_into_outcomes(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    entries = EntryService()

    first = entries.add_entry(
        "2026-05-11",
        "보고서 Agent를 위한 문서 관리 체계에 대해서 좀더 다듬었어. (현업한테 요청할 필요사항들 정리).",
        project="기금심사-AGENT",
        source="test",
    )
    second = entries.add_entry(
        "2026-05-11",
        "프롬프트 리팩토링.",
        project="분석AGENT",
        source="test",
    )

    for period_type in ["week", "month", "quarter", "year"]:
        summary = SummaryService().generate(period_type, "2026-05-11")
        with connect() as conn:
            row = conn.execute(
                "select report_json from summaries where period_type = ?",
                (period_type,),
            ).fetchone()
        payload = json.loads(row["report_json"])

        assert payload["source_entry_ids"] == [first.id, second.id]
        assert "보고서 Agent를 위한 문서 관리 체계에 대해서 좀더 다듬었어" in summary.body
        assert "현업한테 요청할 필요사항들 정리" in summary.body
        assert "프롬프트 리팩토링" in summary.body
        assert len(payload["outcomes"]) == 1
        outcome = payload["outcomes"][0]
        assert outcome["title"] == "기금심사-AGENT 성과"
        assert "문서 관리 체계" in outcome["description"]
        assert "현업한테 요청할 필요사항들 정리" in outcome["description"]
        assert "상위 성과로 정리" not in outcome["description"]
        assert "기금심사-AGENT 작업 2건" not in outcome["description"]
        assert "[기금심사-AGENT] 기금심사-AGENT 성과" not in summary.body
        assert f"{outcome['title']}: {outcome['description']}" not in summary.body


def test_high_level_summary_synthesizes_outcome_from_broader_project_result(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    entries = EntryService()

    first = entries.add_entry(
        "2026-05-07",
        "API 오류 3건 수정 완료",
        project="API",
        source="test",
    )
    second = entries.add_entry(
        "2026-05-08",
        "API 재시도 로직 배포 완료",
        project="API",
        source="test",
    )
    third = entries.add_entry(
        "2026-05-09",
        "API 장애 재발 감소 확인",
        project="API",
        source="test",
    )

    SummaryService().generate("week", "2026-05-09")

    with connect() as conn:
        row = conn.execute("select report_json from summaries where period_type = 'week'").fetchone()
    payload = json.loads(row["report_json"])

    assert len(payload["work_done"]) == 3
    assert len(payload["outcomes"]) == 1
    outcome = payload["outcomes"][0]
    assert outcome["title"] == "API 성과"
    assert "작업 3건" in outcome["description"]
    assert set(outcome["evidence_entry_ids"]) == {first.id, second.id, third.id}


def test_get_or_generate_refreshes_generated_summary_when_period_entries_change(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    entries = EntryService()
    first = entries.add_entry(
        "2026-05-11",
        "첫 번째 업무 정리",
        project="기금심사-AGENT",
        source="test",
    )

    SummaryService().generate("week", "2026-05-11")

    second = entries.add_entry(
        "2026-05-12",
        "두 번째 업무 정리",
        project="기금심사-AGENT",
        source="test",
    )

    refreshed = SummaryService().get_or_generate("week", "2026-05-12")

    assert refreshed.source_entry_ids == [first.id, second.id]
    assert "두 번째 업무 정리" in refreshed.body


def test_high_level_summary_only_includes_explicit_next_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    EntryService().add_entry(
        "2026-05-08",
        "API 문서 정리 완료",
        project="API",
        source="test",
    )
    EntryService().add_entry(
        "2026-05-09",
        "다음에는 배포 계획 확정 예정",
        project="API",
        source="test",
    )

    SummaryService().generate("week", "2026-05-09")

    with connect() as conn:
        row = conn.execute("select report_json from summaries where period_type = 'week'").fetchone()
    payload = json.loads(row["report_json"])

    assert [item["description"] for item in payload["next_actions"]] == ["다음에는 배포 계획 확정 예정."]


def test_summary_uses_llm_report_when_provider_returns_valid_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    created = entries.add_entry(
        "2026-05-08",
        "A 프로젝트 API 오류 3건 수정 완료",
        source="test",
    )

    class FakeSummarizer:
        def summarize(self, context):
            payload = WorkReport.empty(
                report_type=context.report_type,
                period=context.period,
                project=context.project,
                source_entry_ids=[created.id],
            )
            return payload.model_copy(
                update={
                    "executive_summary": "LLM이 정리한 핵심 요약입니다.",
                    "generation": {
                        "mode": "llm",
                        "model": "fake",
                        "fallback_reason": None,
                    },
                }
            )

    summary = SummaryService(summarizer=FakeSummarizer()).generate("day", "2026-05-08")

    assert "LLM이 정리한 핵심 요약입니다." in summary.body
    with connect() as conn:
        row = conn.execute("select generation_mode, model from summaries").fetchone()
    assert row["generation_mode"] == "llm"
    assert row["model"] == "fake"


def test_summary_uses_saved_period_prompt_in_summarizer_context(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    EntryService().add_entry(
        "2026-05-08",
        "API 안정화 작업 완료",
        project="API",
        source="test",
    )
    SummaryPromptService().set_prompt("week", "주별 기록은 중복 없이 핵심 업무만 정리한다.")

    class PromptCheckingSummarizer:
        def summarize(self, context):
            assert context.prompt_text == "주별 기록은 중복 없이 핵심 업무만 정리한다."
            payload = WorkReport.empty(
                report_type=context.report_type,
                period=context.period,
                project=context.project,
                source_entry_ids=context.source_entry_ids,
            )
            return payload.model_copy(
                update={
                    "executive_summary": "저장된 프롬프트 기준으로 정리했습니다.",
                    "generation": {
                        "mode": "llm",
                        "model": "fake",
                        "fallback_reason": None,
                    },
                }
            )

    summary = SummaryService(summarizer=PromptCheckingSummarizer()).generate("week", "2026-05-08")

    assert "저장된 프롬프트 기준" in summary.body


def test_summary_source_entries_are_loaded_from_generated_source_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    first = entries.add_entry(
        "2026-05-08",
        "첫 번째 기록",
        project="API",
        source="test",
    )

    class MutatingSummarizer:
        def summarize(self, context):
            EntryService().add_entry(
                "2026-05-08",
                "요약 생성 중 추가된 기록",
                project="API",
                source="test",
            )
            payload = WorkReport.empty(
                report_type=context.report_type,
                period=context.period,
                project=context.project,
                source_entry_ids=[first.id],
            )
            return payload.model_copy(
                update={
                    "executive_summary": "첫 번째 기록만 사용했습니다.",
                    "generation": {
                        "mode": "llm",
                        "model": "fake",
                        "fallback_reason": None,
                    },
                }
            )

    summary = SummaryService(summarizer=MutatingSummarizer()).generate("day", "2026-05-08")
    source_entries = SummaryService().entries_by_ids(summary.source_entry_ids)

    assert [entry.id for entry in source_entries] == [first.id]
    assert source_entries[0].raw_text == "첫 번째 기록"


def test_llm_report_without_evidence_ids_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    entries.add_entry(
        "2026-05-08",
        "A 프로젝트 API 오류 3건 수정 완료",
        source="test",
    )

    class UngroundedSummarizer:
        def summarize(self, context):
            payload = WorkReport.empty(
                report_type=context.report_type,
                period=context.period,
                project=context.project,
                source_entry_ids=context.source_entry_ids,
            )
            return payload.model_copy(
                update={
                    "executive_summary": "근거 없는 LLM 요약",
                    "outcomes": [
                        {
                            "title": "근거 없는 성과",
                            "description": "출처 없이 만든 성과",
                            "project": "A",
                            "date": "2026-05-08",
                            "evidence_entry_ids": [],
                            "confidence": 0.9,
                        }
                    ],
                    "generation": {
                        "mode": "llm",
                        "model": "fake",
                        "fallback_reason": None,
                    },
                }
            )

    summary = SummaryService(summarizer=UngroundedSummarizer()).generate("day", "2026-05-08")

    assert "근거 없는 성과" not in summary.body
    with connect() as conn:
        row = conn.execute("select generation_mode, error from summaries").fetchone()
    assert row["generation_mode"] == "fallback"
    assert "evidence" in row["error"]


def test_openai_schema_is_strict_compatible():
    from cho_works.llm_client import strict_work_report_schema

    schema = strict_work_report_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_openai_context_payload_includes_period_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    EntryService().add_entry(
        "2026-05-08",
        "프롬프트 payload 확인",
        project="API",
        source="test",
    )
    SummaryPromptService().set_prompt("day", "일별 payload 프롬프트")
    entries, key, title, start_date, end_date = SummaryService()._scope("day", "2026-05-08")
    from cho_works.llm_client import _context_payload
    from cho_works.report_context import build_report_context

    payload = _context_payload(
        build_report_context(
            "day",
            key,
            title,
            entries,
            start_date=start_date,
            end_date=end_date,
            prompt_text=SummaryPromptService().get_prompt("day"),
        )
    )

    assert payload["period_prompt"] == "일별 payload 프롬프트"
