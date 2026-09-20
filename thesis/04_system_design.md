# Chapter 4: System Design

This chapter describes the design of the ProcessMind framework — the system built to address the research gap identified in Chapter 2. The chapter covers the overall pipeline architecture, the five extractor configurations, the BPMN engineering pipeline, the two orchestration engines, and the evaluation harness.

## 4.1 Design Principles

Three principles guided the design:

1. **Separation of structure and enrichment.** Control-flow structure comes from deterministic, provably-sound algorithms (the Inductive Miner). The LLM is confined to semantic enrichment (naming activities, inferring actors, generating recommendations) where errors are recoverable. This prevents the LLM from being the source of structural invalidity.

2. **Offline-first.** The pipeline is fully functional with zero API keys. The deterministic rule parser is the guaranteed extraction path. LLM extraction is an optional enhancement with the same validation gate.

3. **Identical evaluation criteria.** All five extractor configurations (E1–E6) are evaluated on identical inputs with identical measures via the same harness. This is the prerequisite for the comparative evaluation that RQ2–RQ4 require.

## 4.2 Pipeline Architecture

The pipeline is a five-stage linear flow with a conditional feedback edge:

```
SOP text (.md/.txt) ─┐
                      ├─► Ingestion ─► Modeler ─► Validator ─┬─► Optimizer ─► Export
Event logs (.csv/.xes)─┘                                     │
                                         ▲                   │
                                         └── feedback (≤2 retries) ◄┘
```

The same `ProcessModel` artifact flows through all stages. Each stage is a pure function with typed inputs and outputs (all Pydantic models, JSON-serialisable). The stage contract is:

| Stage | Input | Output |
|---|---|---|
| Ingestion | File path or raw text | `IngestedDocument` |
| Modeler | `IngestedDocument` (+ optional LLM feedback) | `ModelerOutput(model, method, validation, warnings)` |
| Validator | `ProcessModel` | `ValidationReport` |
| Optimizer | `ProcessModel` (+ optional `LogSummary`) | `OptimizerOutput(report, tobe_model)` |
| Export | Pipeline state | Artifact files + `PipelineResult` |

## 4.3 The Ingestion Agent

The ingestion agent (`agents/ingestion.py`) normalises heterogeneous inputs into a canonical `IngestedDocument`. Key responsibilities:

- **File and raw-text ingestion** with path-vs-text disambiguation (a guard prevents the agent from misreading text as a file path).
- **Metadata header parsing** — a `Key: value` header is parsed into a `metadata` dict, with fields for `Process`, `Roles`, and `Domain`.
- **Markdown stripping** — markdown syntax is removed, wrapped lines are rejoined, and boilerplate sections (Purpose, Scope, Controls, ...) are suppressed.
- **Sentence segmentation** — the cleaned text is segmented into a step list for the parser.
- **Event-log detection** — CSV and XES files are detected by header fingerprinting and routed to the mining pathway rather than the text extraction pathway.

## 4.4 The Process Modeler Agent

The modeler (`agents/modeler.py`) is the central extraction component. It has two extractor pathways that funnel into the same validator:

### 4.4.1 E1: Offline Rule Parser

The offline rule parser (`agents/offline_parser.py`) implements a deterministic frontier state machine over the step stream. It is the research baseline and the guaranteed offline extraction path.

**Decision detection:** `if <condition>` starts a new XOR branch; `otherwise` continues the alternative branch. A negation-pair continuation links the post-decision continuation: "If complete, notify manager" after "If incomplete, repeat" continues the No-branch, not the Yes-branch.

**Parallel detection:** `while <activities>` or `meanwhile` starts an AND split. The parallel block ends at an explicit join marker (`in both cases`, `once both are complete`) or implicitly at the next decision node.

**Rework loops:** `returns to <target>` or `restart from <target>` creates a backward edge. Target matching is fuzzy (stemmed token similarity ≥ 0.45) to handle minor name variations between the loop reference and the target node name. Rework branches are routed through an explicit XOR merge to maintain well-formedness.

**Actor detection:** A role registry (specific role names mapped to standardised lane names) is applied first. Unrecognised roles are matched against a generic role grammar (verb-noun patterns, passive voice subjects) and a system-actor lexicon (words indicating automation: "send", "notify", "create in system").

**Task kind inference:** Tasks with system-verb patterns (send, notify, create, update, generate) are classified as `serviceTask`; tasks with human-verb patterns (review, approve, check, investigate) are classified as `userTask`.

### 4.4.2 E2 and E3: LLM Extractors

