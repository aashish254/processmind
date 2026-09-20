"""Tests for conformance checking (documented SOP model vs enacted event log)."""

from __future__ import annotations

import pytest

from process_miner.conformance import (
    compare_models,
    match_activities,
    _documented_directly_follows,
)
from process_miner.mining.event_log import Event, EventLog, compute_summary
from process_miner.models import NodeType, ProcessModel


def _log() -> EventLog:
    rows = [
        ("C1", "Receive Application", "2026-01-01 10:00"),
        ("C1", "Check Documents", "2026-01-01 11:00"),
        ("C1", "Approve Vendor", "2026-01-01 12:00"),
        ("C2", "Receive Application", "2026-01-02 10:00"),
        ("C2", "Check Documents", "2026-01-02 11:00"),
        ("C2", "Check Documents", "2026-01-02 12:00"),  # rework repeat
        ("C2", "Approve Vendor", "2026-01-02 13:00"),
        ("C3", "Receive Application", "2026-01-03 10:00"),
        ("C3", "Do Shadow Work", "2026-01-03 11:00"),  # enacted but not documented
        ("C3", "Approve Vendor", "2026-01-03 12:00"),
    ]
    from datetime import datetime

    return EventLog(
        source="t",
        events=[Event(case_id=c, activity=a, ts=datetime.fromisoformat(ts)) for c, a, ts in rows],
    )


def _documented_model() -> ProcessModel:
    m = ProcessModel(id="pm", name="Doc")
    s = m.add_node("S", NodeType.START_EVENT)
    t1 = m.add_node("Receive the application", NodeType.TASK)
    t2 = m.add_node("Check the documents", NodeType.TASK)
    t3 = m.add_node("Approve the vendor", NodeType.TASK)
    t4 = m.add_node("Archive the file", NodeType.TASK)  # documented but never enacted
    e = m.add_node("E", NodeType.END_EVENT)
    for a, b in [(s, t1), (t1, t2), (t2, t3), (t3, t4), (t4, e)]:
        m.add_flow(a.id, b.id)
    return m


def test_activity_matching_fuzzy():
    matches, d_to_e, e_to_d = match_activities(
        ["Receive the application", "Check the documents", "Approve the vendor"],
        ["Receive Application", "Check Documents", "Approve Vendor", "Do Shadow Work"],
    )
    assert len(matches) == 3
    assert d_to_e["Receive the application"] == "Receive Application"
    assert "Do Shadow Work" not in e_to_d


def test_documented_directly_follows_skips_gateways():
    m = ProcessModel(id="g", name="g")
    t1 = m.add_node("A", NodeType.TASK)
    gw = m.add_node("gw", NodeType.XOR_GATEWAY)
    t2 = m.add_node("B", NodeType.TASK)
    m.add_flow(t1.id, gw.id)
    m.add_flow(gw.id, t2.id)
    pairs = _documented_directly_follows(m)
    assert pairs == {("A", "B")}


def test_conformance_detects_drift():
    report = compare_models(_documented_model(), _log(), log_summary=compute_summary(_log()))
    # matching
    assert len(report.matched_activities) == 3
    # documented but never enacted
    assert "Archive the file" in report.documented_only
    # enacted but never documented
    assert "Do Shadow Work" in report.enacted_only
    # issues assembled
    kinds = {i.kind for i in report.issues}
    assert "documented_not_enacted" in kinds
    assert "enacted_not_documented" in kinds
    # the observed rework on Check Documents is not documented as a loop
    assert "Check Documents" in report.rework_drift
    assert "rework_mismatch" in kinds
    assert report.summary


def test_conformance_sequence_indicators():
    report = compare_models(_documented_model(), _log())
    assert 0.0 <= report.df_precision <= 1.0
    assert 0.0 <= report.df_recall <= 1.0
    # the SOP documents Receive -> Check -> Approve -> Archive; the log shows
    # Receive -> Check / Check -> Approve but also Receive -> Do Shadow Work etc.
    assert report.sequence_enacted_only or report.df_recall < 1.0


def test_conformance_perfect_match():
    """A log that exactly mirrors the documented flow, including the rework loop."""
    from datetime import datetime

    rows = [
        ("C1", "Receive Application", "2026-01-01 10:00"),
        ("C1", "Check Documents", "2026-01-01 11:00"),
        ("C1", "Approve Vendor", "2026-01-01 12:00"),
        ("C1", "Check Documents", "2026-01-01 13:00"),  # enacted rework: Approve -> Check
        ("C1", "Approve Vendor", "2026-01-01 14:00"),
    ]
    log = EventLog(source="t", events=[Event(case_id=c, activity=a, ts=datetime.fromisoformat(ts)) for c, a, ts in rows])
    m = ProcessModel(id="pm", name="Doc")
    s = m.add_node("S", NodeType.START_EVENT)
    t1 = m.add_node("Receive Application", NodeType.TASK)
    t2 = m.add_node("Check Documents", NodeType.TASK)
    t3 = m.add_node("Approve Vendor", NodeType.TASK)
    e = m.add_node("E", NodeType.END_EVENT)
    for a, b in [(s, t1), (t1, t2), (t2, t3), (t3, e)]:
        m.add_flow(a.id, b.id)
    m.add_flow(t3.id, t2.id, "Rework")  # documented loop
    report = compare_models(m, log, log_summary=compute_summary(log))
    assert not report.enacted_only
    assert not report.documented_only
    assert not report.rework_drift
    assert report.df_recall == 1.0
    assert report.df_precision == 1.0
    assert not report.issues


def test_conformance_report_serialisable():
    report = compare_models(_documented_model(), _log())
    data = report.model_dump_json()
    assert "documented_not_enacted" in data


def test_conformance_pipeline_artifact(inputs_dir, tmp_path):
    """End-to-end: mining an SOP with --log must produce a conformance artifact."""
    from pathlib import Path

    from process_miner.config import Settings
    from process_miner.graph import run_pipeline

    opts = Settings(engine="builtin", output_dir=tmp_path)
    result = run_pipeline(
        str(inputs_dir / "vendor_onboarding_sop.md"),
        options=opts,
        log_path=str(inputs_dir / "vendor_onboarding_events.csv"),
    )
    assert result.conformance is not None
    assert Path(result.artifacts["vendor_onboarding_sop_conformance.json"]).exists()
    # the synthetic log was generated from the same process: substantial matching expected
    assert len(result.conformance.matched_activities) >= 8
