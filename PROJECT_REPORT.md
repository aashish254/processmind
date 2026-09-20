# PROCESSMIND — PROJECT REPORT & HANDOFF DOCUMENT

**Enterprise AI Process Mining & BPMN Automation**
Version 1.2 · Date: 2026-09-17 · Status: complete, tested, demo-verified
Location: `/Users/acc2/Downloads/cap 1` · Python venv: `.venv` (Python 3.11, Homebrew)

> This is the single working document for the project: what exists, how it works,
> what was verified, what is weak, and what to do next. Read this first when
> resuming work.

---

## 0. WHAT WAS ADDED LAST (v1.1 → v1.2)

1. **AND-gateway discovery from event logs** — `mining/dfg.py` now detects
   parallel blocks: a mutual DFG pair (A→B and B→A) becomes an AND split/join
   only when both activities share the same entry *and* exit context outside
   the pair (footprint discriminator) — rework loops share only one side and
   correctly stay loops. The vendor log has a planted parallel pair
   ("Compliance Screening" / "Financial Risk Assessment", executed in either
   order per case) which is discovered as an AND block matching the SOP's
   documented parallelism.
2. **Trace-weighted footprint fitness** in conformance — every observed
   handover is replayed on the documented model (activity-matched, AND blocks
   accept any interleaving); reported as `fitness` in the report + JSON and as
   a report card. Current: IT 75%, Vendor 56%.
3. **Messy legacy SOP** (`inputs/legacy_it_purchase_sop.txt` + gold) — passive
   voice, coreferences, run-ons, no metadata header. Extraction scores
   **F1 = 0.10** on it vs 1.00 on the curated trio: the honest external-validity
   datapoint that motivates the LLM-extractor experiment.
4. XES support, conformance drift reports, sample XES, artifact browser hub
   (`outputs/index.html` on port 8734) — added in v1.1 (see §2/§4).

---

## 1. WHAT THE PROJECT IS

ProcessMind is a multi-agent Python pipeline for the capstone topic
*"Enterprise AI Process Mining & BPMN Automation"* (target role: Systems
Analyst / ICT Business Analyst).

**The problem it solves:** analysts spend weeks reading SOPs and interviewing
staff to map a process before they can improve it. ProcessMind ingests:

1. **Unstructured SOP documents** (`.md`/`.txt` narratives), and
2. **Event logs** (CSV *or* IEEE XES; `case_id, activity, timestamp, resource`),

and automatically produces:

- a **structured JSON process model** (`ProcessModel`: nodes, flows, lanes, task kinds),
- a **BPMN 2.0 file with full diagram layout** — verified to open in
  bpmn-js / Camunda Modeler / draw.io (draw.io files also import into Lucidchart),
- **bottleneck findings with numeric evidence** (queue waits, rework rates,
  sequential approvals, manual entry, single points of failure),
- an **applied To-Be model** — recommendations are actually transformed into a
  second BPMN, with before/after metrics,
- a **conformance report** (documentation drift between the documented SOP
  process and the enacted log process),
- an **HTML analyst report** embedding both diagrams, all findings, and analytics,
- exports: draw.io, Mermaid, standalone SVG, model JSON, log stats JSON.

Three enterprise scenarios ship with the project and are fully tested:
**vendor onboarding**, **IT incident management**, **employee leave approval**.

**Key design principle:** the pipeline is *fully functional with zero API keys*
— a deterministic offline rule parser is the guaranteed extraction path; LLM
extraction (OpenAI-compatible / Anthropic) is an optional, higher-quality path
with the same validation gate.

---

## 2. WHAT HAS BEEN BUILT (complete inventory)

### 2.1 Core package `process_miner/` (~7,000 lines of Python)

