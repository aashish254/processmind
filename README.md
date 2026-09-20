# ProcessMind — Merged Research Framework
## LLM Multi-Agent Extraction + Sound Process Mining for Automated BPMN Reconstruction

[![Thesis DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22854334.svg)](https://doi.org/10.5281/zenodo.22854334)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 162 passing](https://img.shields.io/badge/tests-162%20passing-brightgreen.svg)](tests/)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0007--8952--6357-green.svg)](https://orcid.org/0009-0007-8952-6357)

> **Author:** Aashish Kumar Mahato · Independent Researcher · [ORCID 0009-0007-8952-6357](https://orcid.org/0009-0007-8952-6357)
>
> **Published preprint:** Mahato, A. K. (2026). *LLM-Assisted Business Process Discovery*. Zenodo. https://doi.org/10.5281/zenodo.22854334

**Start here for the thesis:** [thesis/THESIS_README.md](thesis/THESIS_README.md) — one-page guide: run commands, where the numbers live, what to say when presenting.

**Quick demo:** `open outputs/thesis_index.html` — visual browser of all 4 SOP artifacts with PNG screenshots.

**One pipeline, five extractor configurations, one evaluation harness.** This repository merges two capstone projects into a single research framework backing a Master of Information Technology (research) application:

- **ProcessMind** (multi-agent LLM pipeline: SOPs → BPMN, bottleneck findings, As-Is → To-Be) — the application layer.
- **bpmn-miner** (mini Inductive Miner, token-replay conformance, pm4py-validated) — the sound-by-construction discovery core, now the `process_miner.inductive` subpackage.

**Start here:** [RESEARCH_PROPOSAL.md](RESEARCH_PROPOSAL.md) — the written research proposal this repository supports.

```
SOP text (.md/.txt) ─┐
                     ├─► Ingestion Agent ─► Process Modeler Agent ─► Validator ─► Optimizer Agent ─► BPMN 2.0 + reports
Event logs (.csv/.xes) ┘        (clean)        (E1 rules | E2/E3 LLM)   (retry)     (findings +      (draw.io, Mermaid,
                                                                             To-Be transform)  SVG, HTML, JSON)
Event logs ──► E4 DFG miner ──────────┐
             └► E6 Inductive Miner ───┴─► token-replay fitness ─► conformance / drift ─► research-eval report
```

---

## What was merged

| From | Into this repository |
|---|---|
| bpmn-miner `mining/inductive.py` | `process_miner/inductive/tree.py` — mini Inductive Miner (Leemans-style xor → seq → par → loop cuts, flower fallback), sound by construction |
| bpmn-miner `bpmn/conformance.py` | `process_miner/inductive/replay.py` — bounded token-replay conformance fitness |
| bpmn-miner `bpmn/model.py` | `process_miner/inductive/tree_bpmn.py` — process tree → BPMN block structure |
| new bridges | `process_miner/inductive/convert.py` — discovered models flow through the *same* export pipeline (BPMN XML, draw.io, SVG, HTML reports, validator, optimizer); any pipeline model can be replayed |
| bpmn-miner `datagen.py` | `process_miner/inductive/datagen.py` — synthetic benchmark logs with *planted* ground truth (bottlenecks, rework loops, noise variants) |
| new | `process_miner/research_eval.py` — unified evaluation: extraction quality (E1 vs gold) + discovery soundness (E4 DFG vs E6 Inductive, identical variant multisets) |

## Research evaluation (one command)

```bash
python -m process_miner.cli research-eval     # → outputs/research/research_eval.{json,md}
```

Experiment A measures SOP extraction quality against hand-annotated gold models (task/actor F1, gateway/rework errors). Experiment B mines every available event log with **both** the DFG miner (E4) and the Inductive Miner (E6) and scores both with token-replay fitness on identical inputs. Current results:

| log | cases | variants | E4 DFG fitness | E6 inductive fitness | E6 coverage |
|---|---|---|---|---|---|
| it_incident_events.csv | 300 | 4 | 1.000 | 1.000 | 0.957 |
| vendor_onboarding_events.csv | 250 | 4 | 1.000 | 1.000 | 0.940 |
| it_incident_events.xes | 300 | 4 | 1.000 | 1.000 | 1.000 |
| invoice_ap_log.csv (synthetic) | 150 | 3 | 1.000 | 1.000 | 1.000 |
| noisy_log.csv (synthetic) | 150 | 5 | 0.667 | 0.947 | 0.947 |
| order_to_cash_log.csv (synthetic) | 149 | 5 | 0.919 | 1.000 | 1.000 |
| procurement_log.csv (synthetic) | 150 | 4 | 0.947 | 1.000 | 1.000 |

E6's fitness equals its variant coverage on every log — the signature of a sound-by-construction miner — while E4's frequency thresholding trades fitness for readability. The thesis interrogates exactly this trade-off (RESEARCH_PROPOSAL.md §3, RQ4).

## Quick start

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e ".[graph,api,dev]"

# full pipeline over the bundled SOPs + logs
./.venv/bin/python -m process_miner.cli demo

# mine an SOP into BPMN + analyst report
./.venv/bin/python -m process_miner.cli mine inputs/vendor_onboarding_sop.md \
    --log inputs/vendor_onboarding_events.csv -o outputs/vendor

# discover a block-structured model from a log (Inductive Miner)
./.venv/bin/python -m process_miner.cli discover-im inputs/it_incident_events.csv -o outputs/im

# DFG discovery, validation, extraction eval, unified research eval
./.venv/bin/python -m process_miner.cli analyze-log inputs/it_incident_events.csv
./.venv/bin/python -m process_miner.cli eval
./.venv/bin/python -m process_miner.cli research-eval
./.venv/bin/python -m pytest            # 162 tests
```

## Enabling the LLM agents (optional)

The pipeline is fully functional offline via the deterministic rule parser (E1). For LLM extraction (E2/E3):

```bash
export OPENAI_API_KEY=sk-...            # any OpenAI-compatible endpoint
export PM_LLM_MODEL=gpt-4o-mini
./.venv/bin/python -m process_miner.cli mine inputs/vendor_onboarding_sop.md --engine langgraph
```

The Modeler Agent uses schema-guided extraction with a bounded validate-and-retry loop, falling back to the offline parser on any error. The offline parser is the *baseline extractor* in the research evaluation — E1 vs E2 vs E3 is the thesis's core comparison.

## Design stance

**Structure discovery and semantic enrichment are separated.** Control flow comes from deterministic, provably sound mining (the Inductive Miner's cuts are language-preserving); the LLM is confined to enrichment where errors are recoverable and human-reviewable. Model soundness is a property of the algorithm, never of the LLM.

## Engineering quality

- **162 pytest cases**: every agent, both orchestration engines (asserted equivalent), the BPMN builder, the Inductive Miner's cuts and soundness invariant, replay semantics, conversion round-trips, benchmark generator, and an end-to-end research-eval test.
- Generated BPMN verified to import into bpmn-js; draw.io files verified in the official GraphViewer.
- Deterministic: same input → byte-identical models and layouts.
- Synthetic benchmark logs carry planted ground truth (bottlenecks, rework loops, noise variants) so detection is judged against known answers.

## Documentation

| Doc | Contents |
|---|---|
| [RESEARCH_PROPOSAL.md](RESEARCH_PROPOSAL.md) | **The masters research proposal** — background, RQs, method, first results, planned extension, timeline |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Research methodology: RQs, extractor configurations E1–E6, measures, evaluation design |
| [PROJECT_REPORT.md](PROJECT_REPORT.md) | Full handoff report on the ProcessMind pipeline (architecture, verified evidence, limitations, roadmap) |
| [docs/SRS.md](docs/SRS.md) / [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Requirements specification; system architecture |
| outputs/research/research_eval.md | Generated evaluation report (regenerate with `research-eval`) |

## License

MIT — merged capstone / masters research framework, 2026.