The LLM pathway (`agents/modeler.py`, `_run_llm` method) performs schema-guided JSON extraction. The prompt includes: (a) the full `ProcessModel` JSON schema with field descriptions; (b) 3–5 in-context examples from related SOPs; (c) explicit instructions on BPMN semantics (gateway types, task types, sequence flow direction); and (d) a requirement to output only the JSON object, no explanatory text.

The LLM provider abstraction (`llm/providers.py`) handles OpenAI-compatible endpoints (including Groq, OpenRouter, and local Ollama), JSON mode, retries on API errors, and defensive parsing of malformed responses (stripping code fences, fixing trailing commas, extracting the outermost JSON object).

E2 (single-shot) passes the document to the LLM once and accepts the result. E3 (self-correction) adds a validate-and-retry loop: if the structural validator reports errors, corrective feedback is generated and the LLM is re-prompted with the error list (up to 2 retries).

Both pathways fall through to the offline parser on any LLM error, ensuring the pipeline never fails silently.

## 4.5 Structural Validation and Auto-Repair

The structural validator (`bpmn/validate.py`) checks the produced `ProcessModel` against BPMN 2.0 structural rules:

- Every node is reachable from the start event and can reach the end event.
- All sequence flow references point to valid source and target nodes.
- Gateway directions (split, join, or mixed) are consistent with the surrounding flow structure.
- No dangling nodes, no pass-through gateways, no unlabelled XOR splits.

If validation fails and the extractor is LLM-based, the self-correction loop (E3) retries with feedback. If retry is exhausted or the extractor is the rule parser, an auto-repair step (`bpmn/validate.py`, `repair_model`) applies targeted patches: adding missing join gateways, removing dangling flows, rerouting broken edges. The repaired model is validated again; if it still fails, the pipeline aborts with a descriptive error rather than producing a potentially invalid output.

## 4.6 BPMN Engineering

### 4.6.1 Layout Engine

The layout engine (`bpmn/layout.py`) implements a Sugiyama-style layered layout algorithm to produce deterministic, overlap-free BPMN diagram coordinates:

1. **Back-edge removal** — rework edges are identified and temporarily removed.
2. **Longest-path ranking** — each node is assigned to a rank (layer) based on longest path from the start event.
3. **Barycenter ordering** — nodes within each rank are ordered to minimise crossing by sweeping over predecessor positions.
4. **Lane stacking** — lanes are ordered by first-appearance of their nodes.
5. **(lane, rank) slotting** — each node is assigned a (lane, rank) slot; conflicts are resolved by slot expansion.
6. **Waypoint computation** — orthogonal 4-point waypoints are computed for each flow.

Rework back-edges are routed below the pool to avoid obscuring the forward flow.

### 4.6.2 BPMN 2.0 XML Builder

The builder (`bpmn/builder.py`) emits the BPMN 2.0 XML with full Diagram Interchange (DI) support:

- **Collaboration** element with a `Participant` (pool) and `LaneSet` with per-lane `flowNodeRef` entries.
- **Typed tasks** (`userTask`, `serviceTask`, `sendTask`, `manualTask`), **events** (`start`, `intermediate`, `end`), and **gateways** (`XOR`, `AND`).
- **Gateway direction** attributes (`gatewayType`, `direction`).
- **`conditionExpression`** on labelled sequence flows from XOR gateways.
- **`documentation`** element carrying source provenance.
- **Complete DI** — `BPMNDiagram`, `BPMNPlane`, `BPMNShape` (with `bounds`), and `BPMNEdge` (with `waypoints`) elements.

Generated BPMN files are verified to import into bpmn-js (Camunda) without errors.

## 4.7 The Mining Pathway (E4, E6)

The mining pathway handles event-log inputs (CSV or XES) and produces discovered `ProcessModel` instances without any SOP text.

### 4.7.1 Event Log Loading

The log loader (`mining/event_log.py`) supports CSV (with header aliases for SAP, ServiceNow, Jira, and generic column names) and IEEE XES formats. Corrupt rows are skipped with descriptive warnings. Per-activity statistics are computed: frequency, median wait time (time before the activity), rework rate (fraction of cases that visit the activity more than once), and a composite bottleneck score (0.7 × normalised median wait + 0.3 × rework rate).

### 4.7.2 E4: DFG Discovery

The DFG miner (`mining/dfg.py`) computes the directly-follows relationship from the event log and builds a weighted directed graph. A frequency threshold (default: 0.01 of maximum edge frequency) filters noise edges. XOR gateways are induced where an activity has multiple outgoing directly-follows edges. AND gateway pairs are detected via the footprint discriminator: mutual A→B and B→A relationships become an AND split/join pair only when both A and B share the same entry and exit context outside the pair, discriminating parallel execution from rework loops.

