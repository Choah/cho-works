import os
import subprocess
import sys
from pathlib import Path


def test_load_env_file_sets_supported_values_without_overriding_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    db_path = tmp_path / "cho.sqlite3"
    env_file.write_text(
        "\n".join(
            [
                "# Cho Works local settings",
                f"CHO_WORKS_DB_PATH={db_path}",
                "OPENAI_API_KEY=from-env-file",
                "CHO_WORKS_OPENAI_MODEL=gpt-4o-mini",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CHO_WORKS_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("CHO_WORKS_DB_PATH", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "already-set")
    monkeypatch.delenv("CHO_WORKS_OPENAI_MODEL", raising=False)

    from cho_works.config import database_path, load_env_file

    load_env_file(env_file)

    assert database_path() == db_path
    assert Path(db_path).name == "cho.sqlite3"
    assert os.environ["OPENAI_API_KEY"] == "already-set"
    assert os.environ["CHO_WORKS_OPENAI_MODEL"] == "gpt-4o-mini"


def test_config_import_loads_env_file_selected_by_environment(tmp_path):
    env_file = tmp_path / "custom.env"
    db_path = tmp_path / "selected.sqlite3"
    env_file.write_text(f"CHO_WORKS_DB_PATH={db_path}\n", encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": "src",
        "CHO_WORKS_ENV_FILE": str(env_file),
    }
    env.pop("CHO_WORKS_DB_PATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from cho_works.config import database_path; print(database_path())",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.stdout.strip() == str(db_path)


def test_env_example_documents_runtime_settings_without_secrets():
    example = Path(".env.example").read_text(encoding="utf-8")

    assert "CHO_WORKS_DB_PATH=" in example
    assert "CHO_WORKS_ENV_FILE=" in example
    assert "OPENAI_API_KEY=" in example
    assert "CHO_WORKS_OPENAI_MODEL=" in example
    assert "sk-" not in example
