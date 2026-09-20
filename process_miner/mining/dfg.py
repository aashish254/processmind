"""DFG (Directly-Follows Graph) discovery and BPMN induction.

The classic process-mining pathway: raw event logs -> directly-follows
relations -> frequency-filtered DFG -> BPMN model with XOR split/join
gateways wherever an activity branches or merges, plus AND split/join
gateways for detected *parallel* blocks.

Parallelism detection uses the footprint discriminator: a mutual pair
(A->B and B->A both observed) is **parallel** iff A and B share the same
entry context (predecessors, incl. start) and the same exit context
(successors, incl. end) outside the pair. A short rework loop (A->X->A)
shares only one side and therefore stays a loop.

This gives the pipeline a *data-driven* extractor that is independent of the
text-based agents: SOP text produces the documented process, event logs
produce the enacted process - comparing the two is a classic conformance /
digraph-vs-reality analysis (see docs/RESEARCH.md).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Set, Tuple

from process_miner.models import NodeType, ProcessModel, TaskKind
from process_miner.mining.event_log import EventLog, directly_follows

_START_CTX = "__start__"
_END_CTX = "__end__"


def detect_parallel_pairs(
    edges: Counter,
    starts: Counter,
    ends: Counter,
) -> List[Tuple[str, str]]:
    """Mutual DFG pairs that share both entry and exit context."""
    preds: Dict[str, Set[str]] = defaultdict(set)
    succs: Dict[str, Set[str]] = defaultdict(set)
    for (a, b) in edges:
        succs[a].add(b)
        preds[b].add(a)

    def pred_ctx(x: str) -> Set[str]:
        return (preds[x]) | ({_START_CTX} if x in starts else set())

    def succ_ctx(x: str) -> Set[str]:
        return (succs[x]) | ({_END_CTX} if x in ends else set())

    activities = sorted({a for a, _ in edges} | {b for _, b in edges})
    pairs: List[Tuple[str, str]] = []
    for i in range(len(activities)):
        for j in range(i + 1, len(activities)):
            a, b = activities[i], activities[j]
            if (a, b) not in edges or (b, a) not in edges:
                continue
            pa = pred_ctx(a) - {b}
            pb = pred_ctx(b) - {a}
            sa = succ_ctx(a) - {b}
            sb = succ_ctx(b) - {a}
            if pa == pb and sa == sb:
                pairs.append((a, b))
    return pairs


def discover_dfg(
    log: EventLog,
    threshold_ratio: float = 0.1,
    name: str = "Discovered process",
) -> ProcessModel:
    dfg, starts, ends = directly_follows(log)
    if not dfg:
        raise ValueError("Event log too small to discover a process")

    max_count = max(dfg.values())
    threshold = max(1, round(threshold_ratio * max_count))
    edges: Counter = Counter({(a, b): c for (a, b), c in dfg.items() if c >= threshold and a != b})

    activities = sorted({a for a, _ in edges} | {b for _, b in edges})

    # resource -> activity mapping (lane assignment)
    actor_of: Dict[str, str] = {}
    res_counter: Dict[str, Counter] = defaultdict(Counter)
    for e in log.events:
        if e.resource:
            res_counter[e.activity][e.resource] += 1
    for act in activities:
        actor_of[act] = res_counter[act].most_common(1)[0][0] if res_counter.get(act) else "System"

    # ---- parallelism detection ------------------------------------------------
    parallel_pairs = detect_parallel_pairs(edges, starts, ends)
    pair_of: Dict[str, Tuple[str, str]] = {}
    for a, b in parallel_pairs:  # greedy: an activity joins at most one pair
        if a not in pair_of and b not in pair_of:
            pair_of[a] = (a, b)
            pair_of[b] = (a, b)

    def rewired(a: str, b: str) -> Tuple[str, str]:
        """Route inter-pair edges through the pair's AND gateways; drop intra-pair."""
        pair_a, pair_b = pair_of.get(a), pair_of.get(b)
        if pair_a is not None and pair_a == pair_b:
            return "", ""  # interleaving artifact inside a parallel block
        return (
            f"andjoin::{pair_a[0]}+{pair_a[1]}" if pair_a is not None else a,
            f"andsplit::{pair_b[0]}+{pair_b[1]}" if pair_b is not None else b,
        )

    # build the rewired edge set (activity-level names; gateways get ids later)
    rewired_edges: Counter = Counter()
    for (a, b), count in edges.items():
        ra, rb = rewired(a, b)
        if ra:
            rewired_edges[(ra, rb)] += count
    start_edges: List[Tuple[str, str, int]] = []
    for act, count in starts.most_common():
        if act not in pair_of or act not in activities:
            if act in activities:
                start_edges.append(("__start__", act, count))
            continue
        pair = pair_of[act]
        if pair[0] == act:  # route only once per pair
            start_edges.append(("__start__", f"andsplit::{pair[0]}+{pair[1]}", sum(starts[x] for x in pair if x in starts)))
    end_edges: List[Tuple[str, str, int]] = []
    for act, count in ends.most_common():
        if act not in pair_of or act not in activities:
            if act in activities:
                end_edges.append((act, "__end__", count))
            continue
        pair = pair_of[act]
        if pair[0] == act:
            end_edges.append((f"andjoin::{pair[0]}+{pair[1]}", "__end__", sum(ends[x] for x in pair if x in ends)))

    # degrees computed on the rewired graph
    out_deg: Dict[str, int] = Counter(a for (a, _b) in rewired_edges)
    in_deg: Dict[str, int] = Counter(b for (_a, b) in rewired_edges)

    model = ProcessModel(
        id="pm_dfg",
        name=name,
        description=(
            f"Discovered from {log.source or 'event log'}: {log_summary_counts(log)} "
            f"(edge threshold {threshold}/{max_count})"
        ),
        metadata={
            "extractor": "dfg-mining",
            "threshold": threshold,
            "max_edge_count": max_count,
            "cases": len({e.case_id for e in log.events}),
            "parallel_pairs": [list(p) for p in parallel_pairs],
        },
    )

    task_ids: Dict[str, str] = {}
    for act in activities:
        node = model.add_node(act, NodeType.TASK, kind=TaskKind.USER, actor=actor_of.get(act))
        task_ids[act] = node.id

    # AND split/join per parallel pair
    and_split: Dict[Tuple[str, str], str] = {}
    and_join: Dict[Tuple[str, str], str] = {}
    for a, b in parallel_pairs:
        if pair_of.get(a) != (a, b):
            continue  # skipped by greedy assignment
        split = model.add_node(f"{a} / {b} (parallel)", NodeType.AND_GATEWAY)
        join = model.add_node("", NodeType.AND_GATEWAY)
        and_split[(a, b)] = split.id
        and_join[(a, b)] = join.id
        model.add_flow(split.id, task_ids[a])
        model.add_flow(split.id, task_ids[b])
        model.add_flow(task_ids[a], join.id)
        model.add_flow(task_ids[b], join.id)

    def node_id_for(name: str) -> str:
        if name.startswith("andsplit::"):
            return and_split[tuple(name.split("::", 1)[1].split("+"))]
        if name.startswith("andjoin::"):
            return and_join[tuple(name.split("::", 1)[1].split("+"))]
        if name == "__start__" or name == "__end__":
            return name
        return task_ids[name]

    start = model.add_node("Case started", NodeType.START_EVENT)
    end = model.add_node("Case closed", NodeType.END_EVENT)

    # XOR splits/joins for branching outside parallel blocks
    split_ids: Dict[str, str] = {}
    join_ids: Dict[str, str] = {}
    for act in sorted(out_deg):
        if out_deg[act] > 1 and not act.startswith(("andsplit::", "andjoin::")):
            gw = model.add_node("", NodeType.XOR_GATEWAY)
            model.add_flow(node_id_for(act), gw.id)
            split_ids[act] = gw.id
    for act in sorted(in_deg):
        if in_deg[act] > 1 and not act.startswith(("andsplit::", "andjoin::")):
            gw = model.add_node("", NodeType.XOR_GATEWAY)
            model.add_flow(gw.id, node_id_for(act))
            join_ids[act] = gw.id

    def exit_id(a: str) -> str:
        if a.startswith(("andsplit::", "andjoin::")):
            return node_id_for(a)  # gateways route directly
        return split_ids.get(a, node_id_for(a))

    def entry_id(b: str) -> str:
        if b.startswith(("andsplit::", "andjoin::")):
            return node_id_for(b)
        return join_ids.get(b, node_id_for(b))

    for (a, b), count in sorted(rewired_edges.items()):
        src, tgt = exit_id(a), entry_id(b)
        if src == tgt:
            continue
        model.add_flow(src, tgt, f"{count}" if count > 1 else None)
    for (_s, act, count) in start_edges:
        model.add_flow(start.id, entry_id(act), f"{count} cases" if count > 1 else None)
    for (act, _e, count) in end_edges:
        model.add_flow(exit_id(act), end.id, f"{count} cases" if count > 1 else None)

    return model


def log_summary_counts(log: EventLog) -> str:
    cases = len({e.case_id for e in log.events})
    acts = len({e.activity for e in log.events})
    return f"{cases} cases, {acts} activities"
