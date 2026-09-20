"""Tests for the Ingestion Agent."""

from __future__ import annotations

import pytest

from process_miner.agents.ingestion import IngestionAgent


def test_ingest_sop_metadata(vendor_doc):
    assert vendor_doc.metadata["process"] == "Vendor Onboarding"
    assert "Procurement Officer" in vendor_doc.metadata["roles"]
    assert vendor_doc.kind == "sop"


def test_ingest_sop_steps_exclude_boilerplate(vendor_doc):
    steps = vendor_doc.steps
    assert len(steps) >= 12
    joined = " ".join(steps).lower()
    assert "purpose" not in joined.split()[:2]
    assert not any(s.lower().startswith("this procedure defines") for s in steps)
    assert not any("approvals must be recorded" in s.lower() for s in steps)
    # actual flow steps present
    assert any(s.startswith("The process begins") for s in steps)
    assert any("background screening" in s for s in steps)


def test_ingest_sop_stats(vendor_doc):
    assert vendor_doc.stats.steps == len(vendor_doc.steps)
    assert vendor_doc.stats.words > 100


def test_ingest_raw_text():
    text = (
        "Process: Ping Pong\n"
        "Roles: Player A, Player B\n"
        "The process begins when a serve is performed.\n"
        "Player A returns the ball.\n"
    )
    doc = IngestionAgent().run(text)
    assert doc.metadata["process"] == "Ping Pong"
    assert len(doc.steps) == 2


def test_ingest_csv_detected_as_log():
    csv_text = "case_id,activity,timestamp,resource\nC1,Task A,2026-01-01 10:00,Bot\n"
    doc = IngestionAgent().run(csv_text)
    assert doc.kind == "log"
    assert doc.stats.steps == 1


def test_invalid_log_raises():
    with pytest.raises(ValueError):
        IngestionAgent().run("case_id,foo\nC1,bar\n")


def test_log_missing_required_column_raises():
    bad = "foo,activity,timestamp\n1,2,3\n"
    with pytest.raises(ValueError):
        IngestionAgent().run(bad)


def test_sections_detected(it_doc):
    titles = [s.title.lower() for s in it_doc.sections]
    assert any("purpose" in t for t in titles)
    assert any("procedure" in t for t in titles)
