"""Standalone SVG renderer for process models (no external dependencies).

Reuses the BPMN layout engine so the SVG matches the BPMN DI geometry.
Opens directly in any browser and is embedded in the HTML report.
"""

from __future__ import annotations

import html
from typing import List, Optional, Tuple

from process_miner.bpmn.layout import Layout, layout as default_layout
from process_miner.models import NodeType, ProcessModel, TaskKind

STYLE_BY_KIND = {
    TaskKind.USER: ("#dae8fc", "#6c8ebf"),
    TaskKind.SERVICE: ("#d5e8d4", "#82b366"),
    TaskKind.MANUAL: ("#ffe6cc", "#d79b00"),
    TaskKind.SEND: ("#e1d5e7", "#9673a6"),
    TaskKind.RECEIVE: ("#e1d5e7", "#9673a6"),
    TaskKind.BUSINESS_RULE: ("#fff2cc", "#d6b656"),
    TaskKind.SCRIPT: ("#f5f5f5", "#666666"),
    None: ("#dae8fc", "#6c8ebf"),
}


def to_svg(model: ProcessModel, lay: Optional[Layout] = None) -> str:
    if lay is None:
        lay = default_layout(model)
    w = int(lay.width + 40)
    h = int(lay.height + 40)
    out: List[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="Helvetica, Arial, sans-serif">'
    )
    out.append(_DEFS)
    out.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>')

    # pool
    if lay.pool_box:
        px, py, pw, ph = lay.pool_box
        out.append(
            f'<rect x="{_n(px)}" y="{_n(py)}" width="{_n(pw)}" height="{_n(ph)}" '
            f'fill="#ffffff" stroke="#666666" stroke-width="1.5"/>'
        )
        out.append(_vlabel(model.name, 15, py + ph / 2, "#333333", 13, "bold"))
        out.append(f'<line x1="{_n(px + 30)}" y1="{_n(py)}" x2="{_n(px + 30)}" y2="{_n(py + ph)}" stroke="#666666" stroke-width="1"/>')

    # lanes
    for lb in lay.lanes:
        out.append(
            f'<rect x="{_n(lb.x + 30)}" y="{_n(lb.y)}" width="{_n(lb.w - 30)}" height="{_n(lb.h)}" '
            f'fill="#fafafa" stroke="#999999" stroke-width="1"/>'
        )
        out.append(_vlabel(lb.name, lb.x + 45, lb.y + lb.h / 2, "#555555", 12))
        out.append(
            f'<line x1="{_n(lb.x + 60)}" y1="{_n(lb.y)}" x2="{_n(lb.x + 60)}" y2="{_n(lb.y + lb.h)}" '
            f'stroke="#bbbbbb" stroke-width="0.8"/>'
        )

    # edges
    for f in model.flows:
        pts = lay.edges.get(f.id)
        if not pts:
            continue
        coord = " ".join(f"{_n(x)},{_n(y)}" for x, y in pts)
        out.append(f'<polyline points="{coord}" fill="none" stroke="#4a4a4a" stroke-width="1.4" marker-end="url(#arrow)"/>')
        if f.label:
            (mx, my) = pts[1] if len(pts) > 2 else pts[0]
            if len(pts) > 2:
                mx = (pts[0][0] + pts[1][0]) / 2 or pts[1][0]
                my = (pts[1][1] + pts[2][1]) / 2 if pts[1][1] != pts[2][1] else pts[1][1] - 8
            out.append(
                f'<text x="{_n(mx + 4)}" y="{_n(my - 6)}" font-size="11" fill="#333333" '
                f'stroke="#ffffff" stroke-width="3" paint-order="stroke">{html.escape(f.label)}</text>'
            )

    # nodes
    for n in model.nodes:
        sb = lay.shapes.get(n.id)
        if sb is None:
            continue
        x, y, w_n, h_n = sb.x, sb.y, sb.w, sb.h
        if n.type == NodeType.TASK:
            fill, stroke = STYLE_BY_KIND.get(n.kind, STYLE_BY_KIND[None])
            out.append(
                f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w_n)}" height="{_n(h_n)}" rx="9" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
            )
            out.append(_wrap_label(n.name, x + w_n / 2, y + h_n / 2, 16))
            if n.automated:
                out.append(
                    f'<circle cx="{_n(x + w_n - 11)}" cy="{_n(y + 11)}" r="5" fill="#2e7d32"/>'
                )
        elif n.type in (NodeType.XOR_GATEWAY, NodeType.AND_GATEWAY):
            cx, cy = x + w_n / 2, y + h_n / 2
            r = w_n / 2
            pts_d = f"{_n(cx)},{_n(cy - r)} {_n(cx + r)},{_n(cy)} {_n(cx)},{_n(cy + r)} {_n(cx - r)},{_n(cy)}"
            out.append(f'<polygon points="{pts_d}" fill="#fff2cc" stroke="#d6b656" stroke-width="1.4"/>')
            glyph = "X" if n.type == NodeType.XOR_GATEWAY else "+"
            out.append(
                f'<text x="{_n(cx)}" y="{_n(cy + 4.5)}" text-anchor="middle" font-size="14" '
                f'font-weight="bold" fill="#7a5c00">{glyph}</text>'
            )
            if n.name:
                out.append(_wrap_label(n.name, cx, y - 8, 18))
        else:
            cx, cy = x + w_n / 2, y + h_n / 2
            r = w_n / 2
            if n.type == NodeType.START_EVENT:
                out.append(f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="#e8f5e9" stroke="#2e7d32" stroke-width="1.6"/>')
            elif n.type == NodeType.END_EVENT:
                out.append(f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="#fdecea" stroke="#b03a2e" stroke-width="3"/>')
            else:
                out.append(f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="#ffffff" stroke="#666666" stroke-width="1.4"/>')
            if n.name:
                out.append(_wrap_label(n.name, cx, y + h_n + 12, 20))

    out.append("</svg>")
    return "\n".join(out)


def _n(v: float) -> int:
    return int(round(v))


def _vlabel(text: str, x: float, y: float, color: str, size: int, weight: str = "normal") -> str:
    return (
        f'<text x="{_n(x)}" y="{_n(y)}" font-size="{size}" fill="{color}" font-weight="{weight}" '
        f'text-anchor="middle" transform="rotate(-90 {_n(x)} {_n(y)})">{html.escape(text[:40])}</text>'
    )


def _wrap_label(text: str, cx: float, cy: float, max_chars: int) -> str:
    words = (text or "").split()
    if not words:
        return ""
    lines: List[str] = []
    cur = ""
    for wd in words:
        if len(cur) + len(wd) + 1 <= max_chars:
            cur = f"{cur} {wd}".strip()
        else:
            lines.append(cur)
            cur = wd
        if len(lines) == 3:
            break
    if cur and len(lines) < 3:
        lines.append(cur)
    if len(lines) == 3 and words and " ".join(lines) != text:
        lines[2] = lines[2][: max_chars - 1] + "…"
    line_h = 13
    start_y = cy - (len(lines) - 1) * line_h / 2 + 4
    out = []
    for i, ln in enumerate(lines):
        out.append(
            f'<text x="{_n(cx)}" y="{_n(start_y + i * line_h)}" text-anchor="middle" '
            f'font-size="11.5" fill="#1a1a1a">{html.escape(ln)}</text>'
        )
    return "".join(out)


_DEFS = (
    '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
    'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    '<path d="M 0 0 L 10 5 L 0 10 z" fill="#4a4a4a"/></marker></defs>'
)
