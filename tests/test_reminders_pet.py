from cho_works.services import EntryService, PetService, ReminderService


def test_pet_rewards_logging_consistency(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    entries = EntryService()
    pet = PetService()

    entries.add_entry("2026-05-07", "정산 자동화 완료", source="test")
    entries.add_entry("2026-05-08", "장애 원인 분석 완료", source="test")

    state = pet.refresh(today="2026-05-08")

    assert state.streak_days == 2
    assert state.care_points >= 20
    assert state.mood in {"calm", "happy", "focused"}


def test_due_reminders_respect_enabled_configs(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    reminders = ReminderService()
    reminders.set_config("end_of_day", "18:00", enabled=True)

    due = reminders.due("2026-05-08T18:05:00")

    assert due[0].reminder_type == "end_of_day"


def test_due_reminders_handle_timezone_aware_now(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    reminders = ReminderService()
    reminders.set_config("end_of_day", "18:00", enabled=True)

    due = reminders.due("2026-05-08T18:05:00+09:00")

    assert due[0].reminder_type == "end_of_day"


def test_due_reminders_are_read_only_until_delivered(tmp_path, monkeypatch):
    monkeypatch.setenv("CHO_WORKS_DB_PATH", str(tmp_path / "cho.sqlite3"))
    reminders = ReminderService()
    reminders.set_config("end_of_day", "18:00", enabled=True)

    first = reminders.due("2026-05-08T18:05:00")
    second = reminders.due("2026-05-08T18:05:00")

    assert len(first) == 1
    assert len(second) == 1

    reminders.mark_delivered(first[0])

    assert reminders.due("2026-05-08T18:05:00") == []
