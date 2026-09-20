"""Trace replay against a BPMN model (token-based conformance fitness).

Ported from the bpmn-miner capstone (cap 5). The replay performs a bounded
search over markings (multisets of node tokens). XOR gateways branch the
search, AND gateways spawn/converge tokens, tasks consume trace events.
This gives a token-based fitness metric without external dependencies.
State explosion is bounded by ``state_cap`` - when exceeded the variant is
reported as "unknown" and excluded from fitness.

Research role (docs/RESEARCH.md): replay fitness is the *soundness measure*
of the merged study - it scores every discovered model (E4 DFG and E6
Inductive Miner alike) against the same variant multiset, on equal footing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .tree_bpmn import BpmnModel

TASK_TYPES = {"task", "serviceTask", "userTask", "manualTask"}
Marking = Tuple[str, ...]  # sorted multiset of node ids holding tokens


@dataclass
class ReplayResult:
    accepted_variants: int = 0
    rejected_variants: int = 0
    unknown_variants: int = 0
    cases_accepted: int = 0
    cases_total: int = 0
    traces_checked: int = 0
    details: List[dict] = field(default_factory=list)

    @property
    def fitness(self) -> float:
        if self.cases_total == 0:
            return 0.0
        return self.cases_accepted / self.cases_total

    def to_json(self) -> dict:
        return {
            "fitness": round(self.fitness, 4),
            "cases_accepted": self.cases_accepted,
            "cases_total": self.cases_total,
            "variants": {"accepted": self.accepted_variants, "rejected": self.rejected_variants,
                         "unknown": self.unknown_variants},
        }


class _Replayer:
    def __init__(self, model: BpmnModel, state_cap: int = 50_000):
        self.model = model
        self.state_cap = state_cap
        self.flows_by_source: Dict[str, List[str]] = {}
        self.flows_by_target: Dict[str, List[str]] = {}
        for f in model.flows:
            self.flows_by_source.setdefault(f.source, []).append(f.target)
            self.flows_by_target.setdefault(f.target, []).append(f.source)
        self.in_degree = {n.id: len(self.flows_by_target.get(n.id, [])) for n in model.nodes}
        self.end_ids = {e.id for e in model.end_events}

    # -- silent (non-observable) closure -------------------------------------
    def _closure(self, marking: Marking) -> Tuple[Set[Marking], Dict[str, Set[Marking]]]:
        """Return (all silent-reachable markings, task_name -> markings after firing)."""
        seen: Set[Marking] = {marking}
        stack = [marking]
        enabled: Dict[str, Set[Marking]] = {}
        while stack:
            current = stack.pop()
            counts: Dict[str, int] = {}
            for nid in current:
                counts[nid] = counts.get(nid, 0) + 1
            for nid, cnt in counts.items():
                node = self.model.node(nid)
                if node is None:
                    continue
                succ = self.flows_by_source.get(nid, [])
                if node.type in TASK_TYPES:
                    if not succ:
                        continue
                    rest = list(current)
                    rest.remove(nid)
                    enabled.setdefault(node.name, set()).add(_bump(tuple(rest), succ[0]))
                elif node.type == "endEvent":
                    if all(nid in self.end_ids for nid in current):
                        enabled.setdefault("__END__", set()).add(current)
                elif node.type == "startEvent":
                    rest = list(current)
                    rest.remove(nid)
                    for s in succ:
                        stack.append(_bump(tuple(rest), s))
                elif node.type == "exclusiveGateway":
                    rest = list(current)
                    rest.remove(nid)
                    for s in succ:
                        stack.append(_bump(tuple(rest), s))
                elif node.type == "parallelGateway":
                    direction = node.meta.get("direction", "diverging")
                    if direction == "converging" and len(succ) <= 1:
                        needs = self.in_degree.get(nid, 1)
                        if cnt >= needs:
                            rest = list(current)
                            for _ in range(needs):
                                rest.remove(nid)
                            for s in succ:
                                rest.append(s)
                            stack.append(_sort(tuple(rest)))
                        # else: token waits for the remaining branches
                    else:
                        rest = list(current)
                        rest.remove(nid)
                        for s in succ:
                            rest.append(s)
                        stack.append(_sort(tuple(rest)))
        return seen, enabled

    def replay(self, trace: Tuple[str, ...]) -> str:
        """Return 'accepted' | 'rejected' | 'unknown'."""
        starts = tuple(sorted(s.id for s in self.model.start_events))
        if not starts:
            return "rejected"
        states: Set[Tuple[Marking, int]] = {(starts, 0)}
        visited: Set[Tuple[Marking, int]] = set()
        steps = 0
        while states:
            if steps > self.state_cap or len(visited) > self.state_cap:
                return "unknown"
            next_states: Set[Tuple[Marking, int]] = set()
            for marking, idx in states:
                if (marking, idx) in visited:
                    continue
                visited.add((marking, idx))
                steps += 1
                seen, enabled = self._closure(marking)
                if idx >= len(trace):
                    if enabled.get("__END__"):
                        return "accepted"
                    continue
                wanted = trace[idx]
                for after in enabled.get(wanted, ()):
                    next_states.add((after, idx + 1))
            states = next_states
        return "rejected"


def _bump(marking: Marking, node: str) -> Marking:
    return _sort(tuple(list(marking) + [node]))


def _sort(marking: Marking) -> Marking:
    return tuple(sorted(marking))


def replay_fitness(model: BpmnModel, variants: Dict[Tuple[str, ...], int],
                   state_cap: int = 50_000) -> ReplayResult:
    replayer = _Replayer(model, state_cap)
    result = ReplayResult()
    for trace, count in sorted(variants.items(), key=lambda kv: (-kv[1], kv[0])):
        outcome = replayer.replay(trace)
        result.traces_checked += 1
        result.cases_total += count
        if outcome == "accepted":
            result.accepted_variants += 1
            result.cases_accepted += count
        elif outcome == "rejected":
            result.rejected_variants += 1
        else:
            result.unknown_variants += 1
        result.details.append({"trace": list(trace), "cases": count, "outcome": outcome})
    return result
