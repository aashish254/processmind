# Software Requirements Specification — ProcessMind

**Enterprise AI Process Mining & BPMN Automation**
Version 1.0 · September 2026 · Capstone project, Systems Analyst track

---

## 1. Introduction

### 1.1 Purpose
This document specifies the requirements for **ProcessMind**, a software system that automatically converts unstructured enterprise process documentation (Standard Operating Procedures) and raw event logs into standards-compliant BPMN 2.0 process models, identifies operational bottlenecks, and produces As-Is and To-Be process architectures.

Intended audience: examiners, reviewers, and developers maintaining the project.

### 1.2 Scope
ProcessMind is a standalone Python pipeline with a CLI and an optional REST API.

**In scope**
- Ingestion of SOP documents (`.md`, `.txt`) and event logs (CSV with case id / activity / timestamp / resource).
- Multi-agent extraction of process models via LLM providers **or** a deterministic offline rule engine.
- Discovery of process models from event logs (DFG mining).
- Structural validation and auto-repair of process models.
- BPMN 2.0 XML export with diagram interchange (DI) that opens in Camunda Modeler, bpmn.io, draw.io and Lucidchart (via draw.io import).
- Bottleneck analysis combining static model patterns and event-log statistics (queue waits, rework, variants).
- As-Is → To-Be transformation with applied recommendations and before/after metrics.
- Exports: BPMN, draw.io, Mermaid, SVG, JSON, HTML analyst report.
- An evaluation harness measuring extraction quality against gold annotations.

**Out of scope**
- Live process mining on streaming data (batch CSV only in v1.0).
- Editing/approval workflow for analysts (export targets existing BPMN tooling).
- Direct execution of generated BPMN in a workflow engine.
- Multi-tenancy, authentication, persistence beyond the artifact directory.

### 1.3 Definitions
| Term | Definition |
|---|---|
| SOP | Standard Operating Procedure — narrative document describing a process |
| BPMN 2.0 | Business Process Model and Notation, OMG standard (XML interchange + DI) |
| DFG | Directly-Follows Graph — frequency-relational view of an event log |
| As-Is / To-Be | Current-state / target-state process architecture |
| Rework loop | A flow edge that returns to an earlier activity within one case |
| Gateway | BPMN control-flow construct (XOR = exclusive decision, AND = parallel) |

### 1.4 References
- OMG, *Business Process Model and Notation (BPMN) 2.0.2*, 2011.
- van der Aalst, W., *Process Mining: Data Science in Action*, 2nd ed., 2016.
- IEEE 830-1998, *Recommended Practice for Software Requirements Specifications*.
- LangGraph documentation (state machines for LLM agents), 2024–2026.

---

## 2. Overall Description

### 2.1 Product perspective
ProcessMind sits between document repositories/ERP exports and the analyst's BPMN toolchain. It produces first-draft process models and evidence-based improvement hypotheses that an analyst reviews and refines.

### 2.2 User classes
| User class | Interaction | Technical skill |
|---|---|---|
| Business/Systems Analyst | CLI `demo`/`mine`, reads HTML report, opens BPMN in draw.io | Medium |
| Process miner | CLI `analyze-log`, interprets variant/wait statistics | High |
| Developer / researcher | Python API, evaluation harness, LLM configuration | High |
| Auditor / stakeholder | Reads exported HTML report only | Low |

### 2.3 Operating environment
- Python ≥ 3.10 (developed on 3.11, macOS arm64; CI on Ubuntu).
- Core dependency: `pydantic ≥ 2`. Optional: `langgraph`, `fastapi`/`uvicorn`, `pytest`.
- Fully offline capable; optional outbound HTTPS to LLM providers.

### 2.4 Constraints
- C1: Must run with **no network access and no API keys** (deterministic fallback).
- C2: Generated BPMN must pass structural validation and import into bpmn-js without errors.
- C3: Same input must produce identical outputs (determinism) to keep the evaluation reproducible.
- C4: Both orchestration engines (builtin, LangGraph) must be semantically equivalent.

