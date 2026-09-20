# THESIS PACKAGE — How to Run and Show Everything

**Thesis:** *LLM-Assisted Business Process Discovery: Combining Multi-Agent Extraction with Sound Process Mining for Automated BPMN Reconstruction*

This is the single entry point for the thesis deliverable: the written thesis, the system that produced the results, and the one-command demonstrations for a supervisor or examiner.

---

## 1. The Thesis Documents (What You Submit)

| File | What It Is |
|---|---|
| `thesis/THESIS.md` | **The complete thesis** (~17,600 words): title page, abstract, 7 chapters, references, 2 appendices |
| `thesis/thesis.docx` | **Word version** — open in Word → File → Save As → PDF. This is your submission format |
| `thesis/thesis.pdf` | Pre-generated PDF version (75 pages) |
| `thesis/THESIS_final.html` | Styled HTML version (source for the PDF) |
| `thesis/01_introduction.md` … `thesis/07_conclusion.md` | Individual chapter sources |
| `thesis/references.md` | 17 academic citations (Dumas, van der Aalst, Leemans, Shinn, Wohlin…) |
| `thesis/appendix_a_evidence.md` | System outputs as evidence: BPMN models, HTML reports, test suite, XML samples |
| `thesis/appendix_b_data.md` | Complete raw evaluation data — full reproducibility |

---

## 2. The Artifact Browser

```bash
open outputs/index.html       # visual browser of all outputs
# or serve it:
python3 -m http.server 8734 -d outputs
# → http://localhost:8734/index.html
```

The artifact browser shows all 4 SOP scenarios with their As-Is and To-Be BPMN diagrams, links to every generated artifact (SVG, HTML reports, JSON evaluations, BPMN XML, draw.io files), discovery fitness results, and key findings.

---

## 3. One-Command Demonstrations

All commands run from the project root (`MASTERS CAP1/`).

### 3.1 The 60-Second Research Evaluation

```bash
make research-eval
```

Output: Experiment A (E1 extraction vs gold) + Experiment B (E4 DFG vs E6 Inductive Miner fitness on all 7 logs). Writes `outputs/research/research_eval.{json,md}`. **No API key needed.**

### 3.2 The Full Pipeline Demo (~5 min with LLM, ~10s offline)

```bash
# With LLM (OpenRouter key):
export OPENAI_API_KEY=sk-or-v1-...
export PM_LLM_BASE_URL=https://openrouter.ai/api/v1
export PM_LLM_MODEL=qwen/qwen3-8b
make demo

# Without LLM (E1 rule parser only, instant):
make demo
```

Produces for each of the 4 SOPs: BPMN XML, As-Is/To-Be SVG diagrams, draw.io, Mermaid, model JSON, conformance report, bottleneck findings, and a self-contained HTML analyst report — all in `outputs/demo/`.

### 3.3 Inductive Miner Discovery (RQ4)

```bash
make discover-im
# → outputs/im/ — As-Is / To-Be BPMN, replay fitness: 1.0 (300/300 cases)
```

### 3.4 Run the 162-Test Suite

```bash
make test
```

---

## 4. Key Results from Demo Run

### Extraction Quality (RQ1-RQ3)

| SOP | E1 Task F1 | E1 Actor F1 | Notes |
|---|---|---|---|
| Employee Leave Approval | 1.00 | 1.00 | Structured, rule parser perfect |
| IT Incident Management | 1.00 | 1.00 | Structured, rule parser perfect |
| Vendor Onboarding | 1.00 | 1.00 | Structured, rule parser perfect |
| Legacy IT Purchase | 0.10 | 0.00 | Messy real-world text — **E1 collapses** |

**LLM recovers messy SOPs:** F1=0.48-0.50 on Legacy IT Purchase (4.8x better than rule parser).
**Self-correction loop:** adds +0.02 to +0.09 F1 on every document with a valid LLM-path run (the vendor onboarding E3 run fell back to the rule parser — see Table 5.1 footnote in the thesis).

### Process Mining Soundness (RQ4)

| Event Log | Cases | Variants | E4 DFG Fitness | E6 Inductive Fitness | E6 Coverage |
|---|---|---|---|---|---|
| it_incident_events.csv | 300 | 4 | 1.000 | 1.000 | 0.957 |
| vendor_onboarding_events.csv | 250 | 4 | 1.000 | 1.000 | 0.940 |
| it_incident_events.xes | 300 | 4 | 1.000 | 1.000 | 1.000 |
| invoice_ap_log.csv (synthetic) | 150 | 3 | 1.000 | 1.000 | 1.000 |
| **noisy_log.csv** (40% noise) | 150 | 5 | **0.667** | **0.947** | 0.947 |
| order_to_cash_log.csv | 149 | 5 | 0.919 | **1.000** | 1.000 |
| procurement_log.csv | 150 | 4 | 0.947 | **1.000** | 1.000 |

