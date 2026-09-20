"""Layered (Sugiyama-style) layout engine for process models.

Produces clean, swimlane-aware coordinates used by *both* the BPMN DI
exporter and the SVG renderer:

1. cycle-closing back edges are removed,
2. nodes are ranked by longest-path layering on the remaining DAG,
3. ordering within ranks is improved with barycenter sweeps,
4. lanes (actors) are stacked vertically; nodes slot into (lane, rank) cells,
5. edges get orthogonal 4-point waypoints; back edges are routed below the pool.

The result is deterministic (same model -> same coordinates), which keeps
diffs of generated artefacts stable - useful for the thesis appendix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from process_miner.models import NodeType, ProcessModel

TASK_W, TASK_H = 120.0, 80.0
GATEWAY_SIZE = 50.0
EVENT_SIZE = 36.0
COL_STEP = 180.0
SLOT_H = 100.0
CONTENT_X0 = 120.0  # 30 pool header + 30 lane header + margin
POOL_HEADER_W = 30.0
LANE_HEADER_W = 30.0
Y0 = 40.0


def node_size(ntype: NodeType) -> Tuple[float, float]:
    if ntype == NodeType.TASK:
        return TASK_W, TASK_H
    if ntype in (NodeType.XOR_GATEWAY, NodeType.AND_GATEWAY):
        return GATEWAY_SIZE, GATEWAY_SIZE
    return EVENT_SIZE, EVENT_SIZE


@dataclass
class ShapeBox:
    node_id: str
    x: float
    y: float
    w: float
    h: float
    lane: str = ""
    rank: int = 0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class LaneBox:
    name: str
    index: int
    x: float
    y: float
    w: float
    h: float


@dataclass
class Layout:
    shapes: Dict[str, ShapeBox] = field(default_factory=dict)
    lanes: List[LaneBox] = field(default_factory=list)
    edges: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)
    width: float = 800.0
    height: float = 600.0
    pool: bool = False
    pool_box: Optional[Tuple[float, float, float, float]] = None


def layout(model: ProcessModel) -> Layout:
    if not model.nodes:
        return Layout(width=400, height=300)

    back = model._forward_back_edges()
    ranks = _rank_nodes(model, back)
    order = _order_nodes(model, ranks, back)
    lay = _assign_boxes(model, order)
    lay.edges = _route_edges(model, lay, back)
    return lay


# ---------------------------------------------------------------------------
# ranking + ordering
# ---------------------------------------------------------------------------


def _rank_nodes(model: ProcessModel, back: set) -> Dict[str, int]:
    forward: Dict[str, List[str]] = {n.id: [] for n in model.nodes}
    indeg: Dict[str, int] = {n.id: 0 for n in model.nodes}
    for f in model.flows:
        if (f.source, f.target) in back:
            continue
        if f.target not in forward[f.source]:
            forward[f.source].append(f.target)
            indeg[f.target] += 1
    # Kahn topological order
    from collections import deque

    queue = deque([nid for nid, d in indeg.items() if d == 0])
    topo: List[str] = []
    while queue:
        cur = queue.popleft()
        topo.append(cur)
        for nxt in forward[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    for n in model.nodes:  # nodes inside cycles not covered by Kahn
        if n.id not in topo:
            topo.append(n.id)

    ranks: Dict[str, int] = {}
    max_rank = 0
    for nid in topo:
        preds = [p for p in _forward_preds(model, back, nid) if p in ranks]
        ranks[nid] = (max((ranks[p] for p in preds), default=-1)) + 1
        max_rank = max(max_rank, ranks[nid])
    return ranks


def _forward_preds(model: ProcessModel, back: set, nid: str) -> List[str]:
    return [f.source for f in model.predecessors(nid) if (f.source, nid) not in back]


def _order_nodes(
    model: ProcessModel,
    ranks: Dict[str, int],
    back: set,
) -> Dict[int, List[str]]:
    by_rank: Dict[int, List[str]] = {}
    for n in model.nodes:
        by_rank.setdefault(ranks[n.id], []).append(n.id)
    for nid in by_rank:
        by_rank[nid].sort()

    def barycenter(nid: str, neighbours: List[str], pos: Dict[str, float]) -> float:
        vals = [pos.get(nb) for nb in neighbours if pos.get(nb) is not None]
        return sum(vals) / len(vals) if vals else float("inf")

    for _ in range(4):
        # downward sweep: order by predecessors' positions
        pos: Dict[str, float] = {}
        for r in sorted(by_rank):
            preds_map = {nid: [f.source for f in model.predecessors(nid) if (f.source, nid) not in back]
                         for nid in by_rank[r]}
            by_rank[r].sort(key=lambda nid: (barycenter(nid, preds_map[nid], pos), nid))
            for i, nid in enumerate(by_rank[r]):
                pos[nid] = float(i)
        # upward sweep: order by successors' positions
        pos = {}
        for r in sorted(by_rank, reverse=True):
            succ_map = {nid: [f.target for f in model.successors(nid) if (nid, f.target) not in back]
                        for nid in by_rank[r]}
            by_rank[r].sort(key=lambda nid: (barycenter(nid, succ_map[nid], pos), nid))
            for i, nid in enumerate(by_rank[r]):
                pos[nid] = float(i)
    return by_rank


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------


def _assign_boxes(model: ProcessModel, by_rank: Dict[int, List[str]]) -> Layout:
    lay = Layout(pool=True)

    # lane order = first appearance across ranks
    lane_order: List[str] = []
    for r in sorted(by_rank):
        for nid in by_rank[r]:
            lane = model.node(nid).actor or "Unassigned"
            if lane not in lane_order:
                lane_order.append(lane)

    # per (rank, lane) slot occupancy
    slot_of: Dict[Tuple[int, str], List[str]] = {}
    for r in sorted(by_rank):
        for nid in by_rank[r]:
            lane = model.node(nid).actor or "Unassigned"
            slot_of.setdefault((r, lane), []).append(nid)

    lane_heights = {lane: max(len(ids) for (r, ln), ids in slot_of.items() if ln == lane) * SLOT_H + 40
                    for lane in lane_order}

    y = Y0
    for i, lane in enumerate(lane_order):
        lay.lanes.append(LaneBox(name=lane, index=i, x=0.0, y=y,
                                 w=0.0, h=lane_heights[lane]))
        y += lane_heights[lane]

    max_rank = max(by_rank)
    for r in sorted(by_rank):
        for nid in by_rank[r]:
            node = model.node(nid)
            lane = node.actor or "Unassigned"
            lane_box = next(lb for lb in lay.lanes if lb.name == lane)
            w, h = node_size(node.type)
            k = slot_of[(r, lane)].index(nid)
            x = CONTENT_X0 + r * COL_STEP
            y_node = lane_box.y + 20 + k * SLOT_H + (SLOT_H - h) / 2
            lay.shapes[nid] = ShapeBox(node_id=nid, x=x, y=y_node, w=w, h=h, lane=lane, rank=r)

    content_w = CONTENT_X0 + (max_rank + 1) * COL_STEP
    total_h = sum(lb.h for lb in lay.lanes)
    for lb in lay.lanes:
        lb.w = content_w
    lay.width = content_w + POOL_HEADER_W + 40
    lay.height = total_h + Y0 + 80
    lay.pool_box = (0.0, Y0, content_w + POOL_HEADER_W + LANE_HEADER_W, total_h)
    # shift everything right of the pool+lane headers
    shift = POOL_HEADER_W + LANE_HEADER_W
    for sb in lay.shapes.values():
        sb.x += shift
    for lb in lay.lanes:
        lb.x = POOL_HEADER_W
        lb.w = content_w + LANE_HEADER_W
    lay.pool_box = (0.0, Y0, content_w + POOL_HEADER_W + LANE_HEADER_W, total_h)
    lay.height = max(lay.height, Y0 + total_h + 40)
    return lay


# ---------------------------------------------------------------------------
# edge routing
# ---------------------------------------------------------------------------


def _route_edges(model: ProcessModel, lay: Layout, back: set) -> Dict[str, List[Tuple[float, float]]]:
    routes: Dict[str, List[Tuple[float, float]]] = {}
    back_idx = 0
    lane_bottom = max((lb.y + lb.h for lb in lay.lanes), default=Y0)
    for f in model.flows:
        s = lay.shapes.get(f.source)
        t = lay.shapes.get(f.target)
        if s is None or t is None:
            continue
        if (f.source, f.target) in back:
            y_route = lane_bottom + 40 + back_idx * 30
            back_idx += 1
            routes[f.id] = [
                (s.cx, s.y + s.h),
                (s.cx, y_route),
                (t.cx, y_route),
                (t.cx, t.y + t.h),
            ]
            continue
        if s.rank < t.rank:
            if abs(s.cy - t.cy) < 1.0:
                routes[f.id] = [(s.x + s.w, s.cy), (t.x, t.cy)]
            else:
                xm = (s.x + s.w + t.x) / 2
                routes[f.id] = [(s.x + s.w, s.cy), (xm, s.cy), (xm, t.cy), (t.x, t.cy)]
        else:
            # same-rank or sideways edge: route above both shapes
            y_top = min(s.y, t.y) - 24
            routes[f.id] = [(s.cx, s.y), (s.cx, y_top), (t.cx, y_top), (t.cx, t.y)]
    return routes
