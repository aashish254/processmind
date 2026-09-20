"""Mini Inductive Miner: discover block-structured process trees from traces.

Ported from the bpmn-miner capstone (cap 5) into the merged ProcessMind
framework. Implements the classic cut hierarchy of Leemans et al. in a
simplified but test-covered form:

    xor cut  ->  DFG disconnected into components
    seq cut  ->  strongly-connected-component condensation is a DAG with
                 >1 node (co-occurring SCCs without connecting edges are
                 merged for precision)
    par cut  ->  complete-bipartite both-directions relation between two sets
    loop cut ->  a shared start/end activity with "redo" runs returning to it

If no cut applies and ``allow_flower_fallback`` is set, a flower model
(sound for any log) is produced and flagged. Because every cut is language-
preserving, the resulting process tree replays the filtered log perfectly,
which is what makes block-structured BPMN output trustworthy.

Research role (docs/RESEARCH.md): this is extractor **E6** in the merged
study - a *guaranteed-sound* discovery baseline against which the DFG miner
(E4) and the LLM agents (E2/E3) are compared.

Semantics notes:
* Sequence-cut blocks may be skipped by a trace, so projections keep empty
  traces and the recursion wraps non-empty block models in ``xor(B, tau)``.
* Empty sublogs become ``tau``.

Input contract: callers pass a *variant multiset* ``{trace: case_count}``.
Use :func:`variants_from_event_log` to build one from the pipeline's own
:class:`process_miner.mining.event_log.EventLog`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

Trace = Tuple[str, ...]
Sublog = Dict[Trace, int]  # variant -> case count


class DiscoveryError(RuntimeError):
    pass


@dataclass
class ProcessTree:
    op: str  # leaf | tau | seq | xor | par | loop
    children: List["ProcessTree"] = field(default_factory=list)
    label: Optional[str] = None
    note: Optional[str] = None

    def is_leaf(self) -> bool:
        return self.op == "leaf"

    def to_json(self) -> dict:
        if self.op in {"leaf", "tau"}:
            return {"op": self.op, "label": self.label}
        return {"op": self.op, "children": [c.to_json() for c in self.children]}


def tree_to_text(tree: ProcessTree) -> str:
    if tree.op == "leaf":
        return tree.label or "?"
    if tree.op == "tau":
        return "tau"
    inner = ", ".join(tree_to_text(c) for c in tree.children)
    return f"{tree.op}({inner})"


def variants_from_event_log(log) -> Dict[Trace, int]:
    """Build the variant multiset from the pipeline's pydantic ``EventLog``.

    Cases are ordered by timestamp (stable on activity), matching the
    behaviour of the DFG miner so both extractors see identical input.
    """
    grouped: Dict[str, List] = {}
    for e in log.events:
        grouped.setdefault(e.case_id, []).append(e)
    variants: Dict[Trace, int] = {}
    for events in grouped.values():
        events.sort(key=lambda e: (e.ts, e.activity))
        trace = tuple(e.activity for e in events)
        variants[trace] = variants.get(trace, 0) + 1
    return variants


# ---------------------------------------------------------------------------
# log abstraction helpers
# ---------------------------------------------------------------------------

def _abstraction(sublog: Sublog) -> Tuple[Dict[Tuple[str, str], int], Dict[str, int], Dict[str, int], Set[str]]:
    edges: Dict[Tuple[str, str], int] = {}
    starts: Dict[str, int] = {}
    ends: Dict[str, int] = {}
    acts: Set[str] = set()
    for trace, count in sublog.items():
        if not trace:
            continue
        acts.update(trace)
        starts[trace[0]] = starts.get(trace[0], 0) + count
        ends[trace[-1]] = ends.get(trace[-1], 0) + count
        for i in range(len(trace) - 1):
            key = (trace[i], trace[i + 1])
            edges[key] = edges.get(key, 0) + count
    return edges, starts, ends, acts


def _project(sublog: Sublog, keep: Set[str], keep_empty: bool = False) -> Sublog:
    out: Sublog = {}
    for trace, count in sublog.items():
        proj = tuple(a for a in trace if a in keep)
        if proj or (keep_empty and trace):
            out[proj] = out.get(proj, 0) + count
    return out


def _undirected_components(acts: Set[str], edges: Dict[Tuple[str, str], int]) -> List[Set[str]]:
    parent = {a: a for a in acts}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b) in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    groups: Dict[str, Set[str]] = {}
    for a in acts:
        groups.setdefault(find(a), set()).add(a)
    return sorted(groups.values(), key=lambda s: sorted(s)[0])


def _tarjan_sccs(acts: Set[str], edges: Dict[Tuple[str, str], int]) -> List[Set[str]]:
    """Iterative Tarjan SCC over the directed DFG."""
    adj: Dict[str, List[str]] = {a: [] for a in acts}
    for (a, b) in edges:
        if a in adj and b in adj and a != b:
            adj[a].append(b)
    index_counter = [0]
    stack: List[str] = []
    on_stack: Set[str] = set()
    index: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    result: List[Set[str]] = []

    for root in sorted(acts):
        if root in index:
            continue
        work: List[Tuple[str, int]] = [(root, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = lowlink[node] = index_counter[0]
                index_counter[0] += 1
                stack.append(node)
                on_stack.add(node)
            recurse = False
            successors = adj[node]
            for i in range(pi, len(successors)):
                succ = successors[i]
                if succ not in index:
                    work[-1] = (node, i + 1)
                    work.append((succ, 0))
                    recurse = True
                    break
                elif succ in on_stack:
                    lowlink[node] = min(lowlink[node], index[succ])
            if recurse:
                continue
            if lowlink[node] == index[node]:
                comp: Set[str] = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.add(w)
                    if w == node:
                        break
                result.append(comp)
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
    return result


def _reachable(edges: Dict[Tuple[str, str], int], src: str, dst: str) -> bool:
    if src == dst:
        return True
    adj: Dict[str, List[str]] = {}
    for (a, b) in edges:
        adj.setdefault(a, []).append(b)
    seen = {src}
    frontier = [src]
    while frontier:
        node = frontier.pop()
        for b in adj.get(node, ()):
            if b == dst:
                return True
            if b not in seen:
                seen.add(b)
                frontier.append(b)
    return False


# ---------------------------------------------------------------------------
# cut detectors: each returns (op, child-sublogs) or None
# ---------------------------------------------------------------------------

def _cut_xor(sublog: Sublog, edges, starts, ends, acts) -> Optional[Tuple[str, List[Sublog]]]:
    comps = _undirected_components(acts, edges)
    if len(comps) <= 1:
        return None
    parts = [_project(sublog, comp) for comp in comps]
    if any(not p for p in parts):
        return None
    return "xor", parts


def _cut_seq(sublog: Sublog, edges, starts, ends, acts) -> Optional[Tuple[str, List[Sublog]]]:
    sccs = _tarjan_sccs(acts, edges)
    if len(sccs) <= 1:
        return None
    comp_of: Dict[str, int] = {}
    for i, comp in enumerate(sccs):
        for a in comp:
            comp_of[a] = i
    condensation: Set[Tuple[int, int]] = set()
    for (a, b) in edges:
        ca, cb = comp_of[a], comp_of[b]
        if ca != cb:
            condensation.add((ca, cb))

    preds: Dict[int, Set[int]] = {i: set() for i in range(len(sccs))}
    for (u, v) in condensation:
        preds[v].add(u)
    level: Dict[int, int] = {}
    remaining = set(range(len(sccs)))
    while remaining:
        progressed = False
        for node in sorted(remaining):
            if all(p in level for p in preds[node]):
                level[node] = max((level[p] + 1 for p in preds[node]), default=0)
                remaining.discard(node)
                progressed = True
        if not progressed:  # pragma: no cover - condensation is a DAG
            break

    by_level: Dict[int, List[int]] = {}
    for node, lv in level.items():
        by_level.setdefault(lv, []).append(node)
    blocks: List[Set[str]] = []
    for lv in sorted(by_level):
        block: Set[str] = set()
        for node in by_level[lv]:
            block |= sccs[node]
        blocks.append(block)

    # Precision pass: merge consecutive blocks that are *optionally* co-occurring:
    # every trace has either both blocks or neither. This keeps the language
    # identical while letting recursion recover the inner structure (e.g. an
    # optional seq(Ship, Send) pair vs a Reject branch). Blocks that are always
    # present must NOT be merged (the recursion would just re-merge them).
    changed = True
    while changed and len(blocks) > 1:
        changed = False
        for i in range(len(blocks) - 1):
            a, b = blocks[i], blocks[i + 1]
            patterns = {(any(x in a for x in trace), any(x in b for x in trace)) for trace in sublog}
            if patterns <= {(True, True), (False, False)} and (False, False) in patterns:
                blocks[i:i + 2] = [a | b]
                changed = True
                break

    parts = [_project(sublog, block, keep_empty=True) for block in blocks]
    if len(parts) <= 1:
        return None
    return "seq", parts


def _cut_par(sublog: Sublog, edges, starts, ends, acts) -> Optional[Tuple[str, List[Sublog]]]:
    for seed in sorted(acts):
        related = {b for (a, b) in edges if a == seed and b != seed} | \
                  {a for (a, b) in edges if b == seed and a != seed}
        set_b = related & acts
        set_a = (acts - set_b - {seed}) | {seed}
        if not set_b:
            continue
        both = 0
        ok = True
        for a in sorted(set_a):
            for b in sorted(set_b):
                ab = (a, b) in edges
                ba = (b, a) in edges
                if ab and ba:
                    both += 1
                elif ab or ba:
                    ok = False
                    break
            if not ok:
                break
        if not ok or both == 0:
            continue
        # IM validity: every parallel branch needs its own start and end activity
        if not (set_a & set(starts) and set_a & set(ends) and set_b & set(starts) and set_b & set(ends)):
            continue
        # Soundness guard: par(A, B) executes *both* branches, so a trace that
        # touches only one side of the partition can never replay. Rejecting
        # the cut here keeps the language-preserving guarantee intact.
        if not all(
            any(x in set_a for x in trace) and any(x in set_b for x in trace)
            for trace in sublog
            if trace
        ):
            continue
        return "par", [_project(sublog, set_a), _project(sublog, set_b)]
    return None


def _cut_loop(sublog: Sublog, edges, starts, ends, acts) -> Optional[Tuple[str, List[Sublog]]]:
    overlap = set(starts) & set(ends)
    for a in sorted(overlap):
        redo = {x for x in acts if x != a and (x, a) in edges}
        redo = {x for x in redo if (a, x) in edges or _reachable(edges, a, x)}
        if not redo:
            continue
        body_acts = acts - redo
        if a not in body_acts:
            continue
        body_segments: List[Trace] = []
        redo_runs: List[Trace] = []
        valid = True
        for trace, _count in sublog.items():
            if not trace:
                continue
            if trace[0] != a or trace[-1] != a:
                valid = False
                break
            run: List[str] = []
            for i, act in enumerate(trace):
                if act in redo:
                    # a redo run must start right after `a`
                    if not run and (i == 0 or trace[i - 1] != a):
                        valid = False
                        break
                    run.append(act)
                else:
                    if run:
                        # a redo run must end right before `a`
                        if act != a:
                            valid = False
                            break
                        redo_runs.append(tuple(run))
                        run = []
                    if i == 0 and act != a:  # first body segment starts with a
                        valid = False
                        break
            if run:
                valid = False  # trace ends inside a redo run
            if not valid:
                break
            # split into body segments: cut at redo-run boundaries
            segments: List[List[str]] = [[]]
            i = 0
            while i < len(trace):
                if trace[i] in redo:
                    j = i
                    while j < len(trace) and trace[j] in redo:
                        j += 1
                    segments.append([])  # start a new body segment after the run
                    i = j
                else:
                    segments[-1].append(trace[i])
                    i += 1
            body_segments.extend(tuple(s) for s in segments if s)
        if not valid or not redo_runs or not body_segments:
            continue
        body_log: Sublog = {}
        for seg in body_segments:
            body_log[seg] = body_log.get(seg, 0) + 1
        redo_log: Sublog = {}
        for run in redo_runs:
            redo_log[run] = redo_log.get(run, 0) + 1
        return "loop", [body_log, redo_log]
    return None


# ---------------------------------------------------------------------------
# recursive miner
# ---------------------------------------------------------------------------

_CUT_ORDER = (_cut_xor, _cut_seq, _cut_par, _cut_loop)


def _mine_recursive(sublog: Sublog, allow_flower: bool, depth: int = 0,
                    notes: Optional[List[str]] = None) -> ProcessTree:
    notes = notes if notes is not None else []
    if depth > 200:  # pragma: no cover - defensive
        raise DiscoveryError("cut recursion exceeded depth limit")

    total = sum(sublog.values())
    empty = sublog.get((), 0)
    if total == 0 or not any(sublog):
        return ProcessTree(op="tau")
    if empty == total:
        return ProcessTree(op="tau")
    if empty > 0:
        # Sequence-cut block skipped by some traces: optional fragment.
        nonempty = {t: c for t, c in sublog.items() if t}
        inner = _mine_recursive(nonempty, allow_flower, depth + 1, notes)
        return ProcessTree(op="xor", children=[inner, ProcessTree(op="tau")])

    edges, starts, ends, acts = _abstraction(sublog)

    if len(acts) == 1:
        only = next(iter(acts))
        has_repeat = any(len(t) >= 2 for t in sublog if t)
        if has_repeat and (only, only) in edges:
            return ProcessTree(op="loop", children=[ProcessTree(op="leaf", label=only),
                                                    ProcessTree(op="leaf", label=only)])
        return ProcessTree(op="leaf", label=only)

    for detector in _CUT_ORDER:
        result = detector(sublog, edges, starts, ends, acts)
        if result is None:
            continue
        op, parts = result
        children = [_mine_recursive(part, allow_flower, depth + 1, notes) for part in parts]
        if op == "xor" and len(children) == 1:
            return children[0]
        return ProcessTree(op=op, children=children)

    if allow_flower:
        notes.append("flower fallback for fragment {" + ", ".join(sorted(acts)[:8]) + "}")
        return ProcessTree(op="loop", children=[
            ProcessTree(op="tau"),
            ProcessTree(op="xor", children=[ProcessTree(op="leaf", label=a) for a in sorted(acts)]),
        ])
    raise DiscoveryError(
        f"no process-tree cut applies to fragment with activities {sorted(acts)}")


def filter_variants(traces: Sequence[Tuple[Trace, int]], noise_threshold: float) -> Tuple[Sublog, int]:
    """Keep frequent variants: those whose own share is at least
    ``noise_threshold`` of all cases, plus the top variants until (1 -
    noise_threshold) cumulative coverage is reached."""
    total = sum(c for _, c in traces)
    ordered = sorted(traces, key=lambda kv: (-kv[1], kv[0]))
    kept: Sublog = {}
    cum = 0
    budget = (1.0 - noise_threshold) * total
    for trace, count in ordered:
        own_share = count / total if total else 1.0
        if kept and own_share < noise_threshold and cum + count > budget + 1e-9:
            break
        kept[trace] = kept.get(trace, 0) + count
        cum += count
    if not kept and ordered:
        kept[ordered[0][0]] = ordered[0][1]
    return kept, total - cum


@dataclass
class DiscoveryResult:
    tree: ProcessTree
    variants_total: int
    variants_filtered_out: int
    filtered_log: Sublog
    flower_fallback: bool
    notes: List[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        total = self.variants_total
        kept = sum(self.filtered_log.values())
        return kept / total if total else 0.0


def mine_process_tree(variants: Dict[Trace, int], noise_threshold: float = 0.05,
                      allow_flower: bool = True) -> DiscoveryResult:
    """Mine a block-structured process tree from a variant multiset.

    ``variants`` maps an activity tuple to the number of cases that follow it.
    """
    traces = [(t, c) for t, c in variants.items() if t]
    if not traces:
        raise DiscoveryError("event log has no traces")
    filtered, dropped = filter_variants(traces, noise_threshold)
    notes: List[str] = []
    tree = _mine_recursive(filtered, allow_flower, 0, notes)
    fallback = any("flower" in n for n in notes)
    return DiscoveryResult(
        tree=tree,
        variants_total=sum(c for _, c in traces),
        variants_filtered_out=dropped,
        filtered_log=filtered,
        flower_fallback=fallback,
        notes=notes,
    )