### 2.5 Assumptions
- SOPs are written in English, largely imperative/third-person, one action per sentence.
- Event logs are flat per-event CSVs (the dominant export shape of SAP/ServiceNow/Jira).
- Gold annotations are produced by a human analyst for the evaluation corpus.

---

## 3. User Stories (with acceptance criteria)

### US-01 — Ingest an SOP document
> As a **systems analyst**, I want to point the tool at an SOP file so that I get a structured process model without manual modelling.

**Acceptance criteria**
- Metadata headers (`Process:`, `Roles:`) populate document metadata.
- Boilerplate sections (Purpose, Scope, Controls) are excluded from extraction.
- Every extracted node records its source sentence (provenance).

### US-02 — Generate BPMN 2.0 automatically
> As an **analyst**, I want a `.bpmn` file that opens directly in my existing tooling.

**Acceptance criteria**
- Valid XML with BPMN/MODEL and BPMN/DI namespaces; collaboration, pool, per-role lanes.
- Every node has a shape; every flow has an edge with orthogonal waypoints.
- Imports into bpmn-js with zero errors (verified in CI-style checks).

### US-03 — Mine a process from an event log
> As a **process miner**, I want to discover the *enacted* process from raw logs.

**Acceptance criteria**
- Accepts `case_id, activity, timestamp[, resource, lifecycle]` with common header aliases.
- Produces a validated BPMN model with XOR split/join gateways at branch points.
- Reports per-activity frequency, median/mean wait, rework rate, top-5 variants.

### US-04 — Find bottlenecks with evidence
> As a **stakeholder**, I want bottlenecks quantified, not guessed.

**Acceptance criteria**
- Static findings: manual data entry, sequential approvals, manual handoffs, single points of failure.
- Log findings: top queue waits (with median values) and rework loops (with rates).
- Each finding cites affected task names and numeric evidence.

### US-05 — Produce a To-Be model
> As an **analyst**, I want concrete, applied improvement transformations.

**Acceptance criteria**
- Recommendations are node-targeted and marked applied/advisory.
- Applied transforms: automate tasks (→ service tasks), parallelize approval pairs (AND gateways), integrate handoffs.
- To-Be model passes the same validation; before/after metrics computed (automation rate, estimated critical path).

### US-06 — Run without any LLM
> As a **reviewer without API keys**, I want the full pipeline to work offline.

**Acceptance criteria**
- `PM_LLM_PROVIDER` unset ⇒ offline rule parser used; method recorded as `offline-rules`.
- LLM failure at runtime ⇒ automatic fallback with a warning, never a crash.

### US-07 — Choose the orchestration engine
> As a **researcher**, I want to swap the orchestration framework (LangGraph vs builtin) without changing results.

**Acceptance criteria**
- `--engine langgraph|builtin|auto`.
- Both engines return equal `summary_metrics()` and finding titles on the same input (tested).

### US-08 — Evaluate extraction quality
> As an **examiner**, I want quantified extraction quality against gold models.

**Acceptance criteria**
- Reports task precision/recall/F1 (token-stem matching ≥ 0.5), actor F1, gateway-count error, rework error.
- Writes `eval_report.json` and a human-readable `eval_report.md`.

### US-09 — Serve results over HTTP
> As a **developer**, I want to integrate ProcessMind into other tooling.

**Acceptance criteria**
- `POST /api/v1/mine` (text → model + BPMN + findings), `POST /api/v1/analyze-log` (CSV upload), `GET /api/v1/health`.
- Malformed input ⇒ HTTP 422 with a descriptive message.

### US-10 — Trust the output
> As an **auditor**, I want determinism and provenance.

**Acceptance criteria**
- Identical inputs produce identical artifacts; every node carries `source_text`.
- `validate` command reports structural errors/warnings for any saved artifact.

