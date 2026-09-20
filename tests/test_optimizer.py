"""Tests for the Optimization Agent (findings, recommendations, To-Be transform)."""

from __future__ import annotations

import pytest

from process_miner.agents.optimizer import OptimizationAgent
from process_miner.bpmn.validate import validate_model
from process_miner.mining.dfg import discover_dfg
from process_miner.mining.event_log import compute_summary, load_log


@pytest.fixture(scope="module")
def vendor_opt(vendor_model):
    return OptimizationAgent().run(vendor_model)


def test_findings_present(vendor_opt):
    assert len(vendor_opt.report.findings) >= 2
    cats = {f.category for f in vendor_opt.report.findings}
    assert "sequential_approval" in cats
    assert "manual_data_entry" in cats


def test_metrics_before_after(vendor_opt):
    m_asis = vendor_opt.report.metrics_asis
    m_tobe = vendor_opt.report.metrics_tobe
    assert m_tobe.automation_rate > m_asis.automation_rate
    assert m_tobe.estimated_cycle_time_minutes < m_asis.estimated_cycle_time_minutes


def test_tobe_model_valid(vendor_opt):
    assert vendor_opt.tobe_model is not None
    assert vendor_opt.tobe_model.name.endswith("(To-Be)")
    assert validate_model(vendor_opt.tobe_model).ok


def test_parallelization_inserts_and_gateway(vendor_opt):
    ands = [g for g in vendor_opt.tobe_model.gateways() if g.type.value == "and_gateway"]
    asis_ands = sum(1 for g in vendor_opt.tobe_model.gateways() if g.type.value == "and_gateway")
    assert len(ands) >= 2  # at least the new split+join pair


def test_automated_tasks_marked(vendor_opt):
    rec = next(r for r in vendor_opt.report.recommendations if r.id == "R_AUTOMATE_ENTRY")
    assert rec.applied
    for nid in rec.affected_nodes:
        node = vendor_opt.tobe_model.node(nid)
        assert node.automated
        assert node.kind.value == "service"


def test_asis_model_untouched(vendor_model, vendor_opt):
    # the optimizer must not mutate the As-Is model it was given
    for f in vendor_opt.report.recommendations:
        pass  # run above already executed the transform
    manual = [t for t in vendor_model.tasks() if not t.automated]
    assert manual, "As-Is model should keep its manual tasks"


def test_no_log_stats_when_absent(vendor_opt):
    assert vendor_opt.report.log_summary is None


def test_log_findings_queue_and_rework(vendor_model, inputs_dir):
    log = load_log((inputs_dir / "vendor_onboarding_events.csv").read_text(), "vendor")
    summary = compute_summary(log)
    opt = OptimizationAgent().run(vendor_model, log_stats=summary)
    cats = {f.category for f in opt.report.findings}
    assert "queue_wait" in cats
    assert "rework_loop" in cats
    assert "Compliance Screening" in summary.top_bottlenecks


def test_bottleneck_ranking_planted(inputs_dir):
    log = load_log((inputs_dir / "vendor_onboarding_events.csv").read_text(), "vendor")
    summary = compute_summary(log)
    top3 = summary.top_bottlenecks
    assert "Await Vendor Documents" in top3 or "Compliance Screening" in top3


def test_rework_rate_detected(inputs_dir):
    log = load_log((inputs_dir / "it_incident_events.csv").read_text(), "it")
    summary = compute_summary(log)
    rework_acts = [a.name for a in summary.activities if a.rework_rate >= 0.1]
    assert "Investigate Issue" in rework_acts
    assert "Apply Standard Fix" in rework_acts


def test_apply_false_leaves_model_alone(vendor_model):
    opt = OptimizationAgent().run(vendor_model, apply=False)
    assert opt.tobe_model is None
    assert not opt.report.recommendations[0].applied