| Module | What it does |
|---|---|
| `models.py` | All pydantic contracts: `ProcessModel`, `Node`, `Flow`, `IngestedDocument`, `ValidationReport`, `Finding`, `Recommendation`, `BottleneckReport`, `LogSummary`, `ConformanceReport`, `PipelineResult`. `ProcessModel` has rich helpers (adjacency, critical path with cycle-breaking, automation rate, fuzzy task finder, JSON round-trip). |
| `config.py` | Env-driven settings (`PM_ENGINE`, `PM_OUTPUT_DIR`, `OPENAI_API_KEY`, `PM_LLM_MODEL`, `PM_LLM_BASE_URL`, …). `resolve_engine()` picks LangGraph when importable. |
| `llm/providers.py` | Provider abstraction: OpenAI-compatible `/chat/completions` (JSON mode, retries), Anthropic Messages API, defensive JSON extraction (code fences, trailing commas, prose wrappers). Returns `None` when unconfigured → offline mode. |
| `llm/prompts.py` | Schema-guided extraction prompt (nodes referenced by *name* — more reliable for LLMs), optimization prompt, self-correction feedback template. |
| `agents/ingestion.py` | File/raw-text ingestion, metadata header parsing (`Process:`, `Roles:`), markdown stripping, sentence segmentation, boilerplate-section suppression (Purpose/Scope/Controls/…), CSV-vs-XES-vs-text detection with validation. Guards against misreading text as a path. |
| `agents/offline_parser.py` | **The deterministic extractor** (research baseline + offline fallback). A frontier state machine over the step stream: decisions via `if`/`otherwise` + negation-pair continuation; parallel blocks via `while`/`meanwhile` (AND split/join); joins via `in both cases` + implicit joins; rework loops via `returns to …` with fuzzy target matching routed through explicit XOR merges; branch-termination semantics (end-event/rework branches excluded from downstream merges); actor detection (role registry + generic role grammar + system lexicon); task kind/duration/automation inference; passive→imperative name normalisation. |
| `agents/modeler.py` | Dual-extractor agent: LLM-first (IR validation, name→id resolution, duplicate dedupe, validate→feedback retry ≤2, auto-repair) with automatic fallback to the offline parser. Records which method produced the model. |
| `agents/optimizer.py` | The critic. Findings from static model patterns (manual data entry verbs, longest sequential *human* approval chain, word-boundary handoff matching, SPOF per human lane) + log statistics (top queue waits, rework rates). Applies three transforms to build the To-Be model: `R_AUTOMATE_ENTRY` (→ service tasks, duration×0.3), `R_PARALLEL_APPROVALS` (AND split/join rewiring), `R_INTEGRATE_HANDOFF`. Computes before/after metrics (automation rate, manual steps, critical path). |
| `bpmn/layout.py` | Sugiyama-style layered layout: back-edge removal → longest-path ranking → barycenter sweeps → lane stacking → (lane, rank) slotting → orthogonal 4-point waypoints; rework back-edges routed below the pool. Deterministic, overlap-free (tested). |
| `bpmn/builder.py` | BPMN 2.0 XML: collaboration/participant (pool), laneSet with flowNodeRefs, typed tasks (userTask/serviceTask/sendTask/…), gateway direction attributes, `conditionExpression` on labeled XOR splits, `documentation` provenance, complete DI (shapes/bounds/waypoints). |
| `bpmn/validate.py` | Structural validator (missing start/end, dangling nodes, reachability, bad refs, pass-through gateways, unlabeled XOR splits, implicit merges) + auto-repair (guaranteed exportable model). |
| `mining/event_log.py` | CSV log loading (header aliases for SAP/ServiceNow/Jira, tolerant timestamps, corrupt-row skipping), per-activity frequency/wait/rework stats, top-5 variants, composite bottleneck score (0.7·normalised median wait + 0.3·rework). |
| `mining/dfg.py` | DFG discovery: frequency-thresholded directly-follows edges → BPMN with XOR split/join induction, resource-based lanes. |
| `mining/xes.py` | XES loader (namespaced/alias-tolerant) + writer + content-based dispatcher `load_event_log()`. |
| `conformance.py` | Documentation-drift analysis: fuzzy activity alignment, directly-follows comparison (gateway-skipping), drift classification (documented-not-enacted / enacted-not-documented / sequence mismatch / unexplained rework), DF precision & recall indicators. Rework explanation includes tasks transitively reachable from documented loop entry points. |
| `export/svg.py` | Standalone SVG renderer (reuses the BPMN layout): swimlanes, typed task colours, automation dots, gateway glyphs, labeled edges. |
| `export/drawio.py` | draw.io (mxGraph) exporter: pool → lanes → nodes with parent-relative geometry, orthogonal edges. |
| `export/mermaid.py` | Mermaid flowchart with per-lane subgraphs. |
| `export/html_report.py` | Self-contained print-ready HTML report: metric cards with deltas, As-Is/To-Be SVGs, findings/recommendations tables, conformance section, event-log analytics (activities + variants), Mermaid source, artifact manifest. |
| `graph.py` | Orchestration: one set of stage functions, two engines — `BuiltinEngine` (sequential, no deps) and `LangGraphEngine` (`StateGraph` + conditional validate→model feedback edge). Stage export writes 10–12 artifacts incl. `_result.json` manifest and runs conformance when a log is present. `run_pipeline()`, `analyze_log()`, `validate_artifact()`. |
| `cli.py` | Commands: `mine`, `analyze-log`, `validate`, `eval`, `demo`, `serve`. Clear exit codes; summary printer. |
| `api.py` | FastAPI: `GET /api/v1/health`, `POST /api/v1/mine`, `POST /api/v1/analyze-log`, `GET /api/v1/examples/{name}`; 422 on malformed input. |
| `evaluation.py` | Research harness: task P/R/F1 (greedy token-stem matching ≥0.5), actor F1, gateway/rework count errors vs gold JSON; writes `eval_report.json` + `.md`. |

