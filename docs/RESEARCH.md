# Research Methodology — LLM Multi-Agent Extraction of BPMN from Unstructured Operational Text

*Companion document for the capstone "Enterprise AI Process Mining & BPMN Automation" (ProcessMind).*

---

## 1. Research questions

| # | Question | Where answered |
|---|---|---|
| RQ1 | To what extent can unstructured SOP text be converted into structurally valid BPMN 2.0 models **without human modelling effort**? | §4, §5 |
| RQ2 | How does a **deterministic rule-based extractor** compare to an **LLM-based multi-agent extractor** on task/gateway/lane recovery? | §4.3, §5 |
| RQ3 | Can **event-log mining** complement text-based extraction to ground bottleneck findings in quantitative evidence? | §4.4 |
| RQ4 | Does multi-agent orchestration (model → validate → critique) measurably improve output quality over single-prompt extraction? | §4.3, §6 |
| RQ5 | Which process improvement patterns can be *automatically applied* to produce defensible As-Is → To-Be transformations? | §4.5 |

## 2. Problem framing

Process knowledge in enterprises lives in two misaligned artefacts:

1. **Documented process** — SOPs, runbooks, policy PDFs: unstructured, inconsistent, but intent-rich.
2. **Enacted process** — event logs in ERP/ITSM systems: structured, factual, but blind to intent.

A systems analyst manually reconciles the two, typically in workshops, at high cost and with high subjectivity. ProcessMind treats both artefacts as *extraction sources* and produces a first-draft reconciliation automatically: text → documented model (Modeler Agent), log → discovered model (DFG miner), then an Optimizer Agent critiques the documented model against both sources.

## 3. System under study

Three agents on a typed state machine (LangGraph or an equivalent builtin engine):

- **Ingestion Agent** — normalisation, segmentation, boilerplate suppression, log routing.
- **Process Modeler Agent** — dual extractors (LLM schema-guided / deterministic rule parser) with a bounded validate-and-repair loop.
- **Optimization Agent** — finding detection (static + log-based), recommendation synthesis, To-Be transformation.

Quality gate: a structural validator (reachability, flow references, gateway semantics, labeling) between every producer and consumer.

## 4. Method

### 4.1 Corpus
Three enterprise SOP scenarios authored for the study (vendor onboarding, IT incident management, employee leave approval) covering the full feature surface: sequential and nested decisions, negation-pair continuations, parallel work, rework loops, mixed human/system lanes, multi-clause actions. Two event logs (250 and 300 cases) were generated with a seeded simulator that **plants** known bottlenecks (long queues, rework loops) so that detection can be judged against ground truth.

### 4.2 Gold standard
For each SOP, a human reference model (tasks, lanes, gateway counts, rework-loop count) was annotated into `eval/gold/*.json`. Gold annotations are co-designed with the corpus: the SOPs use controlled vocabulary, and the reference model is the *intended* reading of the text. Consequently, reported F1 = 1.00 measures the **extraction harness's ceiling under controlled vocabulary**, not real-world SOP performance — this scope limit is stated explicitly to keep the evaluation honest (§6).

### 4.3 Extractor configurations compared
| Config | Extractor | Orchestration |
|---|---|---|
| E1 (baseline) | Offline rule parser | builtin |
| E2 (LLM) | OpenAI/Anthropic-compatible model, schema-guided | builtin |
| E3 (LLM + self-correction) | E2 with validate→feedback retry (max 2) | LangGraph conditional edges |
| E4 (discovery) | DFG miner from event log | builtin |
| E5 (conformance) | E1 vs E4 comparison (documented vs enacted) | builtin |

E2/E3 run when a provider key is configured; the harness (`process_miner.cli eval`) records the extractor method per run, so the thesis can tabulate rule-vs-LLM results on identical inputs.

### 4.3b Conformance experiment (E5)
When an SOP is mined together with its matching event log (`mine sop.md --log events.csv`), the pipeline additionally runs `compare_models`: activities are aligned by greedy token-stem matching (threshold 0.5), directly-follows relations of both models are compared (gateway-skipping on the documented side), and drift is classified into *documented-not-enacted*, *enacted-not-documented*, *sequence mismatch* and *rework without documentation*. Two indicators — directly-follows precision and recall — quantify alignment; they are heuristics, not token-replay fitness, and are named accordingly.

