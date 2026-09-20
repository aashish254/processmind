"""Tests for the BPMN 2.0 XML builder and layout engine."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from process_miner.agents.modeler import ProcessModelerAgent
from process_miner.bpmn.builder import to_bpmn_xml
from process_miner.bpmn.layout import layout
from process_miner.models import NodeType, ProcessModel

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}


@pytest.fixture(scope="module")
def vendor_bpmn(vendor_model):
    return to_bpmn_xml(vendor_model)


def test_xml_is_wellformed(vendor_bpmn):
    root = ET.fromstring(vendor_bpmn)
    assert root.tag.endswith("definitions")


def test_namespaces_present(vendor_bpmn):
    assert 'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"' in vendor_bpmn
    assert 'xmlns:bpmndi=' in vendor_bpmn
    assert "targetNamespace=" in vendor_bpmn


def test_collaboration_and_pool(vendor_bpmn):
    root = ET.fromstring(vendor_bpmn)
    assert root.find(".//bpmn:collaboration", NS) is not None
    p = root.find(".//bpmn:participant", NS)
    assert p is not None
    assert p.get("processRef")


def test_lanes_present(vendor_bpmn, vendor_model):
    root = ET.fromstring(vendor_bpmn)
    lanes = root.findall(".//bpmn:lane", NS)
    assert len(lanes) == len([a for a in vendor_model.actors()])
    # every task referenced in exactly one lane
    refs = [r.text for lane in lanes for r in lane.findall("bpmn:flowNodeRef", NS)]
    task_ids = {n.id for n in vendor_model.nodes}
    assert set(refs) == task_ids


def test_task_types_mapped(vendor_bpmn):
    root = ET.fromstring(vendor_bpmn)
    assert root.findall(".//bpmn:serviceTask", NS), "ERP tasks should be serviceTask"
    assert root.findall(".//bpmn:userTask", NS)
    assert root.findall(".//bpmn:sendTask", NS)


def test_xor_conditions(vendor_bpmn):
    root = ET.fromstring(vendor_bpmn)
    conds = root.findall(".//bpmn:conditionExpression", NS)
    assert conds
    labels = [c.text for c in conds]
    assert "Yes" in labels and "No" in labels


def test_di_completeness(vendor_bpmn, vendor_model):
    root = ET.fromstring(vendor_bpmn)
    shapes = {s.get("bpmnElement") for s in root.findall(".//bpmndi:BPMNShape", NS)}
    edges = {e.get("bpmnElement") for e in root.findall(".//bpmndi:BPMNEdge", NS)}
    assert {n.id for n in vendor_model.nodes} <= shapes
    assert {f.id for f in vendor_model.flows} <= edges


def test_waypoints_exist(vendor_bpmn):
    root = ET.fromstring(vendor_bpmn)
    for edge in root.findall(".//bpmndi:BPMNEdge", NS):
        assert len(edge.findall("di:waypoint", NS)) >= 2


def test_documentation_provenance(vendor_bpmn):
    root = ET.fromstring(vendor_bpmn)
    docs = root.findall(".//bpmn:documentation", NS)
    assert docs
    assert any("Source:" in (d.text or "") for d in docs)


def test_layout_no_shape_overlap(vendor_model):
    lay = layout(vendor_model)
    boxes = list(lay.shapes.values())
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            overlap_x = max(a.x, b.x) < min(a.x + a.w, b.x + b.w)
            overlap_y = max(a.y, b.y) < min(a.y + a.h, b.y + b.h)
            assert not (overlap_x and overlap_y), f"{a.node_id} overlaps {b.node_id}"


def test_layout_shapes_inside_lanes(vendor_model):
    lay = layout(vendor_model)
    for sb in lay.shapes.values():
        lane = next(l for l in lay.lanes if l.name == sb.lane)
        assert lane.y <= sb.y and sb.y + sb.h <= lane.y + lane.h + 1


def test_layout_deterministic(vendor_model):
    l1 = layout(vendor_model)
    l2 = layout(vendor_model)
    assert {(s.node_id, round(s.x, 1), round(s.y, 1)) for s in l1.shapes.values()} == {
        (s.node_id, round(s.x, 1), round(s.y, 1)) for s in l2.shapes.values()
    }


def test_empty_model_layout():
    m = ProcessModel(id="e", name="e")
    lay = layout(m)
    assert lay.width > 0


def test_minimal_model_bpmn():
    m = ProcessModel(id="mini", name="Mini")
    s = m.add_node("S", NodeType.START_EVENT)
    e = m.add_node("E", NodeType.END_EVENT)
    m.add_flow(s.id, e.id)
    xml = to_bpmn_xml(m)
    root = ET.fromstring(xml)
    assert root.find(".//bpmn:startEvent", NS) is not None