### 2.2 Inputs, gold, diagrams, docs, tests

- `inputs/` — 3 SOPs (vendor onboarding, IT incident management, leave
  approval), 2 seeded synthetic CSV logs (250 / 300 cases) with **planted**
  bottlenecks + rework loops, and a sample XES log (`it_incident_events.xes`, 60 cases).
- `scripts/generate_logs.py` — seeded log generator (byte-reproducible).
- `eval/gold/` — human reference models (tasks/actors/gateways/rework) per SOP.
- `diagrams/` — 3 hand-authored draw.io files (5 pages): As-Is & To-Be system
  architecture for vendor onboarding AND IT incident management (with event-log
  evidence and impact targets), plus the ProcessMind system architecture.
- `docs/` — `SRS.md` (IEEE-830 style: 15 FRs, 8 NFRs, user stories, use cases,
  ER diagram, traceability), `ARCHITECTURE.md`, `RESEARCH.md` (RQs, method,
  results, threats to validity, thesis outline), `USER_STORIES.md`.
- `tests/` — **140 pytest cases, all passing** (~2 s runtime).
- `outputs/` — generated artifacts (regenerate with `make demo`); includes
  `index.html` (artifact browser hub) and two live interop check pages.
- `Makefile`, `.github/workflows/ci.yml` (3 Python versions), `pyproject.toml`.

### 2.3 Environment notes (important on this machine)

- System `python3` is blocked by an **Xcode license prompt** → use
  `/opt/homebrew/bin/python3.11`. The venv `.venv` was created with
  `--system-site-packages` and has pydantic, langgraph, fastapi, pytest, httpx.
- A local artifact server was used for browser verification:
  `./.venv/bin/python -m http.server 8734 --bind 127.0.0.1` from the project
  root, serving `outputs/index.html` at `http://127.0.0.1:8734/outputs/index.html`.

---

## 3. ARCHITECTURE (how it fits together)

```
            ┌───────────────────────────────────────────────────────────────┐
 INPUTS     │                     ORCHESTRATION (graph.py)                  │
 SOP ───────►  ingest ──► model ──► validate ──┬─► optimize ──► export        │
 event log ► (Ingestion   (Modeler   (Validator │   (Optimizer  (BPMN/SVG/     │
 CSV/XES     Agent)       Agent)     + retry    │    Agent)      drawio/HTML/  │
                     ▲         ▲        loop ≤2)  │        │      JSON/…)       │
                     │         └── LLM feedback ◄─┘        ▼                    │
                     │                                  To-Be model             │
 LLM providers ──────┘ (optional: OpenAI-compat / Anthropic / offline rules)   │
                                                                       │
                       conformance: documented (SOP) vs enacted (log) ◄─┘ + DFG discovery
            └───────────────────────────────────────────────────────────────┘
```

