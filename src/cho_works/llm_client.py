from __future__ import annotations

import json

from cho_works.report_context import ReportContext
from cho_works.report_schema import WorkReport


class OpenAIReportClient:
    def __init__(self, model: str) -> None:
        self.model = model

    def summarize(self, context: ReportContext) -> WorkReport:
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.create(
            model=self.model,
            store=False,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You convert Korean work logs into a strict JSON work report. "
                        "Apply the period_prompt as the writing policy for this report period. "
                        "Rewrite raw logs into polished work-report language instead of concatenating them. "
                        "For week/month/quarter/year reports, merge duplicate work and describe only distinct core work. "
                        "For week/month/quarter/year reports, put completed task-level work in work_done first. "
                        "For week/month/quarter/year reports, outcomes must be grouped period achievements, "
                        "not one-to-one copies of work_done. Synthesize an outcome when multiple related work items "
                        "support a broader project result, delivered output, measurable effect, or clearer progress. "
                        "A single completed task is not an outcome by itself unless the source explicitly states "
                        "a delivered result or measurable effect. "
                        "Only include next_actions when the source explicitly states future work. "
                        "Avoid polite Korean report endings such as 습니다/했습니다; prefer concise noun-style "
                        "or clipped report phrases like 작성, 개발, 정리, 검토. "
                        "Do not invent projects, KPIs, outcomes, next actions, dates, people, or numbers. "
                        "Every claim must cite evidence_entry_ids from the provided entries. "
                        "Use Korean natural language for values, but keep JSON keys unchanged."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(_context_payload(context), ensure_ascii=False),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "work_report",
                    "strict": True,
                    "schema": strict_work_report_schema(),
                }
            },
        )
        text = _response_text(response)
        return WorkReport.model_validate_json(text)


class OpenAIDailyWorkClient:
    def __init__(self, model: str) -> None:
        self.model = model

    def refine(self, raw_text: str, prompt_text: str) -> str:
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.create(
            model=self.model,
            store=False,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You polish Korean daily work-log text for a personal work journal. "
                        "Use the provided day_prompt as the writing policy. "
                        "Do not invent facts, dates, projects, people, metrics, outcomes, or next actions. "
                        "Return only the polished work text for display in a daily card. "
                        "Do not include Markdown headings. Keep line breaks when the source has distinct items. "
                        "Avoid polite endings such as 습니다/했습니다; prefer concise report fragments like 작성, 개발, 정리, 검토."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "day_prompt": prompt_text,
                            "raw_text": raw_text,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        return _response_text(response).strip()


def _context_payload(context: ReportContext) -> dict:
    return {
        "report_type": context.report_type,
        "period": context.period.model_dump(),
        "project": context.project,
        "period_prompt": context.prompt_text,
        "entries": [
            {
                "id": entry.id,
                "work_date": entry.work_date,
                "project": entry.project,
                "raw_text": entry.raw_text,
            }
            for entry in context.entries
        ],
        "extracted_items": context.items,
        "kpi_observations": context.kpis,
    }


def _response_text(response) -> str:
    if getattr(response, "output_text", None):
        return response.output_text
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            text = getattr(content, "text", None)
            if text:
                return text
    raise ValueError("OpenAI response did not include text output.")


def strict_work_report_schema() -> dict:
    schema = WorkReport.model_json_schema()
    return _make_strict(schema)


def _make_strict(value):
    if isinstance(value, dict):
        value = {key: _make_strict(item) for key, item in value.items() if key != "default"}
        if value.get("type") == "object" or "properties" in value:
            properties = value.get("properties", {})
            value["additionalProperties"] = False
            value["required"] = list(properties.keys())
        return value
    if isinstance(value, list):
        return [_make_strict(item) for item in value]
    return value
