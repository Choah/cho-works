import sqlite3


def test_init_db_creates_core_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "cho.sqlite3"
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(db_path))

    from cho_works.db import connect, init_db

    init_db()
    with connect() as conn:
        names = {
            row["name"]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        }

    assert {
        "entries",
        "entry_items",
        "kpi_observations",
        "summaries",
        "projects",
        "work_items",
        "reminder_configs",
        "reminder_events",
        "pet_state",
    }.issubset(names)


def test_package_includes_web_templates_and_static_assets():
    from importlib.resources import files

    package_root = files("cho_works")

    assert package_root.joinpath("templates", "base.html").is_file()
    assert package_root.joinpath("static", "img", "parrot-companion.png").is_file()


def test_init_db_adds_refined_text_to_existing_entries_table(tmp_path, monkeypatch):
    db_path = tmp_path / "cho.sqlite3"
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(db_path))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            create table entries (
                id integer primary key autoincrement,
                work_date text not null,
                raw_text text not null,
                project text,
                source text not null default 'cli',
                created_at text not null,
                updated_at text not null
            )
            """
        )

    from cho_works.db import connect, init_db

    init_db()
    with connect() as conn:
        columns = {row["name"] for row in conn.execute("pragma table_info(entries)").fetchall()}

    assert "refined_text" in columns