**Pipeline stages and contracts** (all pydantic, all JSON-serialisable):

1. **Ingestion** → `IngestedDocument` (steps, sections, metadata, stats) — or routes to the log pathway.
2. **Modeling** → `ModelerOutput(ProcessModel, method, validation, warnings)` — method is `offline-rules` or `llm:<provider>`.
3. **Validation** → `ValidationReport`; on errors the engine retries the modeler with the error list as feedback (≤2), then auto-repairs. Both engines share these exact stage functions.
4. **Optimization** → `OptimizerOutput(BottleneckReport, tobe_model)`; metrics computed for both models.
5. **Export** → writes `*_model.json`, `*_bpmn.bpmn`, `*_asis.svg`, `*_tobe_*`, `*_mermaid.mmd`, `*_process.drawio`, `*_log_stats.json`, `*_conformance.json`, `*_result.json`, `*_report.html`.
6. **Conformance** (only when SOP+log) → compares documented model vs DFG-discovered/log behaviour.

**Two extraction paths for text** (both funnel through the same validator):
- **Offline rule parser** — deterministic, no network; the research baseline.
- **LLM extractor** — schema-guided JSON IR; nodes referenced by name (more
  reliable for LLMs), then resolved to ids; retries with validator feedback.

**Data pathway for logs:** `load_event_log` (CSV|XES) → `compute_summary`
(stats, variants, bottleneck scores) → `discover_dfg` (BPMN induction) → same
optimizer/export stages.

**Engine equivalence is asserted by tests** — swapping LangGraph for the
builtin engine is a research variable, not a rewrite.

---

## 4. WHAT WAS VERIFIED (evidence, not claims)

| Check | Result |
|---|---|
| pytest suite | **140/140 passing** (models, agents, BPMN/DI completeness, no-overlap layout, validation/repair, mining stats, DFG, conformance, XES, exports, both engines equivalent, CLI end-to-end, API) |
| BPMN interop | Generated `.bpmn` imported into **bpmn-js 17** in a real browser — `importXML` succeeded with **zero errors** (`window.__bpmnOpened = true`) |
| draw.io interop | All 3 diagram files (5 pages) render in the **official GraphViewer** (verified via screenshot) |
| HTML report | Rendered and screenshotted in-browser: metric cards with deltas, findings tables with real evidence, recommendations with applied/advisory state, conformance section, log analytics |
| Determinism | Same input → identical models/layouts/artifacts (tested) |
| Eval harness | Task F1 = **1.00** on all three SOPs vs gold (controlled-vocabulary ceiling — see §6) |
| Demo | `make demo` runs 3 SOPs (2 with logs) + prints per-run summaries; all 6 BPMN artifacts pass `validate` |
| Planted-bottleneck detection | "Compliance Screening" (5.1 d median wait), "Financial Risk Assessment" (3.6 d), "Await Vendor Documents" (2.9 d), "Await User Response" (12.8 h) all rank top-3; rework rates 29% / ~19% detected accurately |
| Before/after | Vendor: cycle 54→37 min (−31%), automation 38%→46%; IT: 84→70 min, 27%→40%; Leave: 33→26 min, 50%→62% |
| Conformance | IT: 11/15 matched, DF recall 82%; Vendor: 9/13 matched, recall 50% (vocabulary drift — reported honestly, see §6) |

---

## 5. HOW TO WORK WITH IT (cheat sheet)

