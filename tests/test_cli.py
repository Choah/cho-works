from typer.testing import CliRunner

from cho_works.cli import app
from cho_works.services import EntryService


def test_cli_init_creates_database_and_reports_path(tmp_path, monkeypatch):
    db_path = tmp_path / "nested" / "cho.sqlite3"
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(db_path))
    runner = CliRunner()

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert db_path.exists()
    assert str(db_path) in result.output
    assert "Cho Works 준비 완료" in result.output


def test_cli_add_and_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    runner = CliRunner()

    add = runner.invoke(
        app,
        ["add", "A 프로젝트 문서 1건 정리 완료", "--date", "2026-05-08"],
    )
    assert add.exit_code == 0

    summary = runner.invoke(app, ["summary", "day", "--date", "2026-05-08"])
    assert summary.exit_code == 0
    assert "2026년 5월 8일 일별 요약" in summary.output
    assert "문서" in summary.output


def test_cli_search_finds_project_text(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    runner = CliRunner()

    runner.invoke(app, ["add", "검색 테스트 프로젝트 완료", "--date", "2026-05-08"])
    result = runner.invoke(app, ["search", "검색"])

    assert result.exit_code == 0
    assert "검색 테스트" in result.output


def test_cli_reports_invalid_date_without_traceback(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    runner = CliRunner()

    result = runner.invoke(app, ["add", "날짜 오류", "--date", "2026-99-99"])

    assert result.exit_code != 0
    assert "날짜" in result.output
    assert "Traceback" not in result.output


def test_cli_requires_project_for_project_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    runner = CliRunner()

    result = runner.invoke(app, ["summary", "project"])

    assert result.exit_code != 0
    assert "프로젝트" in result.output
    assert "Traceback" not in result.output


def test_cli_project_and_item_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    runner = CliRunner()

    create = runner.invoke(
        app,
        ["project", "add", "API", "API 안정화", "--goal", "오류를 줄인다"],
    )
    listing = runner.invoke(app, ["project", "list"])

    assert create.exit_code == 0
    assert listing.exit_code == 0
    assert "API 안정화" in listing.output


def test_cli_refresh_recomputes_refined_daily_text(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeOpenAIRefiner:
        def refine(self, raw_text: str) -> str:
            return "REFRESH LLM 정리"

    monkeypatch.setattr("cho_works.services.OpenAIDailyWorkRefiner", FakeOpenAIRefiner)
    runner = CliRunner()

    add = runner.invoke(app, ["add", "초안 작성하고 있어", "--date", "2026-05-08"])
    refresh = runner.invoke(app, ["refresh"])

    assert add.exit_code == 0
    assert refresh.exit_code == 0
    assert "파생 데이터 재정리 완료" in refresh.output
    assert EntryService().list_entries()[0].refined_text == "REFRESH LLM 정리"
