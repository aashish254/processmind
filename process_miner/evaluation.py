"""Extraction-quality evaluation harness (the research experiment).

Compares an extractor's ProcessModel against hand-annotated *gold* models:

* task precision / recall / F1 via greedy token-similarity matching,
* actor (lane) precision / recall / F1,
* gateway-count absolute error (XOR and AND),
* rework-loop count error.

Used two ways in the capstone:
1. quantify the offline rule parser's quality (baseline extractor),
2. the same harness scores the LLM agent when a provider key is configured -
   giving the thesis its rule-based-vs-LLM comparison table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from process_miner.agents.ingestion import IngestionAgent
from process_miner.agents.modeler import ProcessModelerAgent
from process_miner.models import ProcessModel

STOP = {"the", "a", "an", "of", "to", "and", "for", "in", "on"}


def _tokens(name: str) -> set:
    from process_miner.agents.offline_parser import _stem

    return {_stem(t) for t in name.lower().split() if t not in STOP and t.isalpha()}


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def match_tasks(extracted: List[str], gold: List[str], threshold: float = 0.5) -> Tuple[List[Tuple[str, str]], List[str], List[str]]:
    """Greedy matching: best similarity first, each task used once."""
    pairs: List[Tuple[float, int, int]] = []
    for i, e in enumerate(extracted):
        for j, g in enumerate(gold):
            s = _similarity(e, g)
            if s >= threshold:
                pairs.append((s, i, j))
    pairs.sort(reverse=True)
    used_i, used_j = set(), set()
    matches: List[Tuple[str, str]] = []
    for s, i, j in pairs:
        if i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        matches.append((extracted[i], gold[j]))
    missed = [g for j, g in enumerate(gold) if j not in used_j]
    extra = [e for i, e in enumerate(extracted) if i not in used_i]
    return matches, missed, extra


def _prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def evaluate_model(model: ProcessModel, gold: dict) -> Dict:
    extracted_tasks = [t.name for t in model.tasks() if t.name]
    gold_tasks = gold.get("tasks", [])
    matches, missed, extra = match_tasks(extracted_tasks, gold_tasks)

    tp = len(matches)
    p, r, f = _prf(tp, len(extra), len(missed))

    extracted_actors = set(model.actors()) - {"Unassigned"}
    gold_actors = set(gold.get("actors", []))
    # actors matched with fuzzy containment (e.g. "Finance" ~ "Finance Manager")
    matched_actors = set()
    for ga in gold_actors:
        for ea in extracted_actors:
            if _actor_match(ea, ga):
                matched_actors.add(ga)
                break
    ap, ar, af = _prf(len(matched_actors), len(extracted_actors - {e for e in extracted_actors if any(_actor_match(e, g) for g in gold_actors)}),
                      len(gold_actors - matched_actors))

    gw_x = sum(1 for g in model.gateways() if g.type.value == "xor_gateway")
    gw_a = sum(1 for g in model.gateways() if g.type.value == "and_gateway")
    gold_gw = gold.get("gateways", {})
    gw_err = abs(gw_x - gold_gw.get("xor", 0)) + abs(gw_a - gold_gw.get("and", 0))

    rework = sum(1 for f in model.flows if (f.label or "").lower() == "rework")
    gold_rework = gold.get("rework_loops", 0)
    rework_err = abs(rework - gold_rework)

    return {
        "doc": gold.get("doc", model.name),
        "task_precision": p,
        "task_recall": r,
        "task_f1": f,
        "matched_tasks": [m[0] for m in matches],
        "missed_tasks": missed,
        "extra_tasks": extra,
        "actor_precision": ap,
        "actor_recall": ar,
        "actor_f1": af,
        "gateway_error": gw_err,
        "rework_error": rework_err,
        "extracted_task_count": len(extracted_tasks),
        "gold_task_count": len(gold_tasks),
    }


def _actor_match(a: str, b: str) -> bool:
    ta, tb = {t for t in a.lower().split() if t not in STOP}, {t for t in b.lower().split() if t not in STOP}
    return bool(ta & tb)


def evaluate_extractor(inputs_dir: Path, gold_dir: Path, use_llm: bool = False) -> List[Dict]:
    """Run the chosen extractor over every gold-annotated document."""
    provider = None
    if use_llm:
        from process_miner.config import load_settings
        from process_miner.llm.providers import build_provider

        provider = build_provider(load_settings().llm)
    agent = ProcessModelerAgent(provider=provider)
    results: List[Dict] = []
    for gold_file in sorted(gold_dir.glob("*.json")):
        gold = json.loads(gold_file.read_text())
        doc_path = inputs_dir / gold["doc"]
        if not doc_path.exists():
            continue
        doc = IngestionAgent().run(str(doc_path))
        out = agent.run(doc)
        results.append(evaluate_model(out.model, gold))
    return results


def run_evaluation(gold_dir: Path, inputs_dir: Path, out_dir: Path) -> List[Dict]:
    gold_dir = Path(gold_dir)
    inputs_dir = Path(inputs_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scores = evaluate_extractor(inputs_dir, gold_dir, use_llm=False)

    (out_dir / "eval_report.json").write_text(json.dumps(scores, indent=2))

    def avg(key: str) -> float:
        vals = [s[key] for s in scores] or [0.0]
        return sum(vals) / len(vals)

    md = [
        "# Extraction evaluation - offline rule parser vs gold annotations",
        "",
        "| document | task P | task R | task F1 | actor F1 | gateway err | rework err |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        md.append(
            f"| {s['doc']} | {s['task_precision']:.2f} | {s['task_recall']:.2f} | {s['task_f1']:.2f} "
            f"| {s['actor_f1']:.2f} | {s['gateway_error']} | {s['rework_error']} |"
        )
    md += [
        "",
        f"**Macro averages** - task P/R/F1: {avg('task_precision'):.2f}/{avg('task_recall'):.2f}/{avg('task_f1'):.2f}, "
        f"actor F1: {avg('actor_f1'):.2f}",
        "",
        "## Notes",
        "",
        "- Task matching uses greedy token-stem similarity (threshold 0.5); see `process_miner.evaluation`.",
        "- The same harness scores the LLM extractor when a provider key is configured, "
        "enabling the rule-based vs LLM comparison (docs/RESEARCH.md).",
        "",
    ]
    if scores:
        for s in scores:
            if s["missed_tasks"]:
                md.append(f"- **{s['doc']}** missed: {', '.join(s['missed_tasks'])}")
            if s["extra_tasks"]:
                md.append(f"- **{s['doc']}** extra: {', '.join(s['extra_tasks'][:6])}")
    (out_dir / "eval_report.md").write_text("\n".join(md) + "\n")
    return scores
