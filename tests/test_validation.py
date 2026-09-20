"""Tests for model validation and auto-repair."""

from __future__ import annotations

import pytest

from process_miner.bpmn.validate import repair_model, validate_model
from process_miner.models import NodeType, ProcessModel


def _empty() -> ProcessModel:
    return ProcessModel(id="t", name="t")


def test_valid_model_passes():
    m = _empty()
    s = m.add_node("S", NodeType.START_EVENT)
    t = m.add_node("T", NodeType.TASK)
    e = m.add_node("E", NodeType.END_EVENT)
    m.add_flow(s.id, t.id)
    m.add_flow(t.id, e.id)
    report = validate_model(m)
    assert report.ok
    assert not report.errors


def test_missing_start_detected():
    m = _empty()
    t = m.add_node("T", NodeType.TASK)
    e = m.add_node("E", NodeType.END_EVENT)
    m.add_flow(t.id, e.id)
    report = validate_model(m)
    assert not report.ok
    assert any(i.code == "NO_START" for i in report.errors)


def test_dangling_task_detected():
    m = _empty()
    s = m.add_node("S", NodeType.START_EVENT)
    e = m.add_node("E", NodeType.END_EVENT)
    orphan = m.add_node("Orphan", NodeType.TASK)
    m.add_flow(s.id, e.id)
    report = validate_model(m)
    codes = {i.code for i in report.issues}
    assert "DANGLING_INPUT" in codes or "UNREACHABLE" in codes


def test_bad_flow_ref_detected():
    m = _empty()
    s = m.add_node("S", NodeType.START_EVENT)
    e = m.add_node("E", NodeType.END_EVENT)
    m.add_flow(s.id, e.id)
    m.add_flow(s.id, "ghost", "x")
    report = validate_model(m)
    assert any(i.code == "BAD_FLOW_REF" for i in report.errors)


def test_end_with_output_detected():
    m = _empty()
    s = m.add_node("S", NodeType.START_EVENT)
    e = m.add_node("E", NodeType.END_EVENT)
    t = m.add_node("T", NodeType.TASK)
    m.add_flow(s.id, t.id)
    m.add_flow(t.id, e.id)
    m.add_flow(e.id, t.id)
    report = validate_model(m)
    assert any(i.code == "END_WITH_OUTPUT" for i in report.errors)


def test_repair_fixes_broken_model():
    m = _empty()
    t1 = m.add_node("T1", NodeType.TASK)
    t2 = m.add_node("T2", NodeType.TASK)
    m.add_flow(t1.id, t2.id)  # no start, no end
    repaired = repair_model(m)
    report = validate_model(repaired)
    assert report.ok
    assert repaired.start_events()
    assert repaired.end_events()


def test_repair_labels_xor_splits():
    m = _empty()
    s = m.add_node("S", NodeType.START_EVENT)
    gw = m.add_node("Ok?", NodeType.XOR_GATEWAY)
    e1 = m.add_node("E1", NodeType.END_EVENT)
    e2 = m.add_node("E2", NodeType.END_EVENT)
    m.add_flow(s.id, gw.id)
    m.add_flow(gw.id, e1.id)
    m.add_flow(gw.id, e2.id)
    repaired = repair_model(m)
    labels = {f.label for f in repaired.successors(gw.id)}
    assert labels == {"Yes", "No"}


def test_repair_is_idempotent():
    m = _empty()
    s = m.add_node("S", NodeType.START_EVENT)
    t = m.add_node("T", NodeType.TASK)
    e = m.add_node("E", NodeType.END_EVENT)
    m.add_flow(s.id, t.id)
    m.add_flow(t.id, e.id)
    r1 = repair_model(m)
    n_flows = len(r1.flows)
    r2 = repair_model(r1)
    assert len(r2.flows) == n_flows


def test_pass_through_gateway_warning():
    m = _empty()
    s = m.add_node("S", NodeType.START_EVENT)
    gw = m.add_node("", NodeType.XOR_GATEWAY)
    e = m.add_node("E", NodeType.END_EVENT)
    m.add_flow(s.id, gw.id)
    m.add_flow(gw.id, e.id)
    report = validate_model(m)
    assert any(i.code == "PASS_THROUGH_GATEWAY" for i in report.warnings)