---

## 4. Use Cases

### UC-01: Mine an SOP end-to-end
1. Analyst runs `mine sop.md --log events.csv -o out/`.
2. Ingestion normalises the document; Modeler extracts the model.
3. Validator checks structure; on failure the engine retries/repairs (max 2).
4. Optimizer computes findings; applies recommendations into a To-Be model.
5. Export stage writes 10+ artifacts; CLI prints the summary.
   **Extensions:** 3a. Validation still failing after retries ⇒ auto-repair guarantees export. 3b. LLM error ⇒ offline fallback.

### UC-02: Discover a process from a log
1. Miner runs `analyze-log export.csv`.
2. Log loader parses timestamps, skips corrupt rows.
3. DFG discovery filters edges below threshold and induces gateways.
4. Optimizer adds queue/rework findings; exports follow the same path as UC-01.

### UC-03: Evaluate an extractor
1. Researcher runs `eval`.
2. Harness ingests each gold-annotated document, extracts, matches tasks (greedy token-stem similarity), computes P/R/F1, writes JSON+MD reports.

### Use-case / requirement traceability

| Use case | Requirements | User stories |
|---|---|---|
| UC-01 | FR-01…FR-06, FR-10, NFR-1..3 | US-01, 02, 04, 05, 06, 10 |
| UC-02 | FR-07…FR-09 | US-03, 04 |
| UC-03 | FR-11, FR-12 | US-08 |
| API integration | FR-13 | US-09 |

---

## 5. Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The system shall normalise SOP documents into steps with metadata, sections and word/step statistics. | Must |
| FR-02 | The Modeler Agent shall produce a ProcessModel (nodes, typed flows, lanes, task kinds, durations, automation flags) from SOP steps. | Must |
| FR-03 | The offline parser shall reconstruct control flow from discourse markers: decisions (`if`/`otherwise`/negation pairs), parallel work (`while`), joins (`in both cases`), rework (`returns to`). | Must |
| FR-04 | The Modeler Agent shall use the configured LLM provider when available, validate its JSON against the schema, and retry with validation feedback up to 2 times. | Should |
| FR-05 | The Validator shall detect: missing start/end, dangling nodes, unreachable nodes, bad flow references, pass-through gateways, unlabeled XOR splits, implicit merges; the Repairer shall fix error-class issues automatically. | Must |
| FR-06 | The exporter shall emit BPMN 2.0 XML including collaboration, participant, laneSet, typed tasks, gateway direction attributes, condition expressions, and complete DI (shapes, bounds, orthogonal waypoints). | Must |
| FR-07 | The log miner shall parse CSVs with header aliases and tolerant timestamp formats, skipping corrupt rows. | Must |
| FR-08 | The miner shall compute per-activity frequency, case coverage, median/mean/total wait, rework count/rate, start/end activities, and top-5 variants. | Must |
| FR-09 | The DFG miner shall induce a ProcessModel from filtered directly-follows edges with XOR split/join gateways and resource-based lanes. | Must |
| FR-10 | The Optimizer shall generate findings (manual entry, sequential approvals, handoffs, SPOF, queue waits, rework) and recommendations, and apply automation/parallelization/integration transforms to produce a validated To-Be model with before/after metrics. | Must |
| FR-11 | The evaluation harness shall compute task P/R/F1 via greedy token-stem matching, actor F1, gateway and rework count errors against gold JSON. | Should |
| FR-12 | Evaluation outputs shall be machine-readable (`eval_report.json`) and human-readable (`eval_report.md`). | Should |
| FR-16 | When an SOP is mined with a matching event log, the pipeline shall produce a conformance report: fuzzy-matched activities, documented-only and enacted-only activities, directly-follows differences with precision/recall indicators, and rework-drift detection, written as `_conformance.json` and rendered in the HTML report. | Should |
| FR-17 | Event logs shall be accepted in CSV and XES (IEEE standard) formats, dispatched by content, with the XES loader understanding namespaced and alias-bearing attribute keys. | Should |
| FR-13 | A FastAPI service shall expose `/api/v1/health`, `/api/v1/mine`, `/api/v1/analyze-log` with 422 responses for malformed input. | Could |
| FR-14 | The CLI shall provide `mine`, `analyze-log`, `validate`, `eval`, `demo`, `serve` with non-zero exit codes on failure. | Must |
| FR-15 | The pipeline shall run under both orchestration engines with equivalent results. | Should |

