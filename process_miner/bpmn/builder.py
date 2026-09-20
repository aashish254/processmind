"""BPMN 2.0 XML builder.

Emits standards-compliant BPMN 2.0 (MODEL + DI namespaces) that opens
directly in Camunda Modeler, bpmn.io, Signavio, draw.io and Bizagi:

* ``bpmn:definitions`` -> ``bpmn:collaboration`` (pool) -> ``bpmn:process``
  with ``bpmn:laneSet`` and typed flow elements,
* task kind mapping (userTask / serviceTask / manualTask / sendTask / ...),
* XOR gateways with ``bpmn:conditionExpression`` on labeled outgoing flows,
* full ``bpmndi`` diagram interchange: shapes with ``dc:Bounds``, orthogonal
  edge waypoints, horizontal lane/participant shapes,
* provenance kept as ``bpmn:documentation`` children.
"""

from __future__ import annotations

from typing import Dict, Optional
import xml.etree.ElementTree as ET

from process_miner.bpmn.layout import Layout, layout as default_layout
from process_miner.models import NodeType, ProcessModel, TaskKind

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

for prefix, uri in [
    ("bpmn", BPMN_NS),
    ("bpmndi", BPMNDI_NS),
    ("dc", DC_NS),
    ("di", DI_NS),
    ("xsi", XSI_NS),
]:
    ET.register_namespace(prefix, uri)

TASK_ELEMENT: Dict[Optional[TaskKind], str] = {
    None: "task",
    TaskKind.USER: "userTask",
    TaskKind.SERVICE: "serviceTask",
    TaskKind.MANUAL: "manualTask",
    TaskKind.SCRIPT: "scriptTask",
    TaskKind.BUSINESS_RULE: "businessRuleTask",
    TaskKind.SEND: "sendTask",
    TaskKind.RECEIVE: "receiveTask",
}