```bash
cd "/Users/acc2/Downloads/cap 1"

# everything (regenerates outputs/demo + outputs/eval)
make demo                      # or: ./.venv/bin/python -m process_miner.cli demo

# single SOP with its log (full pipeline incl. conformance)
./.venv/bin/python -m process_miner.cli mine inputs/vendor_onboarding_sop.md \
    --log inputs/vendor_onboarding_events.csv -o outputs/vendor

# process discovery from a log (CSV or XES)
./.venv/bin/python -m process_miner.cli analyze-log inputs/it_incident_events.xes

# validate any artifact / evaluate extraction / serve API
./.venv/bin/python -m process_miner.cli validate outputs/demo/*_bpmn.bpmn
./.venv/bin/python -m process_miner.cli eval -o outputs/eval
./.venv/bin/python -m process_miner.cli serve --port 8000

# tests / clean regeneration of logs
./.venv/bin/python -m pytest
./.venv/bin/python scripts/generate_logs.py

# browse artifacts in a browser (optional)
./.venv/bin/python -m http.server 8734 --bind 127.0.0.1
# → http://127.0.0.1:8734/outputs/index.html

# enable LLM extraction (optional)
export OPENAI_API_KEY=sk-...           # or ANTHROPIC_API_KEY
export PM_LLM_MODEL=gpt-4o-mini        # any OpenAI-compatible endpoint via PM_LLM_BASE_URL
```

Key knobs: `--engine auto|builtin|langgraph`, `--no-optimize`, `--threshold`
(DFG edge filter), env `PM_OUTPUT_DIR`, `PM_LLM_PROVIDER/MODEL/BASE_URL`.

---

## 6. WHAT COULD HAVE BEEN DONE BETTER (honest limitations)

1. **Gold co-designed with the corpus** — the SOPs use controlled vocabulary
   that the parser was built around, so the F1 = 1.00 is a *ceiling result*,
   not real-world performance. Real SOPs (coreference, passive voice, tacit
   steps, typos) will score lower. The harness exists to quantify that; it just
   hasn't been run on messy external corpora yet.
2. **Conformance activity matching is lexical** — token-stem similarity ≥ 0.5
   misses cross-vocabulary pairs ("Perform background screening" ↔
   "Compliance Screening"), which is why vendor conformance recall is only 50%.
   Embedding-based matching (e.g. sentence-transformers) is the known fix.
3. **DFG→BPMN induction is heuristic** — frequency-thresholded DFGs cannot
   express arbitrary block structure; no noise filtering beyond the threshold;
   noHeuristicsNet / inductive miner equivalents.
4. **Durations are priors** — task durations come from verb heuristics, so
   absolute cycle-time minutes are indicative; only the relative deltas are
   meaningful. No learning from log service times into the SOP model.
5. **LLM path untested in anger** — no API key was available, so E2/E3
   (LLM / LLM+retry) rows in the evaluation are wired but empty. Temperature 0
   + JSON mode + the validation gate mitigate, but multi-seed runs are needed
   for thesis tables.
6. **English-only, single-SOP scope** — no multi-language handling, no
   process-collection discovery across documents, no process variant merging.
7. **Web UI is read-only** — the FastAPI service exposes mining, but there is
   no human-in-the-loop editing/repair UI (validator warnings surface in the
   report/CLI only).
8. **Testing gaps** — no property-based tests, no fuzzing of the parser, no
   performance benchmarks beyond informal timings (~1–2 s per artifact set).
9. **Packaging** — installable via `pip install -e .` but not published;
   `process_miner.mining.ingestion_columns` and `agents/offline_parser`
   internals are quasi-public API without a stability promise.

---

## 7. FUTURE PLANS (roadmap)

### Near term (thesis completion)
1. **Run E2/E3 LLM experiments** — add an API key, run the harness over the
   corpus with ≥3 seeds, tabulate rule-vs-LLM F1/gateway error → the central
   thesis table. (`export OPENAI_API_KEY=...` then `python -m process_miner.cli eval`
   already routes through the LLM when configured.)
2. **Conformance improvement experiment** — swap lexical matching for
   embeddings; measure how much vendor-recall improves; report as ablation.
3. **Write the thesis chapters** mapped in `docs/RESEARCH.md §7`; export
   diagrams from draw.io as PNG/PDF for the appendix; include the HTML reports.
4. **Optional: 1–2 messy real-world SOPs** (redacted) as an external-validity
   section — expect lower F1 and report it.

### Mid term (engineering)
5. Human-in-the-loop repair UI: render validator warnings as editable
   suggestions before export (bpmn-js modeler embeds well).
