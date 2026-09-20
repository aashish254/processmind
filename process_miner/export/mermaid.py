"""Mermaid flowchart exporter (lanes -> subgraphs)."""

from __future__ import annotations

import re
from typing import Dict

from process_miner.models import NodeType, ProcessModel


def to_mermaid(model: ProcessModel) -> str:
    lines = ["flowchart TD"]
    lane_subgraphs: Dict[str, list] = {}
    free_nodes = []

    for n in model.nodes:
        lane = n.actor or "Unassigned"
        if n.actor:
            lane_subgraphs.setdefault(lane, []).append(n)
        else:
            free_nodes.append(n)

    def shape(n) -> str:
        label = _esc(n.name) or n.id
        if n.type == NodeType.START_EVENT:
            return f"{_mid(n.id)}((\"{label}\"))"
        if n.type == NodeType.END_EVENT:
            return f"{_mid(n.id)}((\"{label}\"))"
        if n.type == NodeType.XOR_GATEWAY:
            return f"{_mid(n.id)}{{\"{_esc(n.name) or 'X'}\"}}"
        if n.type == NodeType.AND_GATEWAY:
            return f"{_mid(n.id)}{{\"+\"}}"
        kind_mark = ""
        if n.kind and n.kind.value in {"service", "script"}:
            kind_mark = "[/"
            return f"{_mid(n.id)}[\"{label}\"]"  # keep simple rect; kind shown via tooltip below
        return f"{_mid(n.id)}[\"{label}\"]"

    for i, (lane, nodes) in enumerate(lane_subgraphs.items()):
        lines.append(f"  subgraph L{i}[\"{_esc(lane)}\"]")
        for n in nodes:
            lines.append(f"    {shape(n)}")
        lines.append("  end")
    for n in free_nodes:
        lines.append(f"  {shape(n)}")

    for f in model.flows:
        label = f"|\"{_esc(f.label)}\"|" if f.label else ""
        lines.append(f"  {_mid(f.source)} -->{label} {_mid(f.target)}")

    return "\n".join(lines) + "\n"


def _mid(node_id: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", node_id)


def _esc(text: str) -> str:
    return text.replace('"', "'")