def q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def to_bpmn_xml(model: ProcessModel, lay: Optional[Layout] = None) -> str:
    if lay is None:
        lay = default_layout(model)

    definitions = ET.Element(
        q(BPMN_NS, "definitions"),
        {
            "id": f"Definitions_{_safe(model.id)}",
            "targetNamespace": "http://processmind.local/bpmn",
            "exporter": "ProcessMind 1.0",
            "exporterVersion": "1.0.0",
        },
    )

    use_pool = bool(lay.lanes) and lay.pool
    collab = None
    process_id = f"Process_{_safe(model.id)}"
    if use_pool:
        collab = ET.SubElement(definitions, q(BPMN_NS, "collaboration"), {"id": f"Collaboration_{_safe(model.id)}"})
        ET.SubElement(
            collab,
            q(BPMN_NS, "participant"),
            {"id": f"Participant_{_safe(model.id)}", "name": model.name, "processRef": process_id},
        )

    process = ET.SubElement(
        definitions,
        q(BPMN_NS, "process"),
        {"id": process_id, "name": model.name, "isExecutable": "false"},
    )
    if model.description:
        ET.SubElement(process, q(BPMN_NS, "documentation")).text = model.description

    # lanes
    if lay.lanes:
        lane_set = ET.SubElement(process, q(BPMN_NS, "laneSet"), {"id": f"LaneSet_{_safe(model.id)}"})
        for lb in lay.lanes:
            lane = ET.SubElement(
                lane_set,
                q(BPMN_NS, "lane"),
                {
                    "id": f"Lane_{_safe(lb.name)}_{lb.index}",
                    "name": lb.name,
                },
            )
            for nid, sb in lay.shapes.items():
                if sb.lane == lb.name:
                    ET.SubElement(lane, q(BPMN_NS, "flowNodeRef")).text = nid

    # flow nodes
    incoming: Dict[str, list] = {}
    outgoing: Dict[str, list] = {}
    for f in model.flows:
        outgoing.setdefault(f.source, []).append(f.id)
        incoming.setdefault(f.target, []).append(f.id)

    for n in model.nodes:
        if n.type == NodeType.TASK:
            tag = TASK_ELEMENT.get(n.kind, "task")
            el = ET.SubElement(process, q(BPMN_NS, tag), {"id": n.id, "name": n.name})
        elif n.type == NodeType.START_EVENT:
            el = ET.SubElement(process, q(BPMN_NS, "startEvent"), {"id": n.id, "name": n.name})
            if n.event_kind == "message":
                ET.SubElement(el, q(BPMN_NS, "messageEventDefinition"), {"id": f"{n.id}_msg"})
            elif n.event_kind == "timer":
                ET.SubElement(el, q(BPMN_NS, "timerEventDefinition"), {"id": f"{n.id}_timer"})
        elif n.type == NodeType.END_EVENT:
            el = ET.SubElement(process, q(BPMN_NS, "endEvent"), {"id": n.id, "name": n.name})
        elif n.type == NodeType.INTERMEDIATE_EVENT:
            el = ET.SubElement(process, q(BPMN_NS, "intermediateCatchEvent"), {"id": n.id, "name": n.name})
            if n.event_kind == "message":
                ET.SubElement(el, q(BPMN_NS, "messageEventDefinition"), {"id": f"{n.id}_msg"})
            elif n.event_kind == "timer":
                ET.SubElement(el, q(BPMN_NS, "timerEventDefinition"), {"id": f"{n.id}_timer"})
        elif n.type == NodeType.XOR_GATEWAY:
            el = ET.SubElement(
                process, q(BPMN_NS, "exclusiveGateway"),
                {"id": n.id, "name": n.name, "gatewayDirection": _gateway_direction(model, n.id)},
            )
        elif n.type == NodeType.AND_GATEWAY:
            el = ET.SubElement(
                process, q(BPMN_NS, "parallelGateway"),
                {"id": n.id, "name": n.name, "gatewayDirection": _gateway_direction(model, n.id)},
            )
        else:  # pragma: no cover - exhaustive enum
            continue

        doc_text = _documentation_text(n)
        if doc_text:
            ET.SubElement(el, q(BPMN_NS, "documentation")).text = doc_text
        for fid in incoming.get(n.id, []):
            ET.SubElement(el, q(BPMN_NS, "incoming")).text = fid
        for fid in outgoing.get(n.id, []):
            ET.SubElement(el, q(BPMN_NS, "outgoing")).text = fid

    # sequence flows
    xor_split_ids = {
        g.id for g in model.gateways()
        if g.type == NodeType.XOR_GATEWAY and len(model.successors(g.id)) > 1
    }
    for f in model.flows:
        attrs = {"id": f.id, "sourceRef": f.source, "targetRef": f.target}
        if f.label:
            attrs["name"] = f.label
        ET.SubElement(process, q(BPMN_NS, "sequenceFlow"), attrs)

    # attach conditionExpressions to labeled XOR-split flows
    for f in model.flows:
        if f.label and f.source in xor_split_ids:
            flow_el = next(e for e in process if e.tag == q(BPMN_NS, "sequenceFlow") and e.get("id") == f.id)
            cond = ET.SubElement(flow_el, q(BPMN_NS, "conditionExpression"))
            cond.set(q(XSI_NS, "type"), "bpmn:tFormalExpression")
            cond.text = f.label

    # ---------------- diagram interchange ----------------
    diagram = ET.SubElement(definitions, q(BPMNDI_NS, "BPMNDiagram"), {"id": f"BPMNDiagram_{_safe(model.id)}"})
    plane_el = q(BPMNDI_NS, "BPMNPlane")
    plane_attrs = {"id": f"BPMNPlane_{_safe(model.id)}"}
    plane_attrs["bpmnElement"] = (
        f"Collaboration_{_safe(model.id)}" if collab is not None else process_id
    )
    plane = ET.SubElement(diagram, plane_el, plane_attrs)

    if use_pool and lay.pool_box:
        ET.SubElement(
            plane,
            q(BPMNDI_NS, "BPMNShape"),
            {
                "id": f"shp_Participant_{_safe(model.id)}",
                "bpmnElement": f"Participant_{_safe(model.id)}",
                "isHorizontal": "true",
            },
        ).append(_bounds(lay.pool_box))

    for lb in lay.lanes:
        lane_el_id = f"Lane_{_safe(lb.name)}_{lb.index}"
        shape = ET.SubElement(
            plane,
            q(BPMNDI_NS, "BPMNShape"),
            {"id": f"shp_{lane_el_id}", "bpmnElement": lane_el_id, "isHorizontal": "true"},
        )
        shape.append(_bounds((lb.x, lb.y, lb.w, lb.h)))

    for n in model.nodes:
        sb = lay.shapes.get(n.id)
        if sb is None:
            continue
        shape = ET.SubElement(
            plane,
            q(BPMNDI_NS, "BPMNShape"),
            {"id": f"shp_{n.id}", "bpmnElement": n.id},
        )
        shape.append(_bounds((sb.x, sb.y, sb.w, sb.h)))

    for f in model.flows:
        points = lay.edges.get(f.id)
        if not points:
            continue
        edge = ET.SubElement(
            plane,
            q(BPMNDI_NS, "BPMNEdge"),
            {"id": f"edg_{f.id}", "bpmnElement": f.id},
        )
        for (x, y) in points:
            ET.SubElement(edge, q(DI_NS, "waypoint"), {"x": _fmt(x), "y": _fmt(y)})

    ET.indent(definitions, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(definitions, encoding="unicode")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _safe(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s)[:60].strip("_") or "x"


def _fmt(v: float) -> str:
    return str(int(round(v)))


def _bounds(box) -> ET.Element:
    x, y, w, h = box
    return ET.Element(q(DC_NS, "Bounds"), {"x": _fmt(x), "y": _fmt(y), "width": _fmt(w), "height": _fmt(h)})


def _gateway_direction(model: ProcessModel, node_id: str) -> str:
    n_in = len(model.predecessors(node_id))
    n_out = len(model.successors(node_id))
    if n_out > 1 and n_in <= 1:
        return "Diverging"
    if n_in > 1 and n_out <= 1:
        return "Converging"
    if n_in > 1 and n_out > 1:
        return "Mixed"
    return "Unspecified"


def _documentation_text(node) -> str:
    parts = []
    if node.description:
        parts.append(node.description)
    if node.source_text and node.source_text != node.description:
        parts.append(f'Source: "{node.source_text}"')
    return "\n".join(parts)
