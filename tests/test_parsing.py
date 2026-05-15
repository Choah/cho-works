from cho_works.parsing import parse_entry_text


def test_parse_entry_extracts_korean_work_items_and_kpis():
    parsed = parse_entry_text(
        "A 프로젝트 API 오류 3건 수정 완료. B 회의에서 배포 일정 결정. #backend"
    )

    assert parsed.items[0].item_type == "outcome"
    assert parsed.items[0].project == "A"
    assert parsed.items[1].item_type == "decision"
    assert parsed.kpis[0].value == 3
    assert parsed.kpis[0].unit == "건"
    assert "backend" in parsed.tags


def test_parse_entry_marks_blockers_and_meetings():
    parsed = parse_entry_text("C 프로젝트 회의 진행. 인증 장애로 배포 지연.")

    assert [item.item_type for item in parsed.items] == ["meeting", "blocker"]


def test_parse_entry_keeps_general_work_separate_from_outcomes_and_next_actions():
    parsed = parse_entry_text(
        "샘플, 화면 이미지 & 기능 정리. 일정표 스케줄 지금 작성하고 있어. 다음에는 배포 계획 확정 예정."
    )

    assert [item.item_type for item in parsed.items] == ["task", "task", "next_action"]
