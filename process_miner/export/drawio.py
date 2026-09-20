"""draw.io (mxGraph) exporter for process models.

Emits a swimlane-pool diagram: pool -> lanes -> flow nodes, with orthogonal
edges. Files open directly in draw.io / diagrams.net and Lucidchart
(import draw.io XML).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, Optional

from process_miner.bpmn.layout import Layout, layout as default_layout
from process_miner.models import NodeType, ProcessModel, TaskKind

FILL_BY_KIND = {
    TaskKind.USER: "#dae8fc",
    TaskKind.SERVICE: "#d5e8d4",
    TaskKind.MANUAL: "#ffe6cc",
    TaskKind.SEND: "#e1d5e7",
    TaskKind.RECEIVE: "#e1d5e7",
    TaskKind.BUSINESS_RULE: "#fff2cc",
    TaskKind.SCRIPT: "#f5f5f5",
    None: "#dae8fc",
}


def process_to_drawio(model: ProcessModel, lay: Optional[Layout] = None, page_name: str = "Process") -> str:
    if lay is None:
        lay = default_layout(model)

    mxfile = ET.Element(
        "mxfile",
        {"host": "app.diagrams.net", "agent": "ProcessMind", "version": "21.6.0", "type": "device"},
    )
    diagram = ET.SubElement(mxfile, "diagram", {"id": _safe_id(model.id) + "_diagram", "name": page_name})
    graph = ET.SubElement(
        diagram,
        "mxGraphModel",
        {"dx": "1400", "dy": "900", "grid": "1", "gridSize": "10", "guides": "1", "tooltips": "1",
         "connect": "1", "arrows": "1", "fold": "1", "page": "1", "pageScale": "1",
         "pageWidth": "1600", "pageHeight": "1000", "math": "0", "shadow": "0"},
    )
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    if lay.pool_box:
        px, py, pw, ph = lay.pool_box
        pool = ET.SubElement(
            root,
            "mxCell",
            {
                "id": "pool_1",
                "value": _xml_escape(model.name),
                "style": "swimlane;html=1;horizontal=0;startSize=30;fillColor=#ffffff;strokeColor=#666666;fontSize=13;fontStyle=1;",
                "vertex": "1",
                "parent": "1",
            },
        )
        pool.append(_geometry(px, py, pw, ph))

        for lb in lay.lanes:
            lane = ET.SubElement(
                root,
                "mxCell",
                {
                    "id": f"lane_{lb.index}",
                    "value": _xml_escape(lb.name),
                    "style": "swimlane;html=1;horizontal=0;startSize=30;fillColor=#fafafa;strokeColor=#999999;fontSize=12;",
                    "vertex": "1",
                    "parent": "pool_1",
                },
            )
            lane.append(_geometry(lb.x - px, lb.y - py, lb.w, lb.h))

    lane_parent = {lb.name: f"lane_{lb.index}" for lb in lay.lanes}
    lane_box_by_name = {lb.name: lb for lb in lay.lanes}

    for n in model.nodes:
        sb = lay.shapes.get(n.id)
        if sb is None:
            continue
        parent = lane_parent.get(sb.lane, "1")
        style = _node_style(n)
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": _safe_id(n.id),
                "value": _xml_escape(n.name or ""),
                "style": style,
                "vertex": "1",
                "parent": parent,
            },
        )
        if sb.lane in lane_box_by_name:
            lb = lane_box_by_name[sb.lane]
            cell.append(_geometry(sb.x - lb.x, sb.y - lb.y, sb.w, sb.h))
        else:
            cell.append(_geometry(sb.x, sb.y, sb.w, sb.h))

    for f in model.flows:
        ET.SubElement(
            root,
            "mxCell",
            {
                "id": _safe_id(f.id),
                "value": _xml_escape(f.label or ""),
                "style": "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;orthogonalLoop=1;fontSize=11;",
                "edge": "1",
                "parent": "1",
                "source": _safe_id(f.source),
                "target": _safe_id(f.target),
            },
        )

    ET.indent(mxfile, space="  ")
    return ET.tostring(mxfile, encoding="unicode")


def _geometry(x: float, y: float, w: float, h: float) -> ET.Element:
    return ET.Element("mxGeometry", {"x": str(int(round(x))), "y": str(int(round(y))),
                                     "width": str(int(round(w))), "height": str(int(round(h))), "as": "geometry"})


def _node_style(n) -> str:
    if n.type == NodeType.TASK:
        fill = FILL_BY_KIND.get(n.kind, FILL_BY_KIND[None])
        return f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor=#333333;fontSize=11;"
    if n.type in (NodeType.XOR_GATEWAY, NodeType.AND_GATEWAY):
        return "rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=12;"
    if n.type == NodeType.START_EVENT:
        return "ellipse;whiteSpace=wrap;html=1;fillColor=#e8f5e9;strokeColor=#2e7d32;aspect=fixed;fontSize=10;"
    if n.type == NodeType.END_EVENT:
        return "ellipse;whiteSpace=wrap;html=1;fillColor=#fdecea;strokeColor=#b03a2e;strokeWidth=3;aspect=fixed;fontSize=10;"
    return "ellipse;whiteSpace=wrap;html=1;aspect=fixed;"


def _safe_id(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in s)[:60] or "x"


def _xml_escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
