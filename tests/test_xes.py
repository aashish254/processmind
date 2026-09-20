"""Tests for XES loading/writing and content-based log dispatch."""

from __future__ import annotations

from datetime import datetime

import pytest

from process_miner.mining.event_log import Event, EventLog, compute_summary
from process_miner.mining.xes import load_event_log, load_xes, to_xes

XES_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<log xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.0">
  <string key="concept:name" value="Sample log"/>
  <trace>
    <string key="concept:name" value="Case A"/>
    <event>
      <string key="concept:name" value="Start task"/>
      <date key="time:timestamp" value="2026-01-05T08:00:00.000+00:00"/>
      <string key="org:resource" value="Bot"/>
    </event>
    <event>
      <string key="concept:name" value="End task"/>
      <date key="time:timestamp" value="2026-01-05T09:30:00.000+00:00"/>
    </event>
  </trace>
  <trace>
    <string key="concept:name" value="Case B"/>
    <event>
      <string key="concept:name" value="Start task"/>
      <date key="time:timestamp" value="2026-01-06T08:00:00.000+00:00"/>
    </event>
  </trace>
</log>
"""


def test_load_xes_basics():
    log = load_xes(XES_SAMPLE, "sample.xes")
    assert len(log.events) == 3
    assert len(log.cases) == 2
    first = sorted(log.events, key=lambda e: e.ts)[0]
    assert first.case_id == "Case A"
    assert first.activity == "Start task"
    assert first.resource == "Bot"


def test_load_xes_namespaced():
    namespaced = XES_SAMPLE.replace("<log ", '<log xmlns="http://www.xes-standard.org/" ')
    log = load_xes(namespaced)
    assert len(log.events) == 3


def test_load_xes_rejects_garbage():
    with pytest.raises(ValueError):
        load_xes("not xml at all")
    with pytest.raises(ValueError):
        load_xes("<notalog></notalog>")
    with pytest.raises(ValueError):
        load_xes('<log><trace><event></event></trace></log>')


def test_xes_roundtrip():
    log = EventLog(
        source="t",
        events=[
            Event(case_id="C1", activity="A", ts=datetime(2026, 3, 1, 10, 0), resource="Bot"),
            Event(case_id="C1", activity="B", ts=datetime(2026, 3, 1, 11, 0)),
        ],
    )
    xml = to_xes(log, "roundtrip")
    back = load_xes(xml)
    assert len(back.events) == 2
    assert {e.activity for e in back.events} == {"A", "B"}
    assert back.events[0].resource == "Bot"


def test_dispatcher_picks_xes_vs_csv():
    assert load_event_log(XES_SAMPLE, "s.xes").events
    csv = "case_id,activity,timestamp\nC1,A,2026-01-01 10:00\n"
    assert load_event_log(csv, "s.csv").events
    with pytest.raises(ValueError):
        load_event_log("case_id,activity,timestamp\n", "bad.csv")


def test_xes_through_full_pipeline(inputs_dir, tmp_path):
    """A .xes file supplied as --log must flow through mining + conformance."""
    from pathlib import Path

    from process_miner.config import Settings
    from process_miner.graph import run_pipeline

    opts = Settings(engine="builtin", output_dir=tmp_path)
    result = run_pipeline(
        str(inputs_dir / "it_incident_management_sop.md"),
        options=opts,
        log_path=str(inputs_dir / "it_incident_events.xes"),
    )
    assert result.bottleneck_report is not None
    assert result.bottleneck_report.log_summary is not None
    assert result.bottleneck_report.log_summary.cases == 60
    assert result.conformance is not None


def test_xes_ingestion_detection():
    from process_miner.agents.ingestion import IngestionAgent

    doc = IngestionAgent().run(XES_SAMPLE)
    assert doc.kind == "log"
    assert doc.metadata["format"] == "xes"


def test_xes_summary_statistics():
    log = load_xes(XES_SAMPLE)
    summary = compute_summary(log)
    assert summary.cases == 2
    by_name = {a.name: a for a in summary.activities}
    assert by_name["Start task"].frequency == 2
