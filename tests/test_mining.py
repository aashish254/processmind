"""Tests for event-log loading, statistics and DFG discovery."""

from __future__ import annotations

import pytest

from process_miner.bpmn.validate import validate_model
from process_miner.mining.dfg import discover_dfg
from process_miner.mining.event_log import compute_summary, load_log, parse_timestamp

CSV = """case_id,activity,timestamp,resource
C1,A,2026-01-01 10:00,Bot
C1,B,2026-01-01 11:00,Bot
C1,C,2026-01-01 13:00,Alice
C2,A,2026-01-02 09:00,Bot
C2,B,2026-01-02 09:30,Alice
C2,C,2026-01-02 10:00,Alice
"""


def test_parse_timestamp_formats():
    assert parse_timestamp("2026-01-01 10:00").hour == 10
    assert parse_timestamp("2026-01-01T10:00:00").hour == 10
    assert parse_timestamp("01/02/2026 10:00").day == 1
    with pytest.raises(ValueError):
        parse_timestamp("not a date")


def test_load_log_basics():
    log = load_log(CSV, "test")
    assert len(log.events) == 6
    assert len(log.cases) == 2


def test_load_log_skips_corrupt_rows():
    csv = CSV + "C3,A,garbage,Bot\n"
    log = load_log(csv, "test")
    assert len(log.events) == 6


def test_load_log_rejects_empty():
    with pytest.raises(ValueError):
        load_log("case_id,activity,timestamp\n", "test")


def test_summary_statistics():
    log = load_log(CSV, "test")
    s = compute_summary(log)
    assert s.cases == 2
    assert s.events == 6
    assert s.activities_count == 3
    by_name = {a.name: a for a in s.activities}
    assert by_name["A"].frequency == 2
    assert by_name["A"].cases == 2
    # B waits 60 and 30 min -> median 45
    assert by_name["B"].median_wait_minutes == 45.0
    assert s.start_activities[0] == "A"
    assert s.end_activities[0] == "C"


def test_variant_detection():
    log = load_log(CSV, "test")
    s = compute_summary(log)
    assert s.variants[0].count == 2
    assert s.variants[0].sequence == ["A", "B", "C"]


def test_rework_detection():
    csv = (
        "case_id,activity,timestamp,resource\n"
        "C1,A,2026-01-01 10:00,X\n"
        "C1,A,2026-01-01 11:00,X\n"
        "C1,A,2026-01-01 12:00,X\n"
        "C1,B,2026-01-01 13:00,X\n"
    )
    s = compute_summary(load_log(csv, "t"))
    a = next(a for a in s.activities if a.name == "A")
    assert a.rework_count == 2
    assert a.rework_rate == pytest.approx(2 / 3, abs=0.01)


def test_bottleneck_score_positive():
    csv = (
        "case_id,activity,timestamp,resource\n"
        "C1,A,2026-01-01 10:00,X\n"
        "C1,Z,2026-01-05 10:00,Y\n"
        "C1,B,2026-01-05 10:05,Y\n"
    )
    s = compute_summary(load_log(csv, "t"))
    z = next(a for a in s.activities if a.name == "Z")
    assert z.median_wait_minutes == 4 * 24 * 60
    assert z.bottleneck_score > 0.5


def test_dfg_discovers_model():
    log = load_log(CSV, "test")
    model = discover_dfg(log, threshold_ratio=0.1, name="T")
    assert validate_model(model).ok
    names = [t.name for t in model.tasks()]
    assert set(names) == {"A", "B", "C"}
    assert len(model.start_events()) == 1
    assert len(model.end_events()) == 1


def test_dfg_threshold_filters_edges():
    log = load_log(CSV, "test")
    strict = discover_dfg(log, threshold_ratio=0.9)
    loose = discover_dfg(log, threshold_ratio=0.1)
    assert len(strict.flows) <= len(loose.flows)


def test_dfg_from_it_log(inputs_dir):
    log = load_log((inputs_dir / "it_incident_events.csv").read_text(), "it")
    model = discover_dfg(log, threshold_ratio=0.15, name="IT discovered")
    assert validate_model(model).ok
    assert len(model.tasks()) >= 8
    # lanes come from the resource column
    assert any(a != "Unassigned" for a in model.actors())
