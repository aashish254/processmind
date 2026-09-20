"""Unified research evaluation for the merged framework (the thesis experiment).

Single harness, three extractor families, one soundness measure:

* **E1** - deterministic rule parser (SOP text -> documented model),
* **E2/E3** - LLM / LLM + self-correction (same harness, when a provider
  key is configured; reported as unavailable otherwise),
* **E4** - DFG miner (event log -> frequency-filtered directly-follows model),
* **E6** - Inductive Miner (event log -> block-structured process tree).

Measures
--------
* *Extraction quality* (E1/E2/E3 vs hand-annotated gold SOP models):
  task precision/recall/F1 (greedy token-stem matching, threshold 0.5),
  actor F1, gateway-count error, rework-loop error - unchanged from the
  capstone harness in :mod:`process_miner.evaluation`.
* *Discovery soundness* (E4 vs E6, on identical logs): token-based replay
  fitness over the log's variant multiset, model size (tasks/gateways/flows),
  structural validity, variant coverage and runtime.

Outputs ``research_eval.json`` and ``research_eval.md`` into the output
directory. Run via ``python -m process_miner.cli research-eval``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import fmean
from typing import Dict, List, Optional

from process_miner.bpmn.validate import validate_model
from process_miner.inductive import (
    discover_inductive,
    replay_fitness_process_model,
    variants_from_event_log,
)
from process_miner.mining.dfg import discover_dfg
from process_miner.mining.event_log import compute_summary
from process_miner.models import ProcessModel


# ---------------------------------------------------------------------------
# Experiment A: SOP extraction quality (E1 / E2 / E3 vs gold)
# ---------------------------------------------------------------------------

def extraction_scores(inputs_dir: Path, gold_dir: Path) -> List[Dict]:
    """E1 (rule parser) vs gold. E2/E3 hook in via process_miner.evaluation."""
    from process_miner.evaluation import evaluate_extractor

    return evaluate_extractor(inputs_dir, gold_dir, use_llm=False)


def _avg(rows: List[Dict], key: str) -> float:
    vals = [r[key] for r in rows if key in r]
    return round(fmean(vals), 3) if vals else 0.0


# ---------------------------------------------------------------------------
# Experiment B: discovery soundness benchmark (E4 vs E6)
# ---------------------------------------------------------------------------

def discover_dfg_model(log, threshold_ratio: float, name: str) -> Optional[ProcessModel]:
    try:
        return discover_dfg(log, threshold_ratio=threshold_ratio, name=name)
    except ValueError:
        return None  # log too small / degenerate for DFG discovery


def _model_row(model: Optional[ProcessModel], variants: Dict, t_seconds: float) -> Dict:
    if model is None:
        return {
            "replay_fitness": None,
            "tasks": None, "xor_gateways": None, "and_gateways": None,
            "flows": None, "valid": None, "seconds": round(t_seconds, 4),
        }
    fitness = replay_fitness_process_model(model, variants)
    validation = validate_model(model)
    m = model.summary_metrics()
    return {
        "replay_fitness": round(fitness.fitness, 4),
        "variants_accepted": fitness.cases_accepted,
        "variants_total": fitness.cases_total,
        "tasks": m.task_count,
        "xor_gateways": sum(1 for g in model.gateways() if g.type.value == "xor_gateway"),
        "and_gateways": sum(1 for g in model.gateways() if g.type.value == "and_gateway"),
        "flows": m.flow_count,
        "valid": validation.ok,
        "validation_issues": len(validation.issues),
        "seconds": round(t_seconds, 4),
    }


def discovery_row(log_path: Path, threshold_ratio: float = 0.1,
                  noise_threshold: float = 0.05) -> Dict:
    """Run E4 and E6 on one log; return a combined result row."""
    from process_miner.mining.xes import load_event_log

    log = load_event_log(log_path.read_text(encoding="utf-8", errors="replace"),
                         source=str(log_path))
    variants = variants_from_event_log(log)
    summary = compute_summary(log)

    t0 = time.perf_counter()
    dfg_model = discover_dfg_model(log, threshold_ratio, name=f"{log_path.stem} (DFG)")
    t_dfg = time.perf_counter() - t0

    from process_miner.inductive import mine_with_report

    t0 = time.perf_counter()
    try:
        im_report = mine_with_report(variants, name=f"{log_path.stem} (inductive)",
                                     noise_threshold=noise_threshold)
        im_model: Optional[ProcessModel] = im_report["model"]
        im_error = im_report["discovery_error"]
    except Exception as exc:  # degenerate log - record and continue
        im_model, im_error = None, str(exc)
    t_im = time.perf_counter() - t0

    row: Dict = {
        "log": log_path.name,
        "cases": summary.cases,
        "events": summary.events,
        "activities": summary.activities_count,
        "variants": len(variants),
        "dfg": _model_row(dfg_model, variants, t_dfg),
        "inductive": _model_row(im_model, variants, t_im),
    }
    if im_model is not None:
        row["inductive"]["process_tree"] = im_model.metadata.get("process_tree")
        row["inductive"]["variant_coverage"] = im_model.metadata.get("variant_coverage")
        row["inductive"]["flower_fallback"] = im_model.metadata.get("flower_fallback")
    if im_error:
        row["inductive"]["discovery_error"] = im_error
    return row


def collect_logs(inputs_dir: Path, benchmark_dir: Optional[Path]) -> List[Path]:
    logs = sorted(inputs_dir.glob("*.csv")) + sorted(inputs_dir.glob("*.xes"))
    if benchmark_dir and benchmark_dir.exists():
        logs += sorted(benchmark_dir.glob("*.csv"))
    return logs


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def run_research_eval(
    inputs_dir: Path = Path("inputs"),
    gold_dir: Path = Path("eval/gold"),
    benchmark_dir: Optional[Path] = Path("data/benchmarks"),
    out_dir: Path = Path("outputs/research"),
    threshold_ratio: float = 0.1,
    noise_threshold: float = 0.05,
    generate_benchmarks: bool = True,
) -> Dict:
    """Run the full merged-study evaluation and write JSON + Markdown reports."""
    inputs_dir, gold_dir, out_dir = Path(inputs_dir), Path(gold_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if generate_benchmarks and benchmark_dir is not None:
        from process_miner.inductive.datagen import ensure_benchmark_corpus

        ensure_benchmark_corpus(benchmark_dir)

    # Experiment A
    extraction = extraction_scores(inputs_dir, gold_dir)
    extraction_summary = {
        "task_f1": _avg(extraction, "task_f1"),
        "task_precision": _avg(extraction, "task_precision"),
        "task_recall": _avg(extraction, "task_recall"),
        "actor_f1": _avg(extraction, "actor_f1"),
        "gateway_error": _avg(extraction, "gateway_error"),
        "rework_error": _avg(extraction, "rework_error"),
    }

    # Experiment B
    discovery = [discovery_row(p, threshold_ratio, noise_threshold)
                 for p in collect_logs(inputs_dir, benchmark_dir)]

    report = {
        "study": "Merged framework evaluation - rule parser vs LLM agents vs DFG vs Inductive Miner",
        "extraction": {
            "extractor": "E1 offline rule parser (E2/E3 run the same harness when a provider key is set)",
            "rows": extraction,
            "summary": extraction_summary,
        },
        "discovery": {
            "measures": "token-replay fitness, size, validity, runtime (identical variant multiset per log)",
            "rows": discovery,
        },
    }
    (out_dir / "research_eval.json").write_text(json.dumps(report, indent=2, default=str))
    (out_dir / "research_eval.md").write_text(_to_markdown(report))
    return report


def _to_markdown(report: Dict) -> str:
    lines: List[str] = [
        "# Research evaluation - merged framework",
        "",
        "Generated by `process_miner.research_eval` (`python -m process_miner.cli research-eval`).",
        "",
        "## Experiment A - SOP extraction quality (E1 rule parser vs gold)",
        "",
        "| document | task P | task R | task F1 | actor F1 | gateway err | rework err |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in report["extraction"]["rows"]:
        lines.append(
            f"| {s['doc']} | {s['task_precision']:.2f} | {s['task_recall']:.2f} | {s['task_f1']:.2f} "
            f"| {s['actor_f1']:.2f} | {s['gateway_error']} | {s['rework_error']} |"
        )
    summ = report["extraction"]["summary"]
    lines += [
        "",
        f"**Macro averages** - task P/R/F1: {summ['task_precision']:.2f}/{summ['task_recall']:.2f}/"
        f"{summ['task_f1']:.2f}, actor F1: {summ['actor_f1']:.2f}, gateway err: {summ['gateway_error']:.2f}",
        "",
        "The same harness scores the LLM extractors (E2 schema-guided, E3 + validate-retry) "
        "when a provider key is configured - see `process_miner.evaluation.evaluate_extractor(use_llm=True)`.",
        "",
        "## Experiment B - discovery soundness (E4 DFG vs E6 Inductive Miner)",
        "",
        "Both miners see the identical variant multiset per log; fitness is token-based "
        "replay (cases accepted / cases total).",
        "",
        "| log | cases | variants | E4 fitness | E4 tasks/gw | E4 valid | E6 fitness | E6 tasks/gw | E6 valid | E6 coverage | E6 tree |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["discovery"]["rows"]:
        d, i = r["dfg"], r["inductive"]
        fmt = lambda v, alt="-": (alt if v is None else v)  # noqa: E731
        d_gw = "-" if d["xor_gateways"] is None else f"{d['tasks']}/{d['xor_gateways']}+{d['and_gateways']}"
        i_gw = "-" if i["xor_gateways"] is None else f"{i['tasks']}/{i['xor_gateways']}+{i['and_gateways']}"
        tree = i.get("process_tree") or "-"
        if len(tree) > 60:
            tree = tree[:57] + "..."
        lines.append(
            f"| {r['log']} | {r['cases']} | {r['variants']} "
            f"| {fmt(d['replay_fitness'])} | {d_gw} | {fmt(d['valid'])} "
            f"| {fmt(i['replay_fitness'])} | {i_gw} | {fmt(i['valid'])} "
            f"| {fmt(i.get('variant_coverage'), '-')} | `{tree}` |"
        )
    lines += [
        "",
        "### Notes",
        "",
        "- E4 (DFG) optimises *precision of the directly-follows abstraction*: frequent-variant "
        "behaviour survives, rare branches are thresholded away - fitness < 1 is expected.",
        "- E6 (Inductive Miner) is sound-by-construction on its *filtered* variant log; when "
        "noise filtering drops variants, replay fitness over the *full* log can be < 1 while "
        "the model stays block-structured. Coverage column quantifies that trade-off.",
        "- `flower_fallback` flags fragments where no cut applied (model remains sound but "
        "uninformative - a per-log quality signal for the thesis discussion).",
        "",
    ]
    return "\n".join(lines)
