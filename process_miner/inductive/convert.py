"""Bridges between the inductive pathway's lightweight BpmnModel and the
pipeline's pydantic :class:`process_miner.models.ProcessModel`.

Two directions, two purposes:

* ``bpmn_model_to_process_model`` - discovered block-structured models
  (Inductive Miner) flow through the *same* export pipeline as the agent
  output: BPMN XML with diagram interchange, draw.io, Mermaid, SVG, HTML
  reports, validation and optimization agents all consume a ProcessModel.
* ``process_model_to_bpmn_model`` - any pipeline model (e.g. the DFG
  discovery output) can be replayed with the token-based conformance
  checker, putting every extractor on one soundness measure.
"""

from __future__ import annotations

from typing import Dict, Optional

from process_miner.models import NodeType, ProcessModel, TaskKind

from .tree_bpmn import BpmnFlow, BpmnModel, BpmnNode

_TYPE_TO_NODE = {
    "startEvent": NodeType.START_EVENT,
    "endEvent": NodeType.END_EVENT,
    "task": NodeType.TASK,
    "serviceTask": NodeType.TASK,
    "userTask": NodeType.TASK,
    "manualTask": NodeType.TASK,
    "exclusiveGateway": NodeType.XOR_GATEWAY,
    "parallelGateway": NodeType.AND_GATEWAY,
    "intermediateCatchEvent": NodeType.INTERMEDIATE_EVENT,
}

_NODE_TO_TYPE = {
    NodeType.START_EVENT: "startEvent",
    NodeType.END_EVENT: "endEvent",
    NodeType.TASK: "task",
    NodeType.XOR_GATEWAY: "exclusiveGateway",
    NodeType.AND_GATEWAY: "parallelGateway",
    NodeType.INTERMEDIATE_EVENT: "intermediateCatchEvent",
}


def bpmn_model_to_process_model(
    bpmn: BpmnModel,
    model_id: str = "pm_inductive",
    extractor: str = "inductive-miner",
) -> ProcessModel:
    """Convert a lightweight BpmnModel into the pipeline's ProcessModel."""
    model = ProcessModel(
        id=model_id,
        name=bpmn.name,
        description=f"Block-structured model discovered by the {extractor}",
        metadata={"extractor": extractor, **bpmn.meta},
    )
    id_map: Dict[str, str] = {}
    for n in bpmn.nodes:
        node_type = _TYPE_TO_NODE.get(n.type)
        if node_type is None:
            continue
        kwargs = {}
        if node_type == NodeType.TASK:
            kwargs["kind"] = TaskKind.SERVICE if n.type == "serviceTask" else TaskKind.USER
            kwargs["automated"] = n.type == "serviceTask"
        if n.lane:
            kwargs["actor"] = n.lane
        node = model.add_node(n.name or _fallback_name(node_type, n.id), node_type, **kwargs)
        id_map[n.id] = node.id
    for f in bpmn.flows:
        src, tgt = id_map.get(f.source), id_map.get(f.target)
        if src and tgt:
            model.add_flow(src, tgt, f.label)
    return model


def process_model_to_bpmn_model(model: ProcessModel) -> BpmnModel:
    """Convert any pipeline ProcessModel into the replayable BpmnModel."""
    bpmn = BpmnModel(name=model.name, meta={"source": model.metadata.get("extractor", "pipeline")})
    id_map: Dict[str, str] = {}
    for n in model.nodes:
        node_type = _NODE_TO_TYPE.get(n.type)
        if node_type is None:
            continue
        bpmn.add_node(BpmnNode(id=n.id, type=node_type, name=n.name, lane=n.actor))
        id_map[n.id] = n.id
    for f in model.flows:
        src, tgt = id_map.get(f.source), id_map.get(f.target)
        if src and tgt:
            bpmn.add_flow(BpmnFlow(id=f.id, source=src, target=tgt, label=f.label))
    # The replay engine needs gateway direction; the pipeline model does not
    # carry it, so infer from topology: many successors = split (diverging),
    # many predecessors = join (converging).
    in_deg: Dict[str, int] = {}
    out_deg: Dict[str, int] = {}
    for f in bpmn.flows:
        out_deg[f.source] = out_deg.get(f.source, 0) + 1
        in_deg[f.target] = in_deg.get(f.target, 0) + 1
    for n in bpmn.nodes:
        if n.type in ("exclusiveGateway", "parallelGateway"):
            direction = "converging" if in_deg.get(n.id, 0) > 1 and out_deg.get(n.id, 0) <= 1 else "diverging"
            n.meta = dict(n.meta, direction=direction)
    return bpmn


def _fallback_name(node_type: NodeType, node_id: str) -> str:
    if node_type == NodeType.START_EVENT:
        return "Case started"
    if node_type == NodeType.END_EVENT:
        return "Case closed"
    if node_type in (NodeType.XOR_GATEWAY, NodeType.AND_GATEWAY):
        return ""  # gateways are unnamed, matching the DFG miner's style
    return node_id
