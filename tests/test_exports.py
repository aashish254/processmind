"""Tests for the exporters: Mermaid, SVG, draw.io, HTML report."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from process_miner.export.drawio import process_to_drawio
from process_miner.export.html_report import build_report
from process_miner.export.mermaid import to_mermaid
from process_miner.export.svg import to_svg


def test_mermaid_structure(vendor_model):
    out = to_mermaid(vendor_model)
    assert out.startswith("flowchart TD")
    assert "subgraph" in out
    assert "-->" in out
    assert "|\"Yes\"|" in out or "|\"No\"|" in out


def test_mermaid_lanes(vendor_model):
    out = to_mermaid(vendor_model)
    assert "Procurement Officer" in out
    assert "ERP System" in out


def test_svg_wellformed(vendor_model):
    svg = to_svg(vendor_model)
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "marker" in svg  # arrowhead defs


def test_svg_contains_lanes_and_tasks(vendor_model):
    svg = to_svg(vendor_model)
    assert "Procurement Officer" in svg
    assert "screening" in svg  # task labels appear (possibly wrapped across lines)
    assert svg.count("<rect") >= len(vendor_model.tasks())


def test_svg_automated_marker(vendor_model):
    svg = to_svg(vendor_model)
    assert "#2e7d32" in svg  # automation dot colour present


def test_drawio_wellformed(vendor_model):
    xml = process_to_drawio(vendor_model)
    root = ET.fromstring(xml)
    assert root.tag == "mxfile"
    assert root.find("diagram") is not None


def test_drawio_swimlanes(vendor_model):
    xml = process_to_drawio(vendor_model)
    assert 'style="swimlane' in xml
    root = ET.fromstring(xml)
    cells = root.findall(".//mxCell")
    assert len(cells) > len(vendor_model.nodes)


def test_drawio_edges_have_endpoints(vendor_model):
    root = ET.fromstring(process_to_drawio(vendor_model))
    for edge in [c for c in root.findall(".//mxCell") if c.get("edge") == "1"]:
        assert edge.get("source") and edge.get("target")


def test_report_sections(vendor_model, tmp_path):
    from process_miner.agents.optimizer import OptimizationAgent
    from process_miner.models import PipelineResult
    from process_miner.bpmn.validate import validate_model

    opt = OptimizationAgent().run(vendor_model)
    result = PipelineResult(
        name=vendor_model.name,
        engine="builtin",
        modeler_method="offline-rules",
        model=vendor_model,
        validation=validate_model(vendor_model),
        bottleneck_report=opt.report,
        tobe_model=opt.tobe_model,
        artifacts={"x_model.json": "x_model.json"},
    )
    html = build_report(result)
    for section in ["As-Is process model", "Bottleneck findings", "Recommendations", "To-Be process model", "Mermaid source", "Artifacts"]:
        assert section in html
    assert "<svg" in html


def test_report_with_log_summary(vendor_model, inputs_dir):
    from process_miner.agents.optimizer import OptimizationAgent
    from process_miner.models import PipelineResult
    from process_miner.bpmn.validate import validate_model

    log = load_log = None
    from process_miner.mining.event_log import compute_summary, load_log as ll

    summary = compute_summary(ll((inputs_dir / "vendor_onboarding_events.csv").read_text(), "v"))
    opt = OptimizationAgent().run(vendor_model, log_stats=summary)
    result = PipelineResult(
        name=vendor_model.name,
        model=vendor_model,
        validation=validate_model(vendor_model),
        bottleneck_report=opt.report,
        tobe_model=opt.tobe_model,
    )
    html = build_report(result)
    assert "Event-log analytics" in html
    assert "Top variants" in html


def test_report_rejects_empty():
    from process_miner.models import PipelineResult

    with pytest.raises(ValueError):
        build_report(PipelineResult(name="empty"))
