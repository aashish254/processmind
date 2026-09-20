# ProcessMind — System Architecture

## 1. Architectural overview

ProcessMind is a **pipeline of agents over typed state**. One set of stage functions is orchestrated two ways — a dependency-free builtin engine and a LangGraph `StateGraph` — guaranteeing identical outputs (asserted by tests).

```
                       ┌────────────────────────────────────────────────────┐
 inputs                │                orchestration (graph.py)            │
 SOP .md/.txt ────────►│  ingest → model → validate ─┬→ optimize → export    │
 event log .csv ──────►│        ▲                    │ conditional edge      │
                       │        └── feedback (≤2) ◄──┘                       │
                       └────────────────────────────────────────────────────┘
```

### Stage contracts (all pydantic, all JSON-serialisable)

| Stage | Input | Output |
|---|---|---|
| Ingestion | path / raw text | `IngestedDocument` (steps, sections, metadata, stats) |
| Modeler | `IngestedDocument` (+ optional LLM feedback) | `ModelerOutput(model, method, validation, warnings)` |
| Validator | `ProcessModel` | `ValidationReport` (issues with codes/severity) |
| Optimizer | `ProcessModel` (+ optional `LogSummary`) | `OptimizerOutput(report, tobe_model)` |
| Export | full state | artifact files + `PipelineResult` |

`ProcessModel` is the hub artifact: nodes (start/end/task/xor/and), flows (labels = branch conditions), lanes (actors), task kinds (user/service/send/…), durations, automation flags, provenance.

## 2. The agents

### 2.1 Ingestion Agent
- Reads files or raw text; **never** misreads text as a path (guarded `Path` probing).
- Parses a lightweight `Key: value` metadata header (`Process`, `Roles`, `Domain`).
- Strips markdown, joins wrapped lines, segments sentences, **skips boilerplate sections** (Purpose, Scope, Controls, …).
- Detects event-log CSVs by header-cell fingerprinting and routes them to the mining pathway; malformed logs raise a descriptive `ValueError`.

### 2.2 Process Modeler Agent — two extractors, one validator
**LLM extractor** (optional): schema-guided prompt (nodes referenced by *name*, more reliable for LLMs), strict JSON parsing with code-fence/trailing-comma repair, pydantic IR validation, name→id resolution, duplicate node dedupe. On validation failure the engine re-prompts with the error list (bounded self-correction, max 2), then auto-repairs.

**Offline rule parser** (always available; the research baseline): a frontier state machine over the step stream:
- decisions via `if …, …` / `otherwise` / negation-pair continuation ("If complete, …" after "If incomplete, …" continues the No-branch),
- parallel blocks via `while`/`meanwhile` (AND split/join),
- explicit joins via `in both cases`, implicit joins when both branches have content,
- rework loops via `returns to …` with fuzzy task matching (stemmed token similarity ≥ 0.45) routed through an explicit XOR merge,
- branch-termination semantics: branches ending in end events or rework loops are excluded from downstream merges,
- actor detection from the role registry + generic role grammar + system-actor lexicon; task kind/duration/automation inferred from lexical cues.

Design intent: the parser is *predictable* (documented markers, deterministic), which makes it a fair baseline for the LLM comparison and a reliable fallback. Both extractors pass through the same validator, so downstream quality is uniform.

### 2.3 Optimization Agent — the critic
Findings from two sources:
1. **Static model patterns**: manual data-entry verbs, sequential human approval chains (longest task→task keyword chain), manual communication handoffs (word-boundary matched), single points of failure (human lane with > 50% of manual tasks).
2. **Event-log statistics**: top queue waits (median wait before an activity), rework loops (repetition rate within cases).

Recommendations are concrete node-targeted transforms, and three are *applied* to produce the **To-Be model**: `R_AUTOMATE_ENTRY` (tasks → service tasks, duration × 0.3), `R_PARALLEL_APPROVALS` (AND split/join rewiring with full boundary-flow handling), `R_INTEGRATE_HANDOFF` (notifications → platform service tasks). Metrics (task counts, automation rate, estimated critical path via longest-path with cycle breaking) are computed for both models.

### 2.4 BPMN builder & layout
- **Layout** (Sugiyama-lite): back-edge removal → longest-path ranking → barycenter ordering sweeps → lane stacking (first-appearance order) → (lane, rank) slotting → orthogonal 4-point waypoints; back edges (rework) routed below the pool. Deterministic and overlap-free (tested).
- **Builder**: emits collaboration/participant (pool), laneSet with flowNodeRefs, typed tasks (`userTask`, `serviceTask`, `sendTask`, …), gateway direction attributes, `conditionExpression` on labeled XOR splits, `documentation` provenance, and full DI (shapes, bounds, waypoints). Verified to import into bpmn-js 17 with zero errors.

### 2.5 Mining pathway
`load_log` (header aliases, tolerant timestamps, corrupt-row skipping) → `compute_summary` (frequency, waits, rework, variants, composite bottleneck score = 0.7·normalised median wait + 0.3·rework) → `discover_dfg` (frequency-thresholded directly-follows edges → XOR split/join induction → resource lanes).

## 3. Orchestration

- **BuiltinEngine**: sequential stages with an explicit retry loop.
- **LangGraphEngine**: `StateGraph` over the same `PipelineState` TypedDict (all keys declared — LangGraph drops undeclared keys, an early bug we caught by engine-equivalence testing) with a conditional `validate → model` feedback edge.

Both engines run identical stage functions; `test_langgraph_engine_equivalence` asserts equal metrics and findings.

## 4. Cross-cutting concerns
- **Configuration**: environment-driven (`PM_*`, standard provider vars); `resolve_engine` picks LangGraph when importable.
- **Errors**: descriptive `ValueError`s surfaced by the CLI as exit code 2; API as HTTP 422.
- **Determinism**: no wall-clock or randomness in extraction/layout; seeded synthetic logs.
- **Observability**: per-stage timings in `PipelineResult.timings`; artifact manifest in `_result.json`.

## 5. Repository layout
See README “What's in the box”. Hand-authored architecture diagrams: `diagrams/*.drawio` (As-Is/To-Be for both enterprise scenarios + this system's architecture) — verified in the official draw.io GraphViewer.
