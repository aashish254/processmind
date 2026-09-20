"""ProcessMind command-line interface.

Commands:
    mine          SOP text -> BPMN + bottlenecks + report (full pipeline)
    analyze-log   event-log CSV -> DFG-discovered BPMN + analytics
    discover-im   event-log CSV -> Inductive-Miner BPMN + analytics (E6)
    research-eval unified research evaluation (E1/E4/E6 + replay fitness)
    validate      validate a saved model JSON or BPMN XML artifact
    eval          extraction-quality evaluation vs gold annotations
    demo          run everything over the bundled inputs
    serve         start the FastAPI service

Run ``python -m process_miner.cli --help`` for details.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from process_miner.config import load_settings
from process_miner.graph import analyze_log, discover_im_log, run_pipeline, validate_artifact


def _print_summary(result) -> None:
    print(f"\n=== {result.name} ===")
    print(f"engine: {result.engine}   extractor: {result.modeler_method}")
    if result.model:
        m = result.model.summary_metrics()
        print(
            f"As-Is : {m.task_count} tasks, {m.lane_count} lanes, {m.gateway_count} gateways, "
            f"automation {m.automation_rate:.0%}, est. cycle time {m.estimated_cycle_time_minutes:.0f} min"
        )
    if result.tobe_model:
        m = result.tobe_model.summary_metrics()
        print(
            f"To-Be : {m.task_count} tasks, {m.lane_count} lanes, {m.gateway_count} gateways, "
            f"automation {m.automation_rate:.0%}, est. cycle time {m.estimated_cycle_time_minutes:.0f} min"
        )
    if result.bottleneck_report:
        r = result.bottleneck_report
        print(f"Findings: {len(r.findings)}   Recommendations: {len(r.recommendations)} "
              f"(applied: {sum(1 for x in r.recommendations if x.applied)})")
        for f in r.findings:
            print(f"  [{f.severity.upper():6s}] {f.title}")
    if result.conformance:
        c = result.conformance
        print(f"Conformance: {c.summary}")
        for i in c.issues:
            print(f"  [{i.kind}] {i.title}")
    if result.validation and result.validation.warnings:
        print(f"Validation warnings: {len(result.validation.warnings)}")
    if result.warnings:
        for w in result.warnings[:5]:
            print(f"  warning: {w}")
    print("Artifacts:")
    for k, v in sorted(result.artifacts.items()):
        print(f"  {k:40s} {v}")


def cmd_mine(args) -> int:
    settings = load_settings()
    if args.out:
        settings.output_dir = Path(args.out)
    if args.no_optimize:
        settings.apply_optimizations = False
    if args.engine:
        settings.engine = args.engine

    result = run_pipeline(args.source, options=settings, log_path=args.log)
    _print_summary(result)
    return 0


def cmd_analyze_log(args) -> int:
    settings = load_settings()
    if args.out:
        settings.output_dir = Path(args.out)
    result = analyze_log(args.csv, options=settings, threshold_ratio=args.threshold)
    _print_summary(result)
    return 0


def cmd_discover_im(args) -> int:
    settings = load_settings()
    if args.out:
        settings.output_dir = Path(args.out)
    result = discover_im_log(args.csv, options=settings, noise_threshold=args.noise)
    _print_summary(result)
    print("\nProcess tree:")
    print(f"  {result.model.metadata.get('process_tree', '?')}")
    print(
        f"Replay fitness: {result.model.metadata.get('replay_fitness')} "
        f"({result.model.metadata.get('replay_cases_accepted')}/"
        f"{result.model.metadata.get('replay_cases_total')} cases)"
    )
    return 0


def cmd_research_eval(args) -> int:
    from process_miner.research_eval import run_research_eval

    out = Path(args.out) if args.out else Path("outputs/research")
    report = run_research_eval(
        inputs_dir=Path(args.inputs),
        gold_dir=Path(args.gold),
        benchmark_dir=Path(args.benchmarks) if args.benchmarks else None,
        out_dir=out,
        noise_threshold=args.noise,
    )
    print("\n=== Experiment A: SOP extraction (E1 rule parser vs gold) ===")
    summ = report["extraction"]["summary"]
    print(
        f"task P/R/F1: {summ['task_precision']:.2f}/{summ['task_recall']:.2f}/{summ['task_f1']:.2f}"
        f"   actor F1: {summ['actor_f1']:.2f}"
    )
    print("\n=== Experiment B: discovery soundness (E4 DFG vs E6 Inductive Miner) ===")
    header = f"{'log':32s} {'E4 fitness':>10s} {'E6 fitness':>10s} {'E6 coverage':>11s}"
    print(header)
    print("-" * len(header))
    for r in report["discovery"]["rows"]:
        d, i = r["dfg"], r["inductive"]
        d_f = "-" if d["replay_fitness"] is None else f"{d['replay_fitness']:.3f}"
        i_f = "-" if i["replay_fitness"] is None else f"{i['replay_fitness']:.3f}"
        cov = "-" if i.get("variant_coverage") is None else f"{i['variant_coverage']:.3f}"
        print(f"{r['log']:32s} {d_f:>10s} {i_f:>10s} {cov:>11s}")
    print(f"\nReport: {out / 'research_eval.md'}")
    return 0


def cmd_validate(args) -> int:
    report = validate_artifact(args.file)
    if report.ok:
        print(f"OK: {args.file} is valid ({len(report.warnings)} warnings)")
        for w in report.warnings:
            print(f"  warning: {w.message}")
        return 0
    print(f"FAILED: {args.file} has {len(report.errors)} error(s)")
    for e in report.errors:
        print(f"  error: {e.message}")
    return 1


def cmd_eval(args) -> int:
    from process_miner.evaluation import run_evaluation

    out = Path(args.out) if args.out else Path("outputs")
    scores = run_evaluation(gold_dir=Path(args.gold), inputs_dir=Path(args.inputs), out_dir=out)
    print("\n=== Extraction evaluation (offline rule parser vs gold) ===")
    header = f"{'document':28s} {'task P':>7s} {'task R':>7s} {'task F1':>8s} {'actor F1':>9s} {'gw err':>7s}"
    print(header)
    print("-" * len(header))
    for s in scores:
        print(
            f"{s['doc']:28s} {s['task_precision']:7.2f} {s['task_recall']:7.2f} "
            f"{s['task_f1']:8.2f} {s['actor_f1']:9.2f} {s['gateway_error']:7d}"
        )
    print(f"\nReport: {out / 'eval_report.md'}")
    return 0


def cmd_demo(args) -> int:
    settings = load_settings()
    out = Path(args.out) if args.out else Path("outputs/demo")
    settings.output_dir = out
    inputs = Path(args.inputs)
    exit_code = 0

    sops = sorted(inputs.glob("*.md")) + sorted(inputs.glob("*.txt"))
    logs = sorted(inputs.glob("*.csv"))
    if not sops and not logs:
        print(f"No input documents found in {inputs}", file=sys.stderr)
        return 1

    for sop in sops:
        print(f"\n>>> Mining {sop.name}")
        try:
            log = _matching_log(sop, logs)
            result = run_pipeline(str(sop), options=settings, log_path=str(log) if log else None)
            _print_summary(result)
        except Exception as exc:  # keep demoing even if one input fails
            print(f"  ERROR: {exc}", file=sys.stderr)
            exit_code = 1
    for log in logs:
        if any(l and log == l for l in [_matching_log(s, logs) for s in sops]):
            continue  # already consumed by its SOP run
        print(f"\n>>> Analyzing log {log.name}")
        try:
            result = analyze_log(str(log), options=settings)
            _print_summary(result)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            exit_code = 1
    return exit_code


def _matching_log(sop: Path, logs: List[Path]) -> Optional[Path]:
    stem = sop.stem.replace("_sop", "")
    for log in logs:
        log_stem = log.stem.replace("_events", "").replace("_log", "")
        if log_stem == stem or log_stem.startswith(stem) or stem.startswith(log_stem):
            return log
    return None


def cmd_serve(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed; pip install uvicorn", file=sys.stderr)
        return 1
    from process_miner.api import create_app

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="processmind",
        description="ProcessMind - Enterprise AI Process Mining & BPMN Automation",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_mine = sub.add_parser("mine", help="mine an SOP document into BPMN + report")
    p_mine.add_argument("source", help="path to .md/.txt SOP or raw process text")
    p_mine.add_argument("--log", help="optional event-log CSV for real bottleneck stats", default=None)
    p_mine.add_argument("-o", "--out", help="output directory", default=None)
    p_mine.add_argument("--engine", choices=["auto", "builtin", "langgraph"], default="auto")
    p_mine.add_argument("--no-optimize", action="store_true", help="skip As-Is -> To-Be optimization")
    p_mine.set_defaults(func=cmd_mine)

    p_log = sub.add_parser("analyze-log", help="discover a process model from an event log")
    p_log.add_argument("csv", help="event log CSV (case_id, activity, timestamp, ...)")
    p_log.add_argument("-o", "--out", help="output directory", default=None)
    p_log.add_argument("--threshold", type=float, default=0.1, help="DFG edge threshold ratio (0-1)")
    p_log.set_defaults(func=cmd_analyze_log)

    p_im = sub.add_parser("discover-im", help="discover a block-structured model (Inductive Miner)")
    p_im.add_argument("csv", help="event log CSV or XES file")
    p_im.add_argument("-o", "--out", help="output directory", default=None)
    p_im.add_argument("--noise", type=float, default=0.05,
                      help="variant noise threshold for the miner (0-1)")
    p_im.set_defaults(func=cmd_discover_im)

    p_reval = sub.add_parser("research-eval", help="run the unified research evaluation (E1/E4/E6)")
    p_reval.add_argument("--gold", default="eval/gold")
    p_reval.add_argument("--inputs", default="inputs")
    p_reval.add_argument("--benchmarks", default="data/benchmarks",
                         help="synthetic benchmark corpus dir (generated if missing)")
    p_reval.add_argument("-o", "--out", default=None)
    p_reval.add_argument("--noise", type=float, default=0.05, help="Inductive Miner noise threshold")
    p_reval.set_defaults(func=cmd_research_eval)

    p_val = sub.add_parser("validate", help="validate a saved model JSON or BPMN XML file")
    p_val.add_argument("file")
    p_val.set_defaults(func=cmd_validate)

    p_eval = sub.add_parser("eval", help="evaluate extraction quality vs gold annotations")
    p_eval.add_argument("--gold", default="eval/gold")
    p_eval.add_argument("--inputs", default="inputs")
    p_eval.add_argument("-o", "--out", default=None)
    p_eval.set_defaults(func=cmd_eval)

    p_demo = sub.add_parser("demo", help="run the full pipeline over bundled inputs")
    p_demo.add_argument("--inputs", default="inputs")
    p_demo.add_argument("-o", "--out", default=None)
    p_demo.set_defaults(func=cmd_demo)

    p_serve = sub.add_parser("serve", help="start the FastAPI service")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
