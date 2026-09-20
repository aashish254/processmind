"""Core data contracts shared by every stage of the ProcessMind pipeline.

The central artifact is :class:`ProcessModel` - a tool-agnostic, JSON
serialisable process graph. Every extractor (LLM agent, offline rule parser,
DFG miner) produces a ``ProcessModel``; every exporter (BPMN XML, draw.io,
Mermaid, SVG) consumes one.
"""

from __future__ import annotations

import copy
import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Process model primitives
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    """BPMN-aligned node categories supported by the pipeline."""

    START_EVENT = "start_event"
    END_EVENT = "end_event"
    TASK = "task"
    XOR_GATEWAY = "xor_gateway"
    AND_GATEWAY = "and_gateway"
    INTERMEDIATE_EVENT = "intermediate_event"


class TaskKind(str, Enum):
    """BPMN task type mapping (userTask, serviceTask, ...)."""

    USER = "user"
    SERVICE = "service"
    MANUAL = "manual"
    SCRIPT = "script"
    BUSINESS_RULE = "business_rule"
    SEND = "send"
    RECEIVE = "receive"


NODE_PREFIX = {
    NodeType.START_EVENT: "start",
    NodeType.END_EVENT: "end",
    NodeType.XOR_GATEWAY: "xor",
    NodeType.AND_GATEWAY: "and",
    NodeType.INTERMEDIATE_EVENT: "event",
}

GATEWAY_TYPES = {NodeType.XOR_GATEWAY, NodeType.AND_GATEWAY}
EVENT_TYPES = {NodeType.START_EVENT, NodeType.END_EVENT, NodeType.INTERMEDIATE_EVENT}


def slugify(text: str, max_len: int = 28) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len].strip("_") or "node"


class Node(BaseModel):
    """A single flow object in the process graph."""

    id: str
    name: str
    type: NodeType
    kind: Optional[TaskKind] = None  # only meaningful for tasks
    actor: Optional[str] = None  # lane / responsible role
    description: str = ""
    source_text: str = ""  # provenance: the sentence the node was extracted from
    duration_minutes: float = 10.0
    automated: bool = False
    event_kind: Optional[str] = None  # "message" | "timer" for events

    def is_task(self) -> bool:
        return self.type == NodeType.TASK

    def is_gateway(self) -> bool:
        return self.type in GATEWAY_TYPES


class Flow(BaseModel):
    """A directed sequence flow between two nodes."""

    id: str
    source: str
    target: str
    label: Optional[str] = None


