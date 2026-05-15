from __future__ import annotations

import re

from cho_works.models import ParsedEntry, ParsedItem, ParsedKpi

TAG_RE = re.compile(r"#([0-9A-Za-z_가-힣-]+)")
KPI_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>건|개|명|시간|분|회|%|원|만원|일)")
PROJECT_RE = re.compile(r"([0-9A-Za-z가-힣_-]+)\s*프로젝트")


def parse_entry_text(text: str) -> ParsedEntry:
    tags = _dedupe(TAG_RE.findall(text))
    clean_text = TAG_RE.sub("", text)
    sentences = _split_sentences(clean_text)
    projects = _dedupe(project for sentence in sentences for project in _projects(sentence))

    items: list[ParsedItem] = []
    kpis: list[ParsedKpi] = []
    for sentence in sentences:
        project = _projects(sentence)
        item = ParsedItem(
            item_type=_classify(sentence),
            content=sentence,
            project=project[0] if project else None,
            tags=tags,
        )
        items.append(item)
        kpis.extend(_kpis(sentence))

    return ParsedEntry(items=items, kpis=kpis, tags=tags, projects=projects)


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?\n。]+", text) if part.strip()]


def _projects(sentence: str) -> list[str]:
    return _dedupe(PROJECT_RE.findall(sentence))


def _classify(sentence: str) -> str:
    if _has(sentence, "다음", "예정", "해야", "할 일", "액션", "todo", "TODO"):
        return "next_action"
    if _has(sentence, "결정", "합의", "확정"):
        return "decision"
    if _has(sentence, "장애", "이슈", "문제", "지연", "블로커", "막힘", "오류") and not _has(
        sentence, "완료", "해결", "개선", "수정", "감소", "완화", "확인", "정상화"
    ):
        return "blocker"
    if _has(sentence, "회의", "미팅", "논의", "공유"):
        return "meeting"
    if _has(sentence, "완료", "해결", "개선", "수정", "배포", "감소", "완화", "확인", "정상화"):
        return "outcome"
    return "task"


def _kpis(sentence: str) -> list[ParsedKpi]:
    kpis: list[ParsedKpi] = []
    for match in KPI_RE.finditer(sentence):
        value = float(match.group("value"))
        if value.is_integer():
            value = int(value)
        unit = match.group("unit")
        kpis.append(
            ParsedKpi(
                name=_kpi_name(sentence, match.start()),
                value=value,
                unit=unit,
            )
        )
    return kpis


def _kpi_name(sentence: str, index: int) -> str:
    prefix = sentence[:index].strip()
    words = prefix.split()
    if not words:
        return "수치"
    return " ".join(words[-3:])


def _has(sentence: str, *keywords: str) -> bool:
    return any(keyword in sentence for keyword in keywords)


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
