"""BPMN 2.0 process model data structures for the inductive pathway.

Ported from the bpmn-miner capstone (cap 5). This is a lightweight,
dependency-free model used for (a) converting process trees into BPMN
block structure and (b) token-based conformance replay. Converters in
:mod:`process_miner.inductive.convert` bridge to/from the pipeline's
pydantic :class:`process_miner.models.ProcessModel` so discovered models
flow through the same export pipeline (BPMN XML, draw.io, SVG, reports).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

NODE_TYPES = {"startEvent", "endEvent", "task", "exclusiveGateway", "parallelGateway",
              "serviceTask", "userTask", "manualTask", "intermediateCatchEvent"}


@dataclass
class BpmnNode:
    id: str
    type: str
    name: str = ""
    lane: Optional[str] = None
    meta: Dict = field(default_factory=dict)

    @property
    def is_gateway(self) -> bool:
        return self.type.endswith("Gateway")

    @property
    def is_event(self) -> bool:
        return self.type.endswith("Event")

    def to_json(self) -> dict:
        out = {"id": self.id, "type": self.type, "name": self.name}
        if self.lane:
            out["lane"] = self.lane
        if self.meta:
            out["meta"] = self.meta
        return out


@dataclass
class BpmnFlow:
    id: str
    source: str
    target: str
    label: Optional[str] = None
    freq: Optional[int] = None

    def to_json(self) -> dict:
        out = {"id": self.id, "sourceRef": self.source, "targetRef": self.target}
        if self.label:
            out["label"] = self.label
        if self.freq is not None:
            out["frequency"] = self.freq
        return out


@dataclass
class BpmnModel:
    name: str
    nodes: List[BpmnNode] = field(default_factory=list)
    flows: List[BpmnFlow] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)
    _by_id: Dict[str, BpmnNode] = field(default_factory=dict, repr=False)

    # -- mutation -----------------------------------------------------------
    def add_node(self, node: BpmnNode) -> BpmnNode:
        if node.id in self._by_id:
            raise ValueError(f"duplicate node id: {node.id}")
        self._by_id[node.id] = node
        self.nodes.append(node)
        return node

    def add_flow(self, flow: BpmnFlow) -> BpmnFlow:
        self.flows.append(flow)
        return flow

    # -- accessors ------------------------------------------------------------
    def node(self, node_id: str) -> Optional[BpmnNode]:
        return self._by_id.get(node_id)

    def successors(self, node_id: str) -> List[BpmnNode]:
        return [self.node(f.target) for f in self.flows if f.source == node_id and self.node(f.target)]

    def predecessors(self, node_id: str) -> List[BpmnNode]:
        return [self.node(f.source) for f in self.flows if f.target == node_id and self.node(f.source)]

    def nodes_of_type(self, *types: str) -> List[BpmnNode]:
        return [n for n in self.nodes if n.type in types]

    @property
    def tasks(self) -> List[BpmnNode]:
        return self.nodes_of_type("task", "serviceTask", "userTask", "manualTask")

    @property
    def start_events(self) -> List[BpmnNode]:
        return self.nodes_of_type("startEvent")

    @property
    def end_events(self) -> List[BpmnNode]:
        return self.nodes_of_type("endEvent")

    def activity_node(self, activity: str) -> Optional[BpmnNode]:
        for n in self.tasks:
            if n.name == activity:
                return n
        return None

    # -- serialization ----------------------------------------------------------
    def to_json(self) -> dict:
        return {
            "name": self.name,
            "meta": self.meta,
            "nodes": [n.to_json() for n in self.nodes],
            "flows": [f.to_json() for f in self.flows],
        }

    @classmethod
    def from_json(cls, data: dict) -> "BpmnModel":
        model = cls(name=data.get("name", "Process"), meta=dict(data.get("meta", {})))
        for nd in data.get("nodes", []):
            model.add_node(BpmnNode(id=nd["id"], type=nd["type"], name=nd.get("name", ""),
                                    lane=nd.get("lane"), meta=dict(nd.get("meta", {}))))
        for fl in data.get("flows", []):
            model.add_flow(BpmnFlow(id=fl["id"], source=fl["sourceRef"], target=fl["targetRef"],
                                    label=fl.get("label"), freq=fl.get("frequency")))
        return model

    def summary(self) -> str:
        counts: Dict[str, int] = {}
        for n in self.nodes:
            counts[n.type] = counts.get(n.type, 0) + 1
        parts = [f"{v} {k}" for k, v in sorted(counts.items())]
        return f"{self.name}: {', '.join(parts)}; {len(self.flows)} flows"


# ---------------------------------------------------------------------------
# process tree -> BPMN conversion
# ---------------------------------------------------------------------------

AUTOMATED_ROLE_HINTS = {"system", "portal", "erp", "it", "bot", "api", "auto", "workflow"}


class BpmnBuilder:
    """Converts a ProcessTree into a BpmnModel with systematic gateway patterns."""

    def __init__(self, name: str, condition_labels: Optional[Dict[str, str]] = None,
                 roles: Optional[Dict[str, str]] = None, dfg=None):
        self.model = BpmnModel(name=name)
        self.condition_labels = condition_labels or {}
        self.roles = roles or {}
        self.dfg = dfg
        self._counters: Dict[str, int] = {}

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}_{self._counters[prefix]}"

    def build(self, tree) -> BpmnModel:
        entry, exit_ = self._convert(tree)
        start = self.model.add_node(BpmnNode(id=self._next_id("StartEvent"), type="startEvent",
                                             name="Start", meta={"synthetic": True}))
        end = self.model.add_node(BpmnNode(id=self._next_id("EndEvent"), type="endEvent",
                                           name="End", meta={"synthetic": True}))
        self._wire(start.id, entry)
        self._wire(exit_, end.id)
        self._annotate_frequencies()
        return self.model

    def _task_type(self, name: str) -> str:
        role = (self.roles.get(name) or "").lower()
        if any(h in role for h in AUTOMATED_ROLE_HINTS):
            return "serviceTask"
        return "task"

    def _convert(self, tree):
        """Return (entry_id|None, exit_id|None)."""
        op = tree.op
        if op == "tau":
            return None, None
        if op == "leaf":
            node = self.model.add_node(BpmnNode(
                id=self._next_id("Task"), type=self._task_type(tree.label or ""),
                name=tree.label or "Activity",
                lane=self.roles.get(tree.label or "")))
            return node.id, node.id
        if op == "seq":
            current = None
            first_entry = None
            for child in tree.children:
                ce, cx = self._convert(child)
                if ce is None and cx is None:
                    continue
                if current is None:
                    first_entry = ce
                else:
                    self._wire(current, ce)
                current = cx
            return first_entry, current
        if op in {"xor", "par"}:
            gtype = "exclusiveGateway" if op == "xor" else "parallelGateway"
            split = self.model.add_node(BpmnNode(id=self._next_id("Gateway"), type=gtype,
                                                 name="", meta={"direction": "diverging"}))
            join = self.model.add_node(BpmnNode(id=self._next_id("Gateway"), type=gtype,
                                                name="", meta={"direction": "converging"}))
            for child in tree.children:
                ce, cx = self._convert(child)
                if ce is None and cx is None:
                    # tau branch: a skip path through the gateways
                    self.model.add_flow(BpmnFlow(id=self._next_id("Flow"), source=split.id,
                                                 target=join.id, label="else"))
                    continue
                self._wire(split.id, ce, label_for=ce)
                self._wire(cx, join.id)
            return split.id, join.id
        if op == "loop":
            g_in = self.model.add_node(BpmnNode(id=self._next_id("Gateway"), type="exclusiveGateway",
                                                name="", meta={"direction": "diverging", "loop": True}))
            g_out = self.model.add_node(BpmnNode(id=self._next_id("Gateway"), type="exclusiveGateway",
                                                 name="", meta={"direction": "converging", "loop": True}))
            body_entry, body_exit = self._convert(tree.children[0]) if tree.children else (None, None)
            redo_entry, redo_exit = self._convert(tree.children[1]) if len(tree.children) > 1 else (None, None)
            # entry -> g_in -> body -> g_out; g_out -> redo -> g_in (repeat); exit from g_out
            if body_entry is None and body_exit is None:
                self._wire(g_in.id, g_out.id)
            else:
                self._wire(g_in.id, body_entry)
                self._wire(body_exit, g_out.id)
            if redo_entry is not None and redo_exit is not None:
                self.model.add_flow(BpmnFlow(id=self._next_id("Flow"), source=g_out.id,
                                             target=redo_entry, label="repeat"))
                self._wire(redo_exit, g_in.id)
            return g_in.id, g_out.id
        raise ValueError(f"unknown process-tree op: {op}")

    def _wire(self, source_id, target_id, label_for=None):
        """Connect source to target; None means pass-through (skip)."""
        if source_id is None and target_id is None:
            return
        if source_id is None or target_id is None:
            raise ValueError("cannot wire a pass-through boundary at top level")
        label = None
        if label_for is not None:
            node = self.model.node(label_for)
            if node is not None and node.name in self.condition_labels:
                label = self.condition_labels[node.name]
        self.model.add_flow(BpmnFlow(id=self._next_id("Flow"), source=source_id,
                                     target=target_id, label=label))

    def _annotate_frequencies(self) -> None:
        if self.dfg is None:
            return
        for flow in self.model.flows:
            src, dst = self.model.node(flow.source), self.model.node(flow.target)
            if src is None or dst is None:
                continue
            if src.type in {"task", "serviceTask", "userTask", "manualTask"} and \
               dst.type in {"task", "serviceTask", "userTask", "manualTask"}:
                freq = self.dfg.frequency(src.name, dst.name)
                if freq:
                    flow.freq = freq


def tree_to_bpmn(tree, name: str = "Discovered Process",
                 condition_labels: Optional[Dict[str, str]] = None,
                 roles: Optional[Dict[str, str]] = None, dfg=None) -> BpmnModel:
    builder = BpmnBuilder(name=name, condition_labels=condition_labels, roles=roles, dfg=dfg)
    return builder.build(tree)