**Key finding:** E6 fitness equals variant coverage on every log — the signature of soundness-by-construction. The noisy log exposes E4's frequency-threshold cost (0.667 vs 0.947).

### To-Be Transforms (RQ5)

- Critical path cut: **17-31%** reduction, grounded in measured queue waits and rework rates
- Automation increases: Leave Approval 43→57%, IT Incident 17→25%, Vendor Onboarding 30%
- Vocabulary gap between SOP intent and event log reality quantified

---

## 5. All Generated Artifacts

### Demo Outputs (`outputs/demo/`)

Each SOP generates:
- `*_asis.svg` — As-Is BPMN diagram
- `*_tobe.svg` — To-Be BPMN diagram (optimized)
- `*_bpmn.bpmn` — As-Is BPMN 2.0 XML
- `*_tobe_bpmn.bpmn` — To-Be BPMN 2.0 XML
- `*_report.html` — Self-contained HTML analyst report
- `*_result.json` — Complete model + extraction metadata
- `*_model.json` — Normalized process model JSON
- `*_process.drawio` — draw.io editable diagram
- `*_mermaid.mmd` — Mermaid diagram format
- `*_conformance.json` — Token-replay conformance results (IT Incident, Vendor Onboarding)
- `*_log_stats.json` — Event log statistics (IT Incident, Vendor Onboarding)

**4 SOPs × ~13 files = 52+ artifacts**

### Process Mining (`outputs/research_im/`)

- `it_incident_events_asis.svg` / `it_incident_events_tobe.svg` — Inductive Miner discovered models
- `it_incident_events_bpmn.bpmn` / `it_incident_events_tobe_bpmn.bpmn` — BPMN XML
- `it_incident_events_result.json` — Full discovery results (229KB, 300 cases replayed)
- `it_incident_events_conformance.json`, `_log_stats.json`, `_report.html`

### Evaluation (`outputs/eval/`, `outputs/research/`)

- `eval/eval_report.json` / `eval_report.md` — Gold-standard extraction evaluation
- `research/research_eval.json` / `research_eval.md` — Unified E1-E6 evaluation report

---

## 6. Repository Map (Thesis ↔ Code)

| Thesis Section | Code |
|---|---|
| Ch 3 Methodology — corpus | `inputs/` (4 SOPs), `eval/gold/` (4 gold JSON), `data/benchmarks/` (5 synthetic logs) |
| Ch 3 §3.4 — Extractors | `agents/offline_parser.py` (E1), `agents/modeler.py` (E2/E3), `mining/dfg.py` (E4), `inductive/tree.py` (E6) |
| Ch 4 — Pipeline | `graph.py`, `config.py`, `cli.py`, `api.py` |
| Ch 4 §4.5-4.6 — BPMN engineering | `bpmn/layout.py`, `bpmn/builder.py`, `bpmn/validate.py` |
| Ch 4 §4.7 — Discovery | `mining/dfg.py`, `inductive/tree.py`, `inductive/replay.py` |
| Ch 5 Results — measures | `evaluation.py`, `research_eval.py` |
| Appendix A evidence | `outputs/demo/`, `outputs/research/`, `outputs/index.html` |
| Appendix B data | `outputs/llm_comparison.json`, `outputs/eval/`, `outputs/research/` |

---

## 7. Quick Start

```bash
# Setup
make setup          # fresh venv + install

# Generate everything
make logs           # regenerate synthetic benchmark logs (seeded)
make test           # 162 tests (~2s, deterministic)
make demo           # all artifacts for 4 SOPs
make research-eval  # unified E1-E6 research eval
make serve          # http://localhost:8734 — artifact browser
```

Everything is deterministic (except LLM calls, which use temperature 0 + recorded outputs). Same inputs → byte-identical artifacts.

---

## 8. What to Say When Presenting (3-Minute Script)

1. **Problem:** process knowledge lives in two misaligned artefacts — SOPs (intent) and event logs (reality). Analysts reconcile them manually: days to weeks per process.
2. **System:** one pipeline fuses both sources. Five extractors (E1 rules, E2/E3 LLM, E4 DFG, E6 Inductive Miner) evaluated by one harness, under identical measures.
3. **Demo:** `make demo` — a messy SOP becomes a validated BPMN, an analyst report, and bottleneck findings in seconds; `make research-eval` produces every results table in the thesis.
4. **Key results:** rule parser perfect on structured SOPs (F1 1.00) but collapses on real messy text (0.10); LLM recovers it (0.48–0.50); self-correction adds +0.02–0.09 F1 on valid LLM-path runs; Inductive Miner is sound by construction (fitness = coverage on all 7 logs; 0.947 vs DFG's 0.667 on 40%-noise); To-Be transforms cut critical path 17–31% grounded in measured queue waits and rework rates.
5. **Honest ceiling:** controlled-vocabulary corpus, single LLM model — stated in threats-to-validity, with the BPI-Challenge + embedding-matching + human-in-the-loop extension plan ready for the research masters.