---

## 6. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | **Offline capability** — full functionality with no network; LLM features degrade gracefully. |
| NFR-2 | **Determinism** — identical input ⇒ identical artifacts (verified by tests). |
| NFR-3 | **Performance** — a 20-step SOP processes in < 5 s offline; a 3,000-event log in < 10 s (achieved: ~1–2 s). |
| NFR-4 | **Interoperability** — BPMN opens in bpmn.io/Camunda/draw.io/Lucidchart-import; draw.io opens in diagrams.net. |
| NFR-5 | **Testability** — ≥ 100 automated tests; currently 125 passing. |
| NFR-6 | **Maintainability** — typed pydantic contracts; pure functions for extraction; engines share stage implementations. |
| NFR-7 | **Portability** — Python ≥ 3.10, stdlib-first; optional extras isolated. |
| NFR-8 | **Auditability** — provenance (`source_text`) on every extracted node; artifact manifests in `_result.json`. |

---

## 7. Data Model (ER, mermaid)

```mermaid
erDiagram
    INGESTED_DOCUMENT ||--o{ SECTION : "groups"
    INGESTED_DOCUMENT ||--o{ STEP : "yields"
    INGESTED_DOCUMENT ||--o|| PROCESS_MODEL : "extracted into"
    PROCESS_MODEL ||--o{ NODE : contains
    PROCESS_MODEL ||--o{ FLOW : contains
    NODE ||--o{ FLOW : "source of"
    NODE ||--o{ FLOW : "target of"
    PROCESS_MODEL ||--o|| VALIDATION_REPORT : "checked by"
    PROCESS_MODEL ||--o|| BOTTLENECK_REPORT : "analysed by"
    BOTTLENECK_REPORT ||--o{ FINDING : lists
    BOTTLENECK_REPORT ||--o{ RECOMMENDATION : lists
    BOTTLENECK_REPORT ||--o|| MODEL_METRICS : "As-Is"
    BOTTLENECK_REPORT ||--o|| MODEL_METRICS : "To-Be"
    BOTTLENECK_REPORT ||--o| LOG_SUMMARY : "evidence from"
    PROCESS_MODEL ||--o|| PROCESS_MODEL : "transformed into To-Be"
    LOG_SUMMARY ||--o{ ACTIVITY_STATS : contains
    LOG_SUMMARY ||--o{ VARIANT : contains
    EVENT_LOG ||--o{ EVENT : contains
    EVENT_LOG ||--o|| LOG_SUMMARY : "summarised into"
    GOLD_ANNOTATION ||--o|| PROCESS_MODEL : "evaluated against"
```

Key entities: `ProcessModel` (id, name, nodes[], flows[], metadata) is the hub; `Node` carries type/kind/actor/duration/automation; `Finding`/`Recommendation` reference node ids; `LogSummary` carries activity statistics and variants.

---

## 8. Acceptance & Verification

- Unit + integration tests (`pytest`, 125 cases) cover every FR above.
- BPMN compatibility verified by importing generated files into bpmn-js 17 (observed: `importXML` success, zero errors).
- draw.io files verified in the official GraphViewer.
- Evaluation harness reports task F1 = 1.00 on the curated gold corpus (co-designed SOPs; see RESEARCH.md §5 for scope of this claim).
- Demo command exercises the full matrix: 3 SOPs (2 with logs) + 1 standalone log analysis.
