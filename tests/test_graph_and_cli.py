"""Tests for orchestration: both engines, equivalence, retry loop, CLI, API."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from process_miner.config import Settings
from process_miner.graph import (
    BuiltinEngine,
    analyze_log,
    run_pipeline,
    validate_artifact,
)

OPTIONS = Settings(engine="builtin", output_dir=Path("outputs/_tests"))


@pytest.fixture(scope="module")
def pipeline_result(inputs_dir):
    return run_pipeline(
        str(inputs_dir / "vendor_onboarding_sop.md"),
        options=OPTIONS.model_copy(deep=True),
        log_path=str(inputs_dir / "vendor_onboarding_events.csv"),
    )


def test_pipeline_success(pipeline_result):
    assert pipeline_result.validation.ok
    assert pipeline_result.model is not None
    assert pipeline_result.tobe_model is not None
    assert pipeline_result.engine == "builtin"
    assert pipeline_result.modeler_method == "offline-rules"


def test_artifacts_written(pipeline_result):
    for key in ["_model.json", "_bpmn.bpmn", "_asis.svg", "_tobe_bpmn.bpmn", "_tobe.svg",
                "_mermaid.mmd", "_process.drawio", "_report.html", "_result.json", "_log_stats.json"]:
        assert any(k.endswith(key) for k in pipeline_result.artifacts), f"missing {key}"
    for path in pipeline_result.artifacts.values():
        assert Path(path).exists()


def test_result_json_roundtrip(pipeline_result):
    raw = Path(pipeline_result.artifacts["vendor_onboarding_sop_result.json"]).read_text()
    data = json.loads(raw)
    assert data["model"]["name"]
    assert data["bottleneck_report"]["metrics_asis"]["task_count"] > 0


def test_langgraph_engine_equivalence(inputs_dir, pipeline_result):
    pytest.importorskip("langgraph")
    opts = OPTIONS.model_copy(deep=True)
    opts.engine = "langgraph"
    result = run_pipeline(
        str(inputs_dir / "vendor_onboarding_sop.md"),
        options=opts,
        log_path=str(inputs_dir / "vendor_onboarding_events.csv"),
    )
    assert result.engine == "langgraph"
    assert result.model.summary_metrics() == pipeline_result.model.summary_metrics()
    assert [f.title for f in result.bottleneck_report.findings] == [
        f.title for f in pipeline_result.bottleneck_report.findings
    ]


def test_validation_retry_loop_feeds_back():
    """A broken first attempt must trigger the validate->model retry with feedback."""
    calls = {"model": 0}

    class FlakyEngine(BuiltinEngine):
        def _flaky(self, state):
            return state

    # simulate: stage_model produces broken model on first call
    from process_miner.models import NodeType, ProcessModel

    m = ProcessModel(id="x", name="x")
    t = m.add_node("Lone task", NodeType.TASK)  # no start/end -> validation fails

    engine = BuiltinEngine(OPTIONS)
    state = {
        "doc": {"doc_id": "x", "name": "x", "kind": "sop", "text": "", "sections": [], "steps": [], "metadata": {}},
        "model": m,
        "artifacts": {},
        "warnings": [],
        "attempt": 0,
        "feedback": [],
        "timings": {},
        "engine": "builtin",
    }
    engine.pipeline.stage_validate(state)
    assert state["feedback"], "errors must be captured as feedback"
    assert state["attempt"] == 1


def test_repair_after_retries_exhausted():
    from process_miner.models import NodeType, ProcessModel

    m = ProcessModel(id="x", name="x")
    m.add_node("Lone task", NodeType.TASK)
    engine = BuiltinEngine(OPTIONS)
    state = {
        "doc": {"doc_id": "x", "name": "x", "kind": "sop"},
        "model": m,
        "artifacts": {},
        "warnings": [],
        "attempt": OPTIONS.max_repair_attempts,  # retries exhausted
        "feedback": [],
        "timings": {},
        "engine": "builtin",
    }
    engine.pipeline.stage_validate(state)
    assert state["validation"].ok, "repair must fix the model when retries are exhausted"
    assert any("auto-repaired" in w for w in state["warnings"])


def test_analyze_log_pathway(inputs_dir):
    result = analyze_log(str(inputs_dir / "it_incident_events.csv"), options=OPTIONS.model_copy(deep=True))
    assert result.modeler_method == "dfg-mining"
    assert result.validation.ok
    assert len(result.model.tasks()) >= 8
    assert result.bottleneck_report.log_summary is not None
    assert result.bottleneck_report.log_summary.cases == 300


def test_validate_artifact_bpmn(pipeline_result):
    bpmn_path = next(v for k, v in pipeline_result.artifacts.items() if k.endswith("_bpmn.bpmn") and "tobe" not in k)
    report = validate_artifact(bpmn_path)
    assert report.ok


def test_validate_artifact_model_json(pipeline_result):
    json_path = next(v for k, v in pipeline_result.artifacts.items() if k.endswith("_model.json") and "tobe" not in k)
    report = validate_artifact(json_path)
    assert report.ok


def test_validate_artifact_detects_broken(tmp_path):
    broken = tmp_path / "broken.bpmn"
    broken.write_text(
        '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        "<process><sequenceFlow id=\"f1\" sourceRef=\"a\" targetRef=\"ghost\"/></process></definitions>"
    )
    report = validate_artifact(str(broken))
    assert not report.ok


def test_cli_mine(inputs_dir, tmp_path, capsys):
    from process_miner.cli import main

    out = tmp_path / "cli_out"
    code = main([
        "mine", str(inputs_dir / "employee_leave_approval_sop.md"),
        "-o", str(out), "--engine", "builtin",
    ])
    assert code == 0
    assert (out / "employee_leave_approval_sop_report.html").exists()


def test_cli_analyze_log(inputs_dir, tmp_path):
    from process_miner.cli import main

    out = tmp_path / "cli_log"
    code = main(["analyze-log", str(inputs_dir / "vendor_onboarding_events.csv"), "-o", str(out)])
    assert code == 0
    assert any(p.suffix == ".bpmn" for p in out.iterdir())


def test_cli_validate(inputs_dir, tmp_path):
    from process_miner.cli import main

    result = run_pipeline(str(inputs_dir / "employee_leave_approval_sop.md"), options=OPTIONS.model_copy(deep=True))
    bpmn = next(v for k, v in result.artifacts.items() if k.endswith("_bpmn.bpmn"))
    code = main(["validate", bpmn])
    assert code == 0


def test_cli_eval(tmp_path):
    from process_miner.cli import main

    gold = Path(__file__).resolve().parent.parent / "eval" / "gold"
    inputs = Path(__file__).resolve().parent.parent / "inputs"
    out = tmp_path / "eval_out"
    code = main(["eval", "--gold", str(gold), "--inputs", str(inputs), "-o", str(out)])
    assert code == 0
    report = (out / "eval_report.json").read_text()
    data = json.loads(report)
    assert len(data) == 4  # 3 curated SOPs + the messy legacy document
    curated = [d for d in data if not d["doc"].startswith("legacy")]
    assert all(d["task_f1"] >= 0.9 for d in curated)
    # the legacy document is the honest external-validity datapoint: F1 well below 1.0
    legacy = next(d for d in data if d["doc"].startswith("legacy"))
    assert 0.0 <= legacy["task_f1"] < 0.9


def test_cli_demo(inputs_dir, tmp_path):
    from process_miner.cli import main

    out = tmp_path / "demo_out"
    code = main(["demo", "--inputs", str(inputs_dir), "-o", str(out)])
    assert code == 0
    htmls = list(out.glob("*.html"))
    # 3 SOP reports; both CSV logs are consumed by their matching SOP runs
    assert len(htmls) >= 3


def test_api_health():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from process_miner.api import create_app

    client = TestClient(create_app())
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_mine():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from process_miner.api import create_app

    client = TestClient(create_app())
    sop = (Path(__file__).resolve().parent.parent / "inputs" / "employee_leave_approval_sop.md").read_text()
    resp = client.post("/api/v1/mine", json={"text": sop, "optimize": False, "engine": "builtin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["validation_ok"] is True
    root = ET.fromstring(data["bpmn_xml"])
    assert root.tag.endswith("definitions")
    assert isinstance(data["findings"], list)


def test_api_mine_rejects_short_text():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from process_miner.api import create_app

    client = TestClient(create_app())
    resp = client.post("/api/v1/mine", json={"text": "too short"})
    assert resp.status_code == 422


def test_api_analyze_log(inputs_dir):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from process_miner.api import create_app

    client = TestClient(create_app())
    csv_bytes = (inputs_dir / "vendor_onboarding_events.csv").read_bytes()
    resp = client.post(
        "/api/v1/analyze-log",
        files={"file": ("vendor.csv", csv_bytes, "text/csv")},
        params={"threshold": 0.1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["cases"] == 250


def test_api_example_404():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from process_miner.api import create_app

    client = TestClient(create_app())
    resp = client.get("/api/v1/examples/does_not_exist.md")
    assert resp.status_code == 404
