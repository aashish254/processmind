# THESIS PACKAGE — How to Run and Show Everything

**Thesis:** *LLM-Assisted Business Process Discovery: Combining Multi-Agent Extraction with Sound Process Mining for Automated BPMN Reconstruction*

This is the single entry point for the thesis deliverable: the written thesis, the system that produced the results, and the one-command demonstrations for a supervisor or examiner.

---

## 1. The thesis documents (what you submit)

| File | What it is |
|---|---|
| `THESIS.md` | **The complete thesis** (~17,600 words): title page, abstract, 7 chapters, references, 2 appendices |
| `thesis.docx` | **Word version** — open in Word → File → Save As → PDF. This is your submission format |
| `thesis.pdf` | **Pre-generated PDF** (75 pages, generated from `THESIS.md` via pandoc → styled HTML → headless Chrome) |
| `THESIS_final.html` | Styled HTML version (source for `thesis.pdf`) |
| `01_introduction.md` … `07_conclusion.md` | Individual chapter sources |
| `references.md` | 17 academic citations (Dumas, van der Aalst, Leemans, Shinn, Wohlin…) |
| `appendix_a_evidence.md` | System outputs as evidence: BPMN models, HTML reports, test suite, XML samples |
| `appendix_b_data.md` | Complete raw evaluation data — full reproducibility |

**To make the PDF:** `thesis.pdf` is already generated and current. To regenerate after editing `THESIS.md`: `pandoc THESIS.md --toc --number-sections -o thesis.docx` for Word, then `pandoc THESIS.md -s --toc --number-sections -c thesis_academic.css -o THESIS_final.html` and print to PDF with headless Chrome. Earlier working drafts (`THESIS_COMPLETE.md`, `THESIS_MASTER.md`, …) are archived in `drafts/` — `THESIS.md` is the single source of truth.

---

## 2. One-command demonstrations (run these for a supervisor)

All commands run from the project root (`MASTERS CAP1/`).

### 2.1 The 60-second demo

```bash
./.venv/bin/python -m process_miner.cli research-eval
```

Output: Experiment A (E1 extraction vs gold) + Experiment B (E4 DFG vs E6 Inductive Miner fitness on all 7 logs). Writes `outputs/research/research_eval.{json,md}`. **No API key needed.**

### 2.2 The full pipeline demo (~5 min with LLM, ~10 s offline)

```bash
# With LLM (OpenRouter key):
export OPENAI_API_KEY=sk-or-v1-...
export PM_LLM_BASE_URL=https://openrouter.ai/api/v1
export PM_LLM_MODEL=qwen/qwen3-8b
./.venv/bin/python -m process_miner.cli demo

# Without LLM (E1 rule parser only, instant):
./.venv/bin/python -m process_miner.cli demo
```

Produces for each of the 4 SOPs: BPMN XML, As-Is/To-Be SVG diagrams, draw.io, Mermaid, model JSON, conformance report, bottleneck findings, and a self-contained HTML analyst report — all in `outputs/demo/`.

### 2.3 Inductive Miner discovery (RQ4)

```bash
./.venv/bin/python -m process_miner.cli discover-im inputs/it_incident_events.csv -o outputs/im
# → As-Is : 12 tasks, 4 gateways … Replay fitness: 1.0 (300/300 cases)
```

### 2.4 The evidence browser

```bash
open outputs/thesis_index.html     # visual browser of all artifacts
# or serve it:
python -m http.server 8734 -d outputs   # → http://localhost:8734/thesis_index.html
```

### 2.5 Test suite (engineering-quality evidence)

```bash
./.venv/bin/python -m pytest        # 162 tests, ~2 s, deterministic
```

---

## 3. The experiments and where the numbers live

| Thesis table | Source | File |
|---|---|---|
| Table 5.1 — E1/E2/E3 vs gold (RQ1–3) | `python scripts/run_llm_experiments.py` (rerunnable) | `outputs/llm_comparison.json` |
| Table 5.2 — E4 vs E6 fitness (RQ4) | `make research-eval` | `outputs/research/research_eval.{json,md}` |
| Table 5.3 — conformance (RQ5) | `make demo` with `--log` | `outputs/demo/*_conformance.json` |
| Test suite evidence | `make test` | 162 passing |

**LLM runs (E2/E3) used `qwen/qwen3-8b` via OpenRouter, temperature 0.** When you have GPT-4o/Claude keys, set `OPENAI_API_KEY` + `PM_LLM_MODEL` and rerun — the harness records the method per run and the thesis tables update.

---

## 4. Repository map (thesis ↔ code)

| Thesis section | Code |
|---|---|
| Ch 3 Methodology — corpus | `inputs/` (4 SOPs), `eval/gold/` (4 gold JSON), `data/benchmarks/` (5 synthetic logs) |
| Ch 3 §3.4 — Extractors | `agents/offline_parser.py` (E1), `agents/modeler.py` (E2/E3), `mining/dfg.py` (E4), `inductive/tree.py` (E6) |
| Ch 4 — Pipeline | `graph.py`, `config.py`, `cli.py`, `api.py` |
| Ch 4 §4.5–4.6 — BPMN engineering | `bpmn/layout.py`, `bpmn/builder.py`, `bpmn/validate.py` |
| Ch 4 §4.7 — Discovery | `mining/dfg.py`, `inductive/tree.py`, `inductive/replay.py` |
| Ch 5 Results — measures | `evaluation.py`, `research_eval.py` |
| Appendix A evidence | `outputs/demo/`, `outputs/research/`, `outputs/thesis_index.html` |
| Appendix B data | `outputs/llm_comparison.json`, `outputs/eval/`, `outputs/research/` |

---

## 5. Regenerating everything from scratch

```bash
make setup          # fresh venv + install
make logs           # regenerate synthetic benchmark logs (seeded)
make test           # 162 tests
make demo           # all artifacts for 4 SOPs
make eval           # E1 vs gold extraction eval
make research-eval  # unified E1–E6 research eval
make serve          # http://localhost:8734 — artifact browser
```

Everything is deterministic (except LLM calls, which use temperature 0 + recorded outputs). Same inputs → byte-identical artifacts.

---

## 6. What to say when presenting (3-minute script)

1. **Problem:** process knowledge lives in two misaligned artefacts — SOPs (intent) and event logs (reality). Analysts reconcile them manually: days to weeks per process.
2. **System:** one pipeline fuses both sources. Five extractors (E1 rules, E2/E3 LLM, E4 DFG, E6 Inductive Miner) evaluated by one harness, under identical measures.
3. **Demo:** `make demo` — a messy SOP becomes a validated BPMN, an analyst report, and bottleneck findings in seconds; `make research-eval` produces every results table in the thesis.
4. **Key results:** rule parser perfect on structured SOPs (F1 1.00) but collapses on real messy text (0.10); LLM recovers it (0.48–0.50); self-correction adds +0.02–0.09 F1 on valid LLM-path runs; Inductive Miner is sound by construction (fitness = coverage on all 7 logs; 0.947 vs DFG's 0.667 on 40%-noise); To-Be transforms cut critical path 17–31% grounded in measured queue waits and rework rates.
5. **Honest ceiling:** controlled-vocabulary corpus, single LLM model — stated in threats-to-validity, with the BPI-Challenge + embedding-matching + human-in-the-loop extension plan ready for the research masters.
