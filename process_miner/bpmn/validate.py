"""Structural validation and auto-repair for ProcessModels.

``validate_model`` implements the quality gate between the Modeler Agent and
the BPMN exporter; ``repair_model`` performs guaranteed-safe fixes so that a
slightly broken extraction still yields an exportable model. The optimizer
and orchestration graph use the validation report to drive a bounded
self-correction loop (see graph.py).
"""

from __future__ import annotations

from typing import List, Set

from process_miner.models import (
    NodeType,
    ProcessModel,
    ValidationIssue,
    ValidationReport,
)


def validate_model(model: ProcessModel) -> ValidationReport:
    issues: List[ValidationIssue] = []
    ids: Set[str] = set()

    for n in model.nodes:
        if n.id in ids:
            issues.append(ValidationIssue(code="DUPLICATE_ID", message=f"Duplicate node id '{n.id}'", node_id=n.id))
        ids.add(n.id)
        if not n.name and n.type == NodeType.TASK:
            issues.append(ValidationIssue(code="EMPTY_NAME", message=f"Task '{n.id}' has no name", node_id=n.id))

    for f in model.flows:
        if f.source not in ids:
            issues.append(ValidationIssue(code="BAD_FLOW_REF", message=f"Flow '{f.id}' references missing source '{f.source}'"))
        if f.target not in ids:
            issues.append(ValidationIssue(code="BAD_FLOW_REF", message=f"Flow '{f.id}' references missing target '{f.target}'"))
        if f.source == f.target:
            issues.append(ValidationIssue(code="SELF_LOOP", message=f"Flow '{f.id}' is a self-loop on '{f.source}'"))

    starts = model.start_events()
    ends = model.end_events()
    if not starts:
        issues.append(ValidationIssue(code="NO_START", message="Model has no start event"))
    if not ends:
        issues.append(ValidationIssue(code="NO_END", message="Model has no end event"))
    if len(starts) > 1:
        issues.append(ValidationIssue(code="MULTI_START", message=f"Model has {len(starts)} start events", severity="warning"))

    for s in starts:
        if model.predecessors(s.id):
            issues.append(ValidationIssue(code="START_WITH_INPUT", message=f"Start event '{s.id}' has incoming flows", node_id=s.id))
    for e in ends:
        if model.successors(e.id):
            issues.append(ValidationIssue(code="END_WITH_OUTPUT", message=f"End event '{e.id}' has outgoing flows", node_id=e.id))

    # reachability from start
    if starts:
        reach = _reachable(model, [s.id for s in starts], forward=True)
        for n in model.nodes:
            if n.id not in reach and n.type != NodeType.START_EVENT:
                issues.append(
                    ValidationIssue(
                        code="UNREACHABLE",
                        message=f"Node '{n.name or n.id}' is not reachable from a start event",
                        node_id=n.id,
                        severity="warning",
                    )
                )
        reach_back = _reachable(model, [e.id for e in ends], forward=False)
        for n in model.nodes:
            if n.id not in reach_back and n.type != NodeType.END_EVENT:
                issues.append(
                    ValidationIssue(
                        code="NO_PATH_TO_END",
                        message=f"Node '{n.name or n.id}' has no path to an end event",
                        node_id=n.id,
                        severity="warning",
                    )
                )

    # dangling / degenerate nodes
    for n in model.nodes:
        incoming = model.predecessors(n.id)
        outgoing = model.successors(n.id)
        if n.type == NodeType.TASK and not incoming:
            issues.append(ValidationIssue(code="DANGLING_INPUT", message=f"Task '{n.name}' has no incoming flow", node_id=n.id))
        if n.type == NodeType.TASK and not outgoing:
            issues.append(ValidationIssue(code="DANGLING_OUTPUT", message=f"Task '{n.name}' has no outgoing flow", node_id=n.id))
        if n.type in (NodeType.XOR_GATEWAY, NodeType.AND_GATEWAY):
            if len(outgoing) == 1 and len(incoming) == 1:
                issues.append(
                    ValidationIssue(
                        code="PASS_THROUGH_GATEWAY",
                        message=f"Gateway at '{n.name or n.id}' neither splits nor merges",
                        node_id=n.id,
                        severity="warning",
                    )
                )
            if n.type == NodeType.XOR_GATEWAY and len(outgoing) > 1 and not all(f.label for f in outgoing):
                issues.append(
                    ValidationIssue(
                        code="UNLABELED_SPLIT",
                        message=f"XOR split at '{n.name or n.id}' has unlabeled outgoing flows",
                        node_id=n.id,
                        severity="warning",
                    )
                )
        if n.type == NodeType.TASK and len(incoming) > 1:
            issues.append(
                ValidationIssue(
                    code="IMPLICIT_MERGE",
                    message=f"Task '{n.name}' has multiple incoming flows without a merge gateway",
                    node_id=n.id,
                    severity="warning",
                )
            )

    errors = [i for i in issues if i.severity == "error"]
    return ValidationReport(ok=len(errors) == 0, issues=issues)


def repair_model(model: ProcessModel) -> ProcessModel:
    """Apply safe fixes until the model passes validation (single pass)."""
    ids = {n.id for n in model.nodes}
    model.flows = [f for f in model.flows if f.source in ids and f.target in ids and f.source != f.target]
    model.flows = list({(f.source, f.target, f.label or ""): f for f in model.flows}.values())

    starts = model.start_events()
    ends = model.end_events()

    if not starts:
        start = model.add_node("Process start", NodeType.START_EVENT)
        starts = [start]
    if not ends:
        end = model.add_node("Process end", NodeType.END_EVENT)
        ends = [end]

    start = starts[0]
    end = ends[0]

    # every node with no incoming gets connected from start (unless it IS a start)
    for n in list(model.nodes):
        if n.type == NodeType.START_EVENT or n.id == start.id:
            continue
        if not model.predecessors(n.id):
            model.add_flow(start.id, n.id)

    # every node with no outgoing gets connected to end (unless it IS an end)
    for n in list(model.nodes):
        if n.type == NodeType.END_EVENT or n.id == end.id:
            continue
        if not model.successors(n.id):
            model.add_flow(n.id, end.id)

    # guarantee start has at least one outgoing and end at least one incoming
    if not model.successors(start.id):
        first_task = next((t for t in model.tasks()), None)
        if first_task:
            model.add_flow(start.id, first_task.id)
    if not model.predecessors(end.id):
        last = next((n for n in reversed(model.nodes) if n.type != NodeType.END_EVENT), None)
        if last:
            model.add_flow(last.id, end.id)

    # label XOR split flows
    for g in model.gateways():
        outs = model.successors(g.id)
        if g.type == NodeType.XOR_GATEWAY and len(outs) > 1:
            for i, f in enumerate(outs):
                if not f.label:
                    f.label = ["Yes", "No", "Other"][min(i, 2)]
    return model


def _reachable(model: ProcessModel, roots: List[str], forward: bool) -> Set[str]:
    seen: Set[str] = set()
    stack = list(roots)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        neigh = model.out_nodes(cur) if forward else model.in_nodes(cur)
        stack.extend(neigh)
    return seen
