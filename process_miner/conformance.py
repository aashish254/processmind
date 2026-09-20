"""Conformance checking: documented (SOP) model vs discovered (event-log) model.

The two extractors produce comparable artifacts on purpose. This module aligns
them (fuzzy activity matching), compares their directly-follows relations, and
reports *documentation drift*:

* activities documented but never enacted (policy that reality ignores),
* activities enacted but never documented (shadow work),
* sequence differences (handovers only in the SOP or only in the log),
* rework loops observed in the log but not modelled in the SOP.

Two simple indicators are reported: directly-follows **recall** ("fitness
proxy": how much observed behaviour the documented model explains) and
directly-follows **precision** (how much of the documented flow is observed).
They are heuristics, not token-based fitness — the naming keeps that honest.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from process_miner.mining.event_log import EventLog, LogSummary, directly_follows
from process_miner.models import (
    ActivityMatch,
    ConformanceIssue,
    ConformanceReport,
    NodeType,
    ProcessModel,
)

__all__ = [
    "ActivityMatch",
    "ConformanceIssue",
    "ConformanceReport",
    "match_activities",
    "compare_models",
]


def _stem(token: str) -> str:
    for suf in ("ation", "ition", "tion", "sion", "ing", "ised", "ized", "ed", "es", "ly", "s"):
        if token.endswith(suf) and len(token) - len(suf) >= 3:
            return token[: -len(suf)]
    return token


_STOP = {"the", "a", "an", "of", "to", "and", "for", "in", "on"}


def _tokens(name: str) -> Set[str]:
    return {_stem(t) for t in name.lower().split() if t not in _STOP and t.isalpha()}


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def match_activities(
    documented_names: List[str], enacted_names: List[str], threshold: float = 0.5
) -> Tuple[List[ActivityMatch], Dict[str, str], Dict[str, str]]:
    """Greedy best-first matching between documented and enacted activity names."""
    scored: List[Tuple[float, int, int]] = []
    for i, d in enumerate(documented_names):
        for j, e in enumerate(enacted_names):
            s = _similarity(d, e)
            if s >= threshold:
                scored.append((s, i, j))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_d, used_e = set(), set()
    matches: List[ActivityMatch] = []
    d_to_e: Dict[str, str] = {}
    e_to_d: Dict[str, str] = {}
    for s, i, j in scored:
        if i in used_d or j in used_e:
            continue
        used_d.add(i)
        used_e.add(j)
        d, e = documented_names[i], enacted_names[j]
        matches.append(ActivityMatch(documented=d, enacted=e, similarity=round(s, 3)))
        d_to_e[d] = e
        e_to_d[e] = d
    return matches, d_to_e, e_to_d


def _documented_directly_follows(model: ProcessModel) -> Set[Tuple[str, str]]:
    """Directly-follows pairs over task names, skipping gateways/events between."""
    pairs: Set[Tuple[str, str]] = set()

    def next_tasks(start: str) -> List[str]:
        found: List[str] = []
        seen = {start}
        frontier = [start]
        while frontier:
            cur = frontier.pop()
            for nxt in model.out_nodes(cur):
                node = model.node(nxt)
                if node is None:
                    continue
                if node.type == NodeType.TASK:
                    found.append(node.name)
                elif nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        return found

    for task in model.tasks():
        for target in next_tasks(task.id):
            if target != task.name:
                pairs.add((task.name, target))
    return pairs


def _enacted_directly_follows(log: EventLog) -> Set[Tuple[str, str]]:
    dfg, _, _ = directly_follows(log)
    return set(dfg.keys())


def _documented_rework_targets(model: ProcessModel) -> Set[str]:
    targets = set()
    for f in model.flows:
        if (f.label or "").lower() == "rework":
            node = model.node(f.target)
            if node is not None and node.type == NodeType.TASK:
                targets.add(node.name)
            else:
                # rework enters a merge gateway -> find the task it feeds
                for nxt in model.out_nodes(f.target):
                    n = model.node(nxt)
                    if n is not None and n.type == NodeType.TASK:
                        targets.add(n.name)
    return targets


def _rework_explained_tasks(model: ProcessModel) -> Set[str]:
    """Tasks whose repetition is explained by documented rework loops.

    Everything transitively reachable from a rework loop entry point can
    legitimately re-execute (Approve -> Check -> Approve ...).
    """
    seeds = _documented_rework_targets(model)
    explained = set(seeds)
    frontier = [t.id for t in model.tasks() if t.name in seeds]
    seen = set(frontier)
    while frontier:
        cur = frontier.pop()
        for nxt in model.out_nodes(cur):
            node = model.node(nxt)
            if node is None:
                continue
            if node.type == NodeType.TASK:
                explained.add(node.name)
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return explained


def _documented_parallel_blocks(model: ProcessModel) -> List[Set[str]]:
    """Task sets executed between AND splits and their joins (any order fits)."""
    blocks: List[Set[str]] = []
    for g in model.gateways():
        if g.type != NodeType.AND_GATEWAY or len(model.out_nodes(g.id)) < 2:
            continue
        branches = model.out_nodes(g.id)
        reach_sets = []
        for b in branches:
            reach: Set[str] = set()
            frontier = [b]
            seen = {g.id, b}
            while frontier:
                cur = frontier.pop()
                node = model.node(cur)
                if node is not None and node.type == NodeType.TASK:
                    reach.add(node.name)
                    continue  # block members stop; successors explored from the join side
                for nxt in model.out_nodes(cur):
                    if nxt not in seen:
                        seen.add(nxt)
                        frontier.append(nxt)
            reach_sets.append(reach)
        members: Set[str] = set().union(*reach_sets) if reach_sets else set()
        if len(members) >= 2:
            blocks.append(members)
    return blocks


def footprint_fitness(documented: ProcessModel, log: EventLog, e_to_d: Optional[Dict[str, str]] = None) -> float:
    """Trace-weighted share of observed handovers the documented model allows.

    Traces are first translated into the documented naming space via the
    activity match map; unmatched activities drop out of the replay. A
    directly-follows pair (a, b) fits when the documented model contains the
    a->b relation (gateways skipped), or a and b sit in the same AND block
    (parallel work may interleave in any order).
    """
    allowed = _documented_directly_follows(documented)
    blocks = _documented_parallel_blocks(documented)
    for block in blocks:
        for a in block:
            for b in block:
                if a != b:
                    allowed.add((a, b))
    e_to_d = e_to_d or {}

    fitting = 0
    total = 0
    for evs in log.cases.values():
        seq = [e_to_d.get(e.activity, e.activity) for e in sorted(evs, key=lambda e: e.ts)]
        seq = [a for a in seq if a in {t.name for t in documented.tasks()}]  # replayable names only
        for a, b in zip(seq, seq[1:]):
            total += 1
            if (a, b) in allowed:
                fitting += 1
    return round(fitting / total, 3) if total else 1.0


def compare_models(
    documented: ProcessModel,
    log: EventLog,
    log_summary: Optional[LogSummary] = None,
    match_threshold: float = 0.5,
) -> ConformanceReport:
    sop_names = [t.name for t in documented.tasks()]
    enacted_names = sorted({e.activity for e in log.events})
    matches, d_to_e, e_to_d = match_activities(sop_names, enacted_names, match_threshold)

    documented_only = sorted(n for n in sop_names if n not in d_to_e)
    enacted_only = sorted(n for n in enacted_names if n not in e_to_d)

    sop_pairs = _documented_directly_follows(documented)
    log_pairs = _enacted_directly_follows(log)
    # translate observed pairs into the documented naming space
    explained_pairs = {
        (e_to_d[a], e_to_d[b])
        for (a, b) in log_pairs
        if a in e_to_d and b in e_to_d
    }
    common = sop_pairs & explained_pairs
    df_recall = round(len(common) / len(explained_pairs), 3) if explained_pairs else 1.0
    df_precision = round(len(common) / len(sop_pairs), 3) if sop_pairs else 1.0

    seq_doc_only = sorted(f"{a}  →  {b}" for (a, b) in sop_pairs - explained_pairs)
    seq_enacted_only = sorted(f"{a}  →  {b}" for (a, b) in explained_pairs - sop_pairs)

    # rework drift: observed repeats with no explanation in the documented model
    rework_targets_doc = {d_to_e.get(t, t) for t in _rework_explained_tasks(documented)}
    rework_drift: List[str] = []
    if log_summary is not None:
        for act in log_summary.activities:
            if act.rework_rate >= 0.1 and act.name not in rework_targets_doc:
                rework_drift.append(act.name)

    issues: List[ConformanceIssue] = []
    if documented_only:
        issues.append(
            ConformanceIssue(
                kind="documented_not_enacted",
                severity="medium",
                title=f"{len(documented_only)} documented step(s) never observed in the log",
                description=(
                    "These steps appear in the SOP but no matching activity was found in the "
                    "event log — the documented policy may not be enacted, or the log uses a "
                    "different vocabulary."
                ),
                evidence=documented_only,
            )
        )
    if enacted_only:
        issues.append(
            ConformanceIssue(
                kind="enacted_not_documented",
                severity="high",
                title=f"{len(enacted_only)} enacted step(s) missing from the SOP",
                description=(
                    "Work observed in the event log that the documented process does not "
                    "describe (shadow work or outdated documentation)."
                ),
                evidence=enacted_only,
            )
        )
    if seq_enacted_only:
        issues.append(
            ConformanceIssue(
                kind="sequence_mismatch",
                severity="medium",
                title=f"{len(seq_enacted_only)} handover(s) observed in the log but not documented",
                description="Directly-follows relations present in reality but absent from the SOP model (after activity matching).",
                evidence=seq_enacted_only[:12],
            )
        )
    if seq_doc_only:
        issues.append(
            ConformanceIssue(
                kind="sequence_mismatch",
                severity="low",
                title=f"{len(seq_doc_only)} documented handover(s) not observed in the log",
                description="Directly-follows relations documented in the SOP but not present in the observed behaviour.",
                evidence=seq_doc_only[:12],
            )
        )
    if rework_drift:
        issues.append(
            ConformanceIssue(
                kind="rework_mismatch",
                severity="medium",
                title=f"Rework observed on {len(rework_drift)} activity(ies) without a documented rework loop",
                description="The log shows repeated executions within cases, but the SOP model has no return path for them.",
                evidence=rework_drift,
            )
        )

    parts = [
        f"{len(matches)}/{len(sop_names)} documented activities matched to the log",
        f"directly-follows precision {df_precision:.0%}, recall {df_recall:.0%}",
    ]
    fitness = footprint_fitness(documented, log, e_to_d)
    parts.append(f"trace fitness {fitness:.0%}")
    if fitness < 0.8:
        issues.append(
            ConformanceIssue(
                kind="low_fitness",
                severity="high" if fitness < 0.5 else "medium",
                title=f"Only {fitness:.0%} of observed handovers fit the documented model",
                description=(
                    "Walking every trace, most directly-follows transitions cannot be replayed "
                    "on the SOP model - the documented process diverges substantially from "
                    "reality (after activity matching)."
                ),
                evidence=[f"footprint fitness: {fitness:.0%}"],
            )
        )
    if issues:
        parts.append(f"{len(issues)} drift issue(s)")
    else:
        parts.append("no drift detected")
    summary_text = "; ".join(parts)

    return ConformanceReport(
        matched_activities=matches,
        documented_only=documented_only,
        enacted_only=enacted_only,
        sequence_documented_only=seq_doc_only,
        sequence_enacted_only=seq_enacted_only,
        rework_drift=rework_drift,
        df_precision=df_precision,
        df_recall=df_recall,
        fitness=fitness,
        issues=issues,
        summary=summary_text,
    )