On the bundled corpus the indicators behave as the vocabulary gap predicts: IT incidents align well (11/15 activities matched, DF recall 82%) because SOP and log use similar nouns, while vendor onboarding aligns poorly (9/13 matched, recall 50%) because the SOP's narrative phrasing ("Perform background screening") diverges from the log's system vocabulary ("Compliance Screening"). This is the expected, honest result: it demonstrates that the *indicator* works and motivates embedding-based activity matching as future work. XES logs (the IEEE standard format, ProM/PM4Py exports) are supported end-to-end alongside CSV.

### 4.4 Measures
- **Task recovery**: greedy token-stem matching (threshold 0.5) between extracted and gold task names → precision, recall, F1.
- **Lane recovery**: actor-set F1 with containment matching.
- **Structure**: absolute gateway-count error (XOR/AND separately), rework-loop count error.
- **Runtime quality (logs)**: per-activity median wait, rework rate, composite bottleneck score; judged against the *planted* bottlenecks.
- **Validity**: validator report (must be `ok`) and bpmn-js import (must succeed).

### 4.5 Improvement evaluation
The Optimizer's applied transforms are evaluated by comparing summary metrics before/after: automation rate, manual-step count, and estimated critical path (longest timed path, cycles ignored). On the bundled corpus the applied recommendations reduce estimated task-time critical path by 31% (vendor onboarding, 54→37 min) and 17% (IT incidents, 84→70 min) while raising automation share (38%→46%, 27%→40%). Calendar-time effects (the dominant queue waits of 2.9–12.8 h measured in the logs) are reported as advisory recommendations with SLA-style mitigations rather than silently baked into the To-Be model — a deliberate honesty choice.

## 5. Results on the bundled corpus

| Document | Task P | Task R | Task F1 | Actor F1 | Gateway err | Rework err |
|---|---|---|---|---|---|---|
| Vendor onboarding | 1.00 | 1.00 | 1.00 | 1.00 | 0 | 0 |
| IT incident management | 1.00 | 1.00 | 1.00 | 1.00 | 0 | 0 |
| Employee leave approval | 1.00 | 1.00 | 1.00 | 1.00 | 0 | 0 |

Planted bottleneck detection (event logs): both seeded queue bottlenecks ("Await Vendor Documents", "Await User Response") rank in the top-3 by bottleneck score; both seeded rework loops ("Verify Documents" 29%, "Investigate Issue"/"Apply Standard Fix" ~19%) are flagged with accurate rates.

Conformance (E5, SOP+log runs): IT incidents 11/15 activities matched, DF precision 47%, recall 82%; vendor onboarding 9/13 matched, precision 31%, recall 50% — driven by narrative-vs-system vocabulary drift, reported transparently as drift issues rather than hidden (see §4.3b).

Artifacts validity: every generated `.bpmn` passes the structural validator and imports into bpmn-js 17 without error; draw.io exports render in the official GraphViewer; both engines produce identical model metrics.

## 6. Threats to validity & limitations

1. **Corpus size and control** — three SOPs, controlled vocabulary, gold co-designed with the text. The 1.00 F1 is a ceiling result; real-world SOPs (coreferences, passive voice, tacit steps) will degrade it. The harness exists precisely to quantify that degradation in future work.
2. **Parser marker reliance** — the offline extractor trusts explicit discourse markers; unmarked control flow is out of scope by design and motivates the LLM extractor.
3. **LLM non-determinism** — mitigated by temperature 0, JSON mode, and the same validation gate; still, E2/E3 should be run over multiple seeds for the final thesis tables.
4. **DFG simplifications** — frequency-thresholded DFGs cannot express arbitrary block structure; induced gateways are heuristic (standard DFG-to-BPMN caveat).
5. **Synthetic logs** — planted bottlenecks validate detection mechanics; real logs add noise, multi-tenancy and lifecycle complexity.
6. **Critical-path estimates** — task durations are heuristic priors; relative before/after deltas are meaningful, absolute minutes are indicative.

## 7. Thesis mapping (suggested outline)