### 4.7.3 E6: Inductive Miner

The Inductive Miner (`inductive/tree.py`) implements the Leemans-style cut hierarchy:

1. **xor cut** — separates mutually exclusive activity sets (activities that never co-occur in any trace).
2. **sequence cut** — separates activities that always occur in order (no interleaving).
3. **parallel cut** — separates activities that can occur in any order (mutual directly-follows, shared entry/exit context).
4. **loop cut** — separates a do-part from a redo-part (the activity set entered on loop entry vs the set that causes re-entry).

Cuts are applied recursively. If no cut applies, the flower model (accepts all traces) is returned. A soundness guard rejects parallel cuts when any trace touches only one side of the partition — a condition where naive parallel projection would lose language. The resulting process tree is converted to BPMN via `inductive/tree_bpmn.py`, which infers gateway direction (split vs join) from the flow topology around each gateway.

### 4.7.4 Token-Replay Conformance

The replay engine (`inductive/replay.py`) performs bounded token-based replay fitness. A token is placed at the start event; log events are replayed by firing the corresponding activity in the model; XOR branches are resolved by selecting the branch whose guard condition matches the event; AND branches spawn tokens on all parallel paths. Cases where a token is unavailable or the model deadlocks are counted as failures. Fitness = (cases accepted) / (total cases).

Any `ProcessModel` is replayable — discovered models (DFG, Inductive) and extracted models (E1, E2, E3) — via the bridge converters in `inductive/convert.py`, which also infers gateway direction from flow topology for DFG models.

## 4.8 Orchestration Engines

Both orchestration engines run identical stage functions:

**BuiltinEngine** (`graph.py`): a sequential loop with an explicit validate-and-retry conditional. Stages are called in order; if validation fails, the state is updated with feedback and the modeler stage is called again.

**LangGraphEngine** (`graph.py`): a `StateGraph` over a `PipelineState` TypedDict with declared keys. The `validate → model` edge is conditional: if the validation report has errors and retry budget remains, the edge fires; otherwise, the pipeline proceeds to the optimizer.

A test (`test_langgraph_engine_equivalence`) asserts that both engines produce identical metrics and findings for all test cases, ensuring that the choice of engine is an implementation detail rather than a behavioural variable.

## 4.9 The Optimization Agent

The optimizer (`agents/optimizer.py`) produces both a diagnostic report and a To-Be model. Findings come from two sources:

1. **Static model patterns** — manual data-entry verbs, sequential human approval chains, manual handoffs between lanes, single points of failure (human lanes with > 50% of manual tasks).
2. **Event-log statistics** — top queue waits (highest median wait time before an activity) and rework loops (highest repetition rate within cases).

Three transformation rules are applied to produce the To-Be model: `R_AUTOMATE_ENTRY` converts entry tasks to service tasks with duration reduced to 30%; `R_PARALLEL_APPROVALS` rewires sequential approval chains into AND-split/AND-join blocks; `R_INTEGRATE_HANDOFF` converts notification tasks into platform service tasks.

Before/after metrics are computed for both models: task count, automation rate, and estimated critical path (longest path through the model, with rework edges excluded).

## 4.10 Export Pipeline

The export stage writes all artifacts for a pipeline run:

- `ProcessModel` as JSON.
- BPMN 2.0 XML.
- SVG (standalone diagram).
- draw.io mxGraph (with parent-relative geometry).
- Mermaid flowchart (per-lane subgraphs).
- Self-contained HTML analyst report (metric cards, As-Is/To-Be diagrams, findings, conformance section).
- Conformance report JSON (when run with a log).
- Bottleneck report JSON (when run with a log).
- Pipeline result JSON (timings, method, artifact manifest).

## 4.11 Configuration and Environment

All configuration is environment-driven. The key variables are:

| Variable | Purpose | Default |
|---|---|---|
| `PM_ENGINE` | `auto` \| `builtin` \| `langgraph` | `auto` (LangGraph if installed) |
| `PM_LLM_MODEL` | Model name | `gpt-4o-mini` |
| `PM_LLM_BASE_URL` | API base URL | `https://api.openai.com/v1` |
| `OPENAI_API_KEY` | API key | none |
| `PM_LLM_TIMEOUT` | Request timeout (s) | 180 |
| `PM_OUTPUT_DIR` | Output directory | `outputs` |

The `resolve_engine()` function auto-detects LangGraph availability and selects the engine accordingly. The pipeline gracefully falls back to the builtin engine when LangGraph is not installed, ensuring reproducibility across environments.