class ProcessModel(BaseModel):
    """Structured JSON process graph - the pipeline's central artifact."""

    id: str
    name: str
    description: str = ""
    nodes: List[Node] = Field(default_factory=list)
    flows: List[Flow] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # -- lookups ------------------------------------------------------------

    def node(self, node_id: str) -> Optional[Node]:
        return self._index().get(node_id)

    def _index(self) -> Dict[str, Node]:
        return {n.id: n for n in self.nodes}

    def successors(self, node_id: str) -> List[Flow]:
        return [f for f in self.flows if f.source == node_id]

    def predecessors(self, node_id: str) -> List[Flow]:
        return [f for f in self.flows if f.target == node_id]

    def out_nodes(self, node_id: str) -> List[str]:
        return [f.target for f in self.flows if f.source == node_id]

    def in_nodes(self, node_id: str) -> List[str]:
        return [f.source for f in self.flows if f.target == node_id]

    def to_adjacency(self) -> Dict[str, List[str]]:
        adj: Dict[str, List[str]] = {n.id: [] for n in self.nodes}
        for f in self.flows:
            adj.setdefault(f.source, []).append(f.target)
        return adj

    # -- typed accessors ----------------------------------------------------

    def tasks(self) -> List[Node]:
        return [n for n in self.nodes if n.type == NodeType.TASK]

    def gateways(self) -> List[Node]:
        return [n for n in self.nodes if n.type in GATEWAY_TYPES]

    def start_events(self) -> List[Node]:
        return [n for n in self.nodes if n.type == NodeType.START_EVENT]

    def end_events(self) -> List[Node]:
        return [n for n in self.nodes if n.type == NodeType.END_EVENT]

    def actors(self) -> List[str]:
        """Lanes in order of first appearance."""
        seen: List[str] = []
        for n in self.nodes:
            lane = n.actor or "Unassigned"
            if lane not in seen:
                seen.append(lane)
        return seen or ["Unassigned"]

    def find_task(self, name_fragment: str) -> Optional[Node]:
        """Fuzzy-find a task by name fragment (used for rework-loop targets)."""
        needle = name_fragment.lower().strip()
        best: Optional[Tuple[float, Node]] = None
        for t in self.tasks():
            hay = t.name.lower()
            score = 1.0 if needle in hay else _token_overlap(needle, hay)
            if score >= 0.34 and (best is None or score > best[0]):
                best = (score, t)
        return best[1] if best else None

    # -- mutation -----------------------------------------------------------

    def add_node(
        self,
        name: str,
        type: NodeType,
        kind: Optional[TaskKind] = None,
        **kwargs: Any,
    ) -> Node:
        node_id = self._next_id(name, type)
        node = Node(id=node_id, name=name, type=type, kind=kind, **kwargs)
        self.nodes.append(node)
        return node

    def _next_id(self, name: str, type: NodeType) -> str:
        base = NODE_PREFIX.get(type) or slugify(name) or "node"
        taken = {n.id for n in self.nodes} | {f.id for f in self.flows}
        if base not in taken:
            return base
        i = 2
        while f"{base}_{i}" in taken:
            i += 1
        return f"{base}_{i}"

    def add_flow(
        self,
        source: str,
        target: str,
        label: Optional[str] = None,
        flow_id: Optional[str] = None,
    ) -> Optional[Flow]:
        if source == target:  # self-loops are never meaningful in our models
            return None
        for f in self.flows:
            if f.source == source and f.target == target and (f.label or None) == (label or None):
                return f
        taken = {f.id for f in self.flows}
        if flow_id is None or flow_id in taken:
            i = len(self.flows) + 1
            while f"flow_{i}" in taken:
                i += 1
            flow_id = f"flow_{i}"
        flow = Flow(id=flow_id, source=source, target=target, label=label)
        self.flows.append(flow)
        return flow

    def remove_node(self, node_id: str, reconnect: bool = False) -> None:
        preds = [f.source for f in self.predecessors(node_id)]
        succs = [f.target for f in self.successors(node_id)]
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.flows = [f for f in self.flows if f.source != node_id and f.target != node_id]
        if reconnect:
            for p in preds:
                for s in succs:
                    if p != s:
                        self.add_flow(p, s)

    def clone(self) -> "ProcessModel":
        return self.model_copy(deep=True)

    # -- analytics ----------------------------------------------------------

    def _forward_back_edges(self) -> set:
        """Edges that close a cycle (found via iterative DFS)."""
        adj = self.to_adjacency()
        back: set = set()
        WHITE, GREY, BLACK = 0, 1, 2
        color = {n.id: WHITE for n in self.nodes}
        for n in self.nodes:
            if color[n.id] != WHITE:
                continue
            stack = [(n.id, iter(adj.get(n.id, [])))]
            color[n.id] = GREY
            while stack:
                cur, it = stack[-1]
                advanced = False
                for nxt in it:
                    if color.get(nxt, BLACK) == GREY:
                        back.add((cur, nxt))
                    elif color.get(nxt, BLACK) == WHITE:
                        color[nxt] = GREY
                        stack.append((nxt, iter(adj.get(nxt, []))))
                        advanced = True
                        break
                if not advanced:
                    color[cur] = BLACK
                    stack.pop()
        return back

    def critical_path_minutes(self) -> float:
        """Estimated cycle time = longest-duration path (cycles ignored)."""
        if not self.nodes:
            return 0.0
        back = self._forward_back_edges()
        adj: Dict[str, List[str]] = {n.id: [] for n in self.nodes}
        for f in self.flows:
            if (f.source, f.target) not in back:
                adj[f.source].append(f.target)
        # longest path via memoised DFS (graph is a DAG once back edges removed)
        memo: Dict[str, float] = {}

        def longest(nid: str, visiting: set) -> float:
            if nid in memo:
                return memo[nid]
            if nid in visiting:
                return 0.0
            visiting.add(nid)
            node = self.node(nid)
            base = node.duration_minutes if node and node.type in (NodeType.TASK, NodeType.INTERMEDIATE_EVENT) else 0.0
            best = 0.0
            for nxt in adj.get(nid, []):
                best = max(best, longest(nxt, visiting))
            visiting.discard(nid)
            memo[nid] = base + best
            return memo[nid]

        return max((longest(n.id, set()) for n in self.nodes), default=0.0)

    def automation_rate(self) -> float:
        tasks = self.tasks()
        if not tasks:
            return 0.0
        return sum(1 for t in tasks if t.automated) / len(tasks)

    def manual_task_count(self) -> int:
        return sum(1 for t in self.tasks() if not t.automated)

    def summary_metrics(self) -> "ModelMetrics":
        return ModelMetrics(
            task_count=len(self.tasks()),
            automated_count=sum(1 for t in self.tasks() if t.automated),
            manual_count=self.manual_task_count(),
            automation_rate=round(self.automation_rate(), 3),
            estimated_cycle_time_minutes=round(self.critical_path_minutes(), 1),
            gateway_count=len(self.gateways()),
            event_count=len([n for n in self.nodes if n.type in EVENT_TYPES]),
            lane_count=len(self.actors()),
            flow_count=len(self.flows),
        )


