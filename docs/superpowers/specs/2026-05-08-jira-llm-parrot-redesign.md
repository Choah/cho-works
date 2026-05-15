# Jira LLM Parrot Redesign

## Goal

Upgrade Cho Works from a basic work-log viewer into a local-first personal work management app that feels closer to a lightweight Jira/Atlassian Home system, while adding optional LLM report generation and a more expressive parrot companion.

## Research Basis

The report and project model follows these external patterns:

- OpenAI Structured Outputs: use strict JSON schema for consistent LLM reports and deterministic parsing.
- Jira work items: preserve status, priority, and resolution-style fields so work can be scanned and reported.
- Jira workflows: represent work through simple columns and transitions instead of a flat log.
- Atlassian Goals/OKR: make outcomes and measurable success evidence explicit.
- Atlassian weekly project updates: include wins, needs/blockers, focus, decisions, risks, and learnings.

## Product Changes

Cho Works now treats projects as first-class records with keys, names, status, health, goals, and target dates. Daily logs remain the source of truth, but parsed work becomes Jira-like work items connected to projects.

The web app should expose:

- Today dashboard.
- Projects.
- Board.
- Entries.
- Period reports.
- Reminders.
- Parrot companion.

## Standard Report Format

Every report uses the same structure:

1. Executive Summary / 핵심 요약
2. Outcomes / 완료/성과
3. KPI Evidence / KPI 근거
4. Project Progress / 프로젝트 진행
5. Decisions / 결정
6. Risks And Blockers / 리스크와 이슈/블로커
7. Next Actions / 다음 액션
8. Source Entries / 원본 기록

This format applies to day, week, month, quarter, year, and project reports. The scope changes, but the structure does not.

## LLM Behavior

LLM summarization is optional. If `OPENAI_API_KEY` is set, Cho Works can call OpenAI Responses API with a strict JSON schema. Otherwise it uses the deterministic local summarizer.

LLM reports must:

- Output Korean report content.
- Use stable English JSON field names.
- Cite source entry ids for every claim.
- Avoid inventing projects, people, dates, KPIs, or outcomes.
- Fall back to local deterministic output if invalid.

## Data Changes

Add:

- `projects`: key, name, status, goal, health, target date, and metadata.
- `work_items`: Jira-like cards linked to projects and source entries.
- structured report columns on `summaries`: JSON payload, schema version, generation mode, model, and error.

## Pet Direction

The pet becomes a visual parrot companion. It should be beautiful, calm, and expressive, with status driven by logging consistency rather than productivity judgment.

The first implementation uses a CSS parrot component so the app has no external asset dependency.

## Verification

Tests must cover:

- Work report schema and markdown rendering.
- Deterministic fallback when no API key exists.
- Valid fake LLM report path.
- Project creation/listing.
- Automatic work item creation from entries.
- Board grouping by status.
- Web Projects and Board pages.
- Parrot dashboard rendering.

