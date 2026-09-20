"""Unit tests for the core data contracts in process_miner.models."""

from __future__ import annotations

import pytest

from process_miner.models import Flow, NodeType, ProcessModel, TaskKind, slugify


def _sample_model() -> ProcessModel:
    m = ProcessModel(id="pm_test", name="Test process")
    start = m.add_node("Start", NodeType.START_EVENT)
    t1 = m.add_node("Do things", NodeType.TASK, kind=TaskKind.USER, actor="Alice", duration_minutes=10)
    t2 = m.add_node("More things", NodeType.TASK, kind=TaskKind.SERVICE, actor="System", duration_minutes=5, automated=True)
    gw = m.add_node("Ok?", NodeType.XOR_GATEWAY)
    end1 = m.add_node("End ok", NodeType.END_EVENT)
    end2 = m.add_node("End bad", NodeType.END_EVENT)
    m.add_flow(start.id, t1.id)
    m.add_flow(t1.id, t2.id)
    m.add_flow(t2.id, gw.id)
    m.add_flow(gw.id, end1.id, "Yes")
    m.add_flow(gw.id, end2.id, "No")
    return m


def test_slugify():
    assert slugify("Validate Documents!") == "validate_documents"
    assert slugify("___") == "node"


def test_add_node_generates_unique_ids():
    m = ProcessModel(id="x", name="x")
    a = m.add_node("Approve", NodeType.TASK)
    b = m.add_node("Approve", NodeType.TASK)
    assert a.id != b.id


def test_add_flow_dedupes():
    m = _sample_model()
    n = len(m.flows)
    m.add_flow(m.nodes[0].id, m.nodes[1].id)
    assert len(m.flows) == n


def test_add_flow_rejects_self_loop():
    m = _sample_model()
    before = len(m.flows)
    assert m.add_flow(m.nodes[0].id, m.nodes[0].id) is None
    assert len(m.flows) == before


def test_adjacency_and_neighbors():
    m = _sample_model()
    start = m.start_events()[0]
    assert m.out_nodes(start.id) == [m.tasks()[0].id]
    gw = m.gateways()[0]
    assert len(m.out_nodes(gw.id)) == 2
    assert len(m.in_nodes(gw.id)) == 1


def test_typed_accessors():
    m = _sample_model()
    assert len(m.tasks()) == 2
    assert len(m.gateways()) == 1
    assert len(m.start_events()) == 1
    assert len(m.end_events()) == 2
    # nodes without an actor land in the "Unassigned" lane (first appearance order)
    assert m.actors() == ["Unassigned", "Alice", "System"]


def test_critical_path():
    m = _sample_model()
    # start -> t1(10) -> t2(5) -> gw -> end: critical path = 15
    assert m.critical_path_minutes() == 15.0


def test_critical_path_ignores_cycles():
    m = ProcessModel(id="c", name="c")
    a = m.add_node("A", NodeType.TASK, duration_minutes=10)
    b = m.add_node("B", NodeType.TASK, duration_minutes=20)
    m.add_flow(a.id, b.id)
    m.add_flow(b.id, a.id)  # cycle
    assert m.critical_path_minutes() == 30.0  # terminates, counts longest simple path


def test_automation_rate():
    m = _sample_model()
    assert m.automation_rate() == 0.5
    assert m.manual_task_count() == 1


def test_summary_metrics():
    m = _sample_model()
    metrics = m.summary_metrics()
    assert metrics.task_count == 2
    assert metrics.gateway_count == 1
    assert metrics.event_count == 3
    assert metrics.flow_count == 5
    assert metrics.lane_count == 3


def test_find_task_fuzzy():
    m = _sample_model()
    assert m.find_task("do things").id == m.tasks()[0].id
    assert m.find_task("nonexistent kaboom") is None


def test_remove_node_reconnect():
    m = _sample_model()
    t1, t2 = m.tasks()
    m.remove_node(t2.id, reconnect=True)
    assert m.node(t2.id) is None
    assert t1.id in m.out_nodes(m.start_events()[0].id)
    # t1 now connects straight to the gateway
    assert any(m.node(x).is_gateway() for x in m.out_nodes(t1.id))


def test_clone_is_deep():
    m = _sample_model()
    c = m.clone()
    c.nodes[0].name = "Changed"
    assert m.nodes[0].name != "Changed"


def test_json_roundtrip():
    m = _sample_model()
    m2 = ProcessModel.model_validate_json(m.model_dump_json())
    assert len(m2.nodes) == len(m.nodes)
    assert len(m2.flows) == len(m.flows)


def test_forward_back_edges_detects_cycle():
    m = ProcessModel(id="c", name="c")
    a = m.add_node("A", NodeType.TASK)
    b = m.add_node("B", NodeType.TASK)
    m.add_flow(a.id, b.id)
    m.add_flow(b.id, a.id)
    assert (b.id, a.id) in m._forward_back_edges()


def test_flow_labels_preserved():
    f = Flow(id="f1", source="a", target="b", label="Yes")
    assert f.label == "Yes"