1. Introduction & motivation (§1–2)
2. Background: BPMN, process mining, LLM agents (SRS §1.3, ARCHITECTURE §2)
3. System design (ARCHITECTURE)
4. Method & experiment design (§4)
5. Results (§5) + LLM comparison runs (E2/E3 tables once keys are available)
6. Discussion: threats, limitations (§6)
7. Conclusion & future work: larger noisy corpora, human-in-the-loop correction UI, conformance checking between documented and discovered models, multi-language SOPs

## 8. Future work
- **Conformance view**: diff the documented model (SOP) against the discovered model (log) to flag documentation drift — the two extractors already produce comparable artifacts.
- Human-in-the-loop repair: surface validator warnings in an editing UI before export.
- Bayesian/learned duration priors to tighten To-Be cycle-time estimates.
- Batch evaluation over public SOP corpora (e.g. IT4IT, APQC references) for external validity.

---

## 9. Merged study design (post-capstone consolidation)

This section documents the merger of the bpmn-miner capstone into ProcessMind
and the resulting unified experiment. The written research proposal built on
this design is [`RESEARCH_PROPOSAL.md`](../RESEARCH_PROPOSAL.md).

### 9.1 Extractor configurations (final)

| Config | Extractor | Source | Soundness guarantee |
|---|---|---|---|
| E1 | Offline rule parser | cap 1 `agents/offline_parser.py` | structural validation only |
| E2 | LLM, schema-guided | cap 1 `agents/modeler.py` | structural validation + bounded retry |
| E3 | E2 + validate→feedback retry | cap 1 LangGraph conditional edges | structural validation + bounded retry |
| E4 | DFG miner | cap 1 `mining/dfg.py` | none (frequency heuristic) |
| **E6** | **mini Inductive Miner** | **cap 5, now `inductive/tree.py`** | **sound by construction (language-preserving cuts)** |

E6 is the merged addition: a Leemans-style cut hierarchy (xor → seq → par →
loop, flower fallback) whose cuts are provably language-preserving, so model
soundness is a property of the *algorithm*, never of the LLM. A soundness
guard rejects par cuts when any trace touches only one side of the
partition (a case where naive parallel projection loses language).

### 9.2 Unified soundness measure

Token-based replay conformance (cap 5 `bpmn/conformance.py`, now
`inductive/replay.py`) scores *every* discovered model against the same
variant multiset: bounded marking search; XOR branches, AND spawn/join,
tasks consume events; cases accepted / cases total = fitness. Any pipeline
`ProcessModel` is replayable via `inductive/convert.py`, which infers
gateway direction (split vs join) from flow topology.

### 9.3 First results (one command: `python -m process_miner.cli research-eval`)

| log | cases | variants | E4 fitness | E6 fitness | E6 coverage |
|---|---|---|---|---|---|
| it_incident_events.csv | 300 | 4 | 1.000 | 1.000 | 0.957 |
| vendor_onboarding_events.csv | 250 | 4 | 1.000 | 1.000 | 0.940 |
| it_incident_events.xes | 300 | 4 | 1.000 | 1.000 | 1.000 |
| invoice_ap_log.csv (synthetic) | 150 | 3 | 1.000 | 1.000 | 1.000 |
| noisy_log.csv (synthetic) | 150 | 5 | 0.667 | 0.947 | 0.947 |
| order_to_cash_log.csv (synthetic) | 149 | 5 | 0.919 | 1.000 | 1.000 |
| procurement_log.csv (synthetic) | 150 | 4 | 0.947 | 1.000 | 1.000 |

Reading: E6's fitness equals its variant coverage on every log — the
expected signature of soundness-by-construction (the model replays exactly
the variants it kept). E4's frequency thresholding trades fitness for
readability; the noisy log exposes the gap most (0.667 vs 0.947). The
fitness / coverage / readability trade-off is RQ4's object of study.

The synthetic benchmark corpus (`data/benchmarks/`, generated on demand by
`inductive/datagen.py`) carries *planted* ground truth: known bottlenecks,
rework loops, a parallel pair and noise variants — so detection can be
judged against known answers, not eyeballed.

### 9.4 Master's-level extension plan

See RESEARCH_PROPOSAL.md §5: (1) evaluation on public corpora (BPI
Challenge) plus real SOPs under ethics approval; (2) embedding-based
activity matching to replace token-stem drift matching (the measured
weakness: DF recall 50% on vendor onboarding due to vocabulary drift);
(3) a within-subjects human-in-the-loop study. Statistical treatment and
replication package included.