6. Inductive-miner-style log discovery (block-structured guarantees) behind
   `analyze-log --algorithm inductive`.
7. Duration learning: estimate task durations from log service times
   (start/complete lifecycle pairs) and feed them into To-Be projections.
8. Conformance v2: token-replay fitness + alignment-based conformance for
   rigorous numbers; diff view (documented vs discovered) as a BPMN overlay.
9. CI hardening: add bpmn-js import check as a real CI step (playwright),
   artifact determinism check between runs.

### Long term / stretch
10. Multi-document process-collection mining (find one process described in N
    documents, merge variants).
11. Multi-language SOP support (start with German/Spanish marker lexicons).
12. Streaming conformance dashboards against live event feeds.
13. Publish to PyPI + a small demo site (FastAPI + bpmn-js viewer).

---

## 8. KEY DESIGN DECISIONS (and why)

| Decision | Rationale |
|---|---|
| Offline-first (rule parser as guaranteed path) | Reviewers/examiners must be able to run everything without keys; also serves as the research baseline. |
| LLM references nodes by *name*, not id | LLMs are markedly more reliable naming entities than generating globally-unique ids; resolution happens deterministically after. |
| Shared stage functions across two engines | LangGraph becomes a swappable orchestration variable; equivalence is a test assertion, not a hope. |
| `PipelineState` TypedDict declares every key | LangGraph silently drops undeclared state keys — this bit us once (engine/method fields vanished); the equivalence test catches it. |
| Validation gate + auto-repair between every producer/consumer | Guarantees exportable BPMN regardless of extractor quality; retry loop gives LLM self-correction. |
| Rework loops through explicit XOR merge gateways | Cleaner BPMN, removes implicit-merge warnings, enables the conformance rework explanation logic. |
| Determinism everywhere (seeded logs, no wall-clock in extraction) | Diff-friendly artifacts, reproducible evaluation, testable. |
| Honest metrics naming (DF precision/recall, not "fitness") | Avoids overclaiming vs token-replay/alignment fitness in the academic sense. |
| Recommendations are *applied* into To-Be, waits only advised | Transforming queue policy into model structure would fabricate precision; advising SLA changes is defensible. |

---

## 9. FILE MAP (resume here)

```
README.md                  product readme (quick start)
PROJECT_REPORT.md          ← this document
Makefile                   setup / test / demo / eval / serve / clean
pyproject.toml             deps + pytest config (pythonpath=".")
.github/workflows/ci.yml   CI: install → logs → tests → demo → validate → eval
process_miner/             the package (see §2.1 for per-module map)
inputs/                    3 SOPs + 2 CSV logs + 1 XES log
scripts/generate_logs.py   seeded synthetic log generator
eval/gold/                 gold annotations (JSON per SOP)
diagrams/                  3 hand-authored draw.io files (5 pages)
docs/                      SRS, ARCHITECTURE, RESEARCH, USER_STORIES
tests/                     140 tests in 10 files
outputs/                   generated artifacts + index.html hub (regenerable)
.venv/                     Python 3.11 venv (--system-site-packages, Homebrew python)
```

## 10. CURRENT NUMBERS AT A GLANCE

| Scenario | Tasks | Findings | Cycle (As-Is→To-Be) | Automation | Conformance (matched / DF recall / trace fitness) |
|---|---|---|---|---|---|
| Vendor onboarding | 13 | 6 (2 applied recs) | 54 → 37 min | 38% → 46% | 9/13 · 56% · 56% — AND block discovered from log ✓ |
| IT incident mgmt | 15 | 7 (1 applied) | 84 → 70 min | 27% → 40% | 11/15 · 82% · 75% |
| Employee leave | 8 | 1 (1 applied) | 33 → 26 min | 50% → 62% | (no bundled log) |
| Legacy IT purchase (messy) | F1 0.10 | — | — | — | external-validity datapoint |

Evaluation: curated SOPs F1 1.00 (ceiling, controlled vocabulary); legacy prose
F1 0.10 (honest degradation) — `outputs/eval/eval_report.md`.