def _token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]+", a))
    tb = set(re.findall(r"[a-z0-9]+", b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------------------
# Ingestion contracts
# ---------------------------------------------------------------------------


class Section(BaseModel):
    title: str
    body: str = ""


class DocumentStats(BaseModel):
    words: int = 0
    sentences: int = 0
    steps: int = 0


class IngestedDocument(BaseModel):
    """Normalised output of the Ingestion Agent."""

    doc_id: str
    name: str
    kind: Literal["sop", "log", "text"] = "sop"
    text: str = ""
    sections: List[Section] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    stats: DocumentStats = Field(default_factory=DocumentStats)
    source_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Validation contracts
# ---------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    code: str
    severity: Literal["error", "warning"] = "error"
    message: str
    node_id: Optional[str] = None


class ValidationReport(BaseModel):
    ok: bool
    issues: List[ValidationIssue] = Field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# Optimisation contracts
# ---------------------------------------------------------------------------


class ModelMetrics(BaseModel):
    task_count: int = 0
    automated_count: int = 0
    manual_count: int = 0
    automation_rate: float = 0.0
    estimated_cycle_time_minutes: float = 0.0
    gateway_count: int = 0
    event_count: int = 0
    lane_count: int = 0
    flow_count: int = 0


class Finding(BaseModel):
    """An observed operational bottleneck / inefficiency (As-Is)."""

    id: str
    category: Literal[
        "manual_data_entry",
        "sequential_approval",
        "manual_handoff",
        "rework_loop",
        "queue_wait",
        "single_point_of_failure",
        "manual_decisioning",
        "general",
    ]
    severity: Literal["low", "medium", "high"] = "medium"
    title: str
    description: str
    evidence: List[str] = Field(default_factory=list)
    affected_nodes: List[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """A proposed To-Be transformation tied to findings."""

    id: str
    title: str
    category: Literal["automation", "parallelization", "integration", "validation", "elimination", "policy"]
    description: str
    affected_nodes: List[str] = Field(default_factory=list)
    resolves_findings: List[str] = Field(default_factory=list)
    expected_impact: str = ""
    estimated_minutes_saved: float = 0.0
    confidence: float = 0.7
    applied: bool = False


class ActivityStats(BaseModel):
    name: str
    frequency: int = 0
    cases: int = 0
    median_wait_minutes: float = 0.0
    mean_wait_minutes: float = 0.0
    total_wait_minutes: float = 0.0
    rework_count: int = 0
    rework_rate: float = 0.0
    service_minutes: Optional[float] = None
    bottleneck_score: float = 0.0


class Variant(BaseModel):
    sequence: List[str]
    count: int
    share: float


class LogSummary(BaseModel):
    """Analytics over a raw event log (input to the Optimization Agent)."""

    source: str = ""
    cases: int = 0
    events: int = 0
    activities_count: int = 0
    activities: List[ActivityStats] = Field(default_factory=list)
    variants: List[Variant] = Field(default_factory=list)
    top_bottlenecks: List[str] = Field(default_factory=list)
    start_activities: List[str] = Field(default_factory=list)
    end_activities: List[str] = Field(default_factory=list)


class BottleneckReport(BaseModel):
    findings: List[Finding] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)
    metrics_asis: ModelMetrics = Field(default_factory=ModelMetrics)
    metrics_tobe: ModelMetrics = Field(default_factory=ModelMetrics)
    log_summary: Optional[LogSummary] = None


class ActivityMatch(BaseModel):
    documented: str
    enacted: str
    similarity: float


class ConformanceIssue(BaseModel):
    kind: str  # documented_not_enacted | enacted_not_documented | sequence_mismatch | rework_mismatch
    severity: str = "medium"
    title: str
    description: str
    evidence: List[str] = Field(default_factory=list)


class ConformanceReport(BaseModel):
    """Documentation-drift analysis: documented (SOP) model vs enacted (log) behaviour."""

    matched_activities: List[ActivityMatch] = Field(default_factory=list)
    documented_only: List[str] = Field(default_factory=list)
    enacted_only: List[str] = Field(default_factory=list)
    sequence_documented_only: List[str] = Field(default_factory=list)
    sequence_enacted_only: List[str] = Field(default_factory=list)
    rework_drift: List[str] = Field(default_factory=list)
    df_precision: float = 1.0
    df_recall: float = 1.0
    fitness: Optional[float] = None  # trace-weighted footprint fitness
    issues: List[ConformanceIssue] = Field(default_factory=list)
    summary: str = ""


class PipelineResult(BaseModel):
    """Everything a full pipeline run produces."""

    name: str
    engine: str = "builtin"
    modeler_method: str = "offline-rules"
    document: Optional[IngestedDocument] = None
    model: Optional[ProcessModel] = None
    validation: Optional[ValidationReport] = None
    bottleneck_report: Optional[BottleneckReport] = None
    tobe_model: Optional[ProcessModel] = None
    conformance: Optional[ConformanceReport] = None
    artifacts: Dict[str, str] = Field(default_factory=dict)
    timings: Dict[str, float] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
