"""Pipeline orchestration.

One set of stage functions, two engines:

* ``builtin``  - deterministic sequential execution (no dependencies).
* ``langgraph`` - the same stages as a LangGraph ``StateGraph`` with a
  conditional validate->model retry edge (bounded self-correction loop).

``auto`` picks LangGraph when installed, else builtin. Both engines return
identical :class:`PipelineResult` payloads (asserted in tests), so the
orchestration framework itself is a swappable research variable.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TypedDict

from process_miner.agents.ingestion import IngestionAgent
from process_miner.agents.modeler import ProcessModelerAgent
from process_miner.agents.optimizer import OptimizationAgent
from process_miner.bpmn.validate import repair_model, validate_model
from process_miner.config import Settings, load_settings, resolve_engine
from process_miner.export.drawio import process_to_drawio
from process_miner.export.html_report import build_report
from process_miner.export.mermaid import to_mermaid
from process_miner.export.svg import to_svg
from process_miner.bpmn.builder import to_bpmn_xml
from process_miner.llm.providers import build_provider
from process_miner.mining.dfg import discover_dfg
from process_miner.mining.event_log import compute_summary, load_log
from process_miner.models import (
    IngestedDocument,
    PipelineResult,
    ProcessModel,
)


class PipelineState(TypedDict, total=False):
    doc: Any
    model: Any
    validation: Any
    report: Any
    tobe_model: Any
    conformance: Any
    artifacts: Dict[str, str]
    warnings: List[str]
    attempt: int
    feedback: List[str]
    timings: Dict[str, float]
    result: Any
    engine: str
    modeler_method: str
    log_summary: Any
    log_events: Any
    discovered_model: Any


def make_pipeline(options: Optional[Settings] = None) -> "Pipeline":
    return Pipeline(options or load_settings())


class Pipeline:
    """Shared stage implementations used by both engines."""

    def __init__(self, options: Settings):
        self.options = options
        self.provider = build_provider(options.llm)

    # -- stages -------------------------------------------------------------

    def stage_ingest(self, state: PipelineState) -> PipelineState:
        t0 = time.perf_counter()
        doc: IngestedDocument = state["doc"]
        state["timings"]["ingest"] = time.perf_counter() - t0
        return state

    def stage_model(self, state: PipelineState) -> PipelineState:
        t0 = time.perf_counter()
        doc: IngestedDocument = state["doc"]
        agent = ProcessModelerAgent(provider=self.provider)
        out = agent.run(doc, feedback=state.get("feedback"))
        state["model"] = out.model
        state["warnings"] = state.get("warnings", []) + out.warnings
        state["timings"]["model"] = time.perf_counter() - t0
        state["modeler_method"] = out.method
        return state

    def stage_validate(self, state: PipelineState) -> PipelineState:
        t0 = time.perf_counter()
        model: ProcessModel = state["model"]
        report = validate_model(model)
        if not report.ok and state.get("attempt", 0) < self.options.max_repair_attempts:
            state["attempt"] = state.get("attempt", 0) + 1
            state["feedback"] = [i.message for i in report.errors]
            state["validation"] = report
        elif not report.ok:
            model = repair_model(model)
            state["model"] = model
            report = validate_model(model)
            state["warnings"] = state.get("warnings", []) + ["Model auto-repaired after validation failures"]
            state["validation"] = report
            state["feedback"] = []
        else:
            state["validation"] = report
            state["feedback"] = []
        state["timings"]["validate"] = time.perf_counter() - t0
        return state

    def validate_router(self, state: PipelineState) -> str:
        validation = state.get("validation")
        if validation is not None and not validation.ok and state.get("feedback"):
            return "model"
        return "optimize"

    def stage_optimize(self, state: PipelineState) -> PipelineState:
        t0 = time.perf_counter()
        model: ProcessModel = state["model"]
        agent = OptimizationAgent()
        out = agent.run(model, log_stats=state.get("log_summary"), apply=self.options.apply_optimizations)
        state["report"] = out.report
        state["tobe_model"] = out.tobe_model
        state["timings"]["optimize"] = time.perf_counter() - t0
        return state

    def stage_export(self, state: PipelineState) -> PipelineState:
        t0 = time.perf_counter()
        doc: IngestedDocument = state["doc"]
        model: ProcessModel = state["model"]
        out_dir = self.options.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = doc.doc_id
        artifacts: Dict[str, str] = {}

        artifacts[f"{slug}_model.json"] = _write(out_dir / f"{slug}_model.json", model.model_dump_json(indent=2))
        artifacts[f"{slug}_bpmn.bpmn"] = _write(out_dir / f"{slug}_bpmn.bpmn", to_bpmn_xml(model))
        artifacts[f"{slug}_asis.svg"] = _write(out_dir / f"{slug}_asis.svg", to_svg(model))
        artifacts[f"{slug}_mermaid.mmd"] = _write(out_dir / f"{slug}_mermaid.mmd", to_mermaid(model))
        artifacts[f"{slug}_process.drawio"] = _write(out_dir / f"{slug}_process.drawio", process_to_drawio(model))

        tobe: Optional[ProcessModel] = state.get("tobe_model")
        report = state.get("report")
        if tobe is not None:
            artifacts[f"{slug}_tobe_model.json"] = _write(out_dir / f"{slug}_tobe_model.json", tobe.model_dump_json(indent=2))
            artifacts[f"{slug}_tobe_bpmn.bpmn"] = _write(out_dir / f"{slug}_tobe_bpmn.bpmn", to_bpmn_xml(tobe))
            artifacts[f"{slug}_tobe.svg"] = _write(out_dir / f"{slug}_tobe.svg", to_svg(tobe))
        if report is not None and report.log_summary is not None:
            artifacts[f"{slug}_log_stats.json"] = _write(out_dir / f"{slug}_log_stats.json", report.log_summary.model_dump_json(indent=2))

        # conformance: documented (SOP) model vs enacted (log) behaviour
        conformance = None
        log_events = state.get("log_events")
        if doc.kind == "sop" and log_events is not None:
            from process_miner.conformance import compare_models

            conformance = compare_models(model, log_events, log_summary=report.log_summary if report else None)
            artifacts[f"{slug}_conformance.json"] = _write(
                out_dir / f"{slug}_conformance.json", conformance.model_dump_json(indent=2)
            )

        state["timings"]["export"] = time.perf_counter() - t0

        result = PipelineResult(
            name=doc.name,
            engine=state.get("engine", "builtin"),
            modeler_method=state.get("modeler_method", "unknown"),
            document=doc,
            model=model,
            validation=state.get("validation"),
            bottleneck_report=report,
            tobe_model=tobe,
            conformance=conformance,
            artifacts=artifacts,
            timings={k: round(v, 4) for k, v in state["timings"].items()},
            warnings=state.get("warnings", []),
        )
        artifacts[f"{slug}_result.json"] = _write(out_dir / f"{slug}_result.json", result.model_dump_json(indent=2))
        report_html = build_report(result)
        artifacts[f"{slug}_report.html"] = _write(out_dir / f"{slug}_report.html", report_html)
        result.artifacts = artifacts
        state["artifacts"] = artifacts
        state["result"] = result
        return state


def _write(path, content: str) -> str:
    path.write_text(content, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------


class BuiltinEngine:
    name = "builtin"

    def __init__(self, options: Settings):
        self.pipeline = Pipeline(options)
        self.options = options

    def run(self, doc: IngestedDocument, log_summary=None, log_events=None, discovered_model=None) -> PipelineResult:
        state: PipelineState = {
            "doc": doc,
            "artifacts": {},
            "warnings": [],
            "attempt": 0,
            "feedback": [],
            "timings": {},
            "engine": self.name,
        }
        if log_summary is not None:
            state["log_summary"] = log_summary
        if log_events is not None:
            state["log_events"] = log_events
        if discovered_model is not None:
            state["discovered_model"] = discovered_model
        p = self.pipeline
        p.stage_ingest(state)
        p.stage_model(state)
        for _ in range(self.options.max_repair_attempts + 1):
            p.stage_validate(state)
            if p.validate_router(state) == "optimize":
                break
            p.stage_model(state)  # retry with feedback
        p.stage_optimize(state)
        p.stage_export(state)
        return state["result"]


class LangGraphEngine:
    name = "langgraph"

    def __init__(self, options: Settings):
        if _langgraph_available() is False:
            raise ImportError("langgraph is not installed; use --engine builtin")
        self.options = options
        self.pipeline = Pipeline(options)
        self.graph = self._build()

    def _build(self):
        from langgraph.graph import END, StateGraph

        builder = StateGraph(PipelineState)
        p = self.pipeline
        builder.add_node("ingest", p.stage_ingest)
        builder.add_node("model", p.stage_model)
        builder.add_node("validate", p.stage_validate)
        builder.add_node("optimize", p.stage_optimize)
        builder.add_node("export", p.stage_export)
        builder.set_entry_point("ingest")
        builder.add_edge("ingest", "model")
        builder.add_edge("model", "validate")
        builder.add_conditional_edges("validate", p.validate_router, {"model": "model", "optimize": "optimize"})
        builder.add_edge("optimize", "export")
        builder.add_edge("export", END)
        return builder.compile()

    def run(self, doc: IngestedDocument, log_summary=None, log_events=None, discovered_model=None) -> PipelineResult:
        init: PipelineState = {
            "doc": doc,
            "artifacts": {},
            "warnings": [],
            "attempt": 0,
            "feedback": [],
            "timings": {},
            "engine": self.name,
        }
        if log_summary is not None:
            init["log_summary"] = log_summary
        if log_events is not None:
            init["log_events"] = log_events
        if discovered_model is not None:
            init["discovered_model"] = discovered_model
        final = self.graph.invoke(init)
        return final["result"]


def _langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run_pipeline(
    source: str,
    options: Optional[Settings] = None,
    log_path: Optional[str] = None,
) -> PipelineResult:
    """Full text -> BPMN pipeline for an SOP document."""
    opts = options or load_settings()
    doc = IngestionAgent().run(source)

    log_summary = None
    log_events = None
    discovered_model = None
    if log_path:
        from process_miner.mining.xes import load_event_log

        log_text = _read(log_path)
        log_events = load_event_log(log_text, source=log_path)
        log_summary = compute_summary(log_events)
        try:
            discovered_model = discover_dfg(
                log_events, threshold_ratio=opts.dfg_threshold_ratio,
                name=f"{doc.name} (discovered from log)",
            )
        except ValueError:
            discovered_model = None  # log too small to discover; conformance still runs

    engine_name = resolve_engine(opts.engine)
    engine: Any
    if engine_name == "langgraph":
        engine = LangGraphEngine(opts)
    else:
        engine = BuiltinEngine(opts)
    result = engine.run(
        doc,
        log_summary=log_summary,
        log_events=log_events,
        discovered_model=discovered_model,
    )

    if log_summary is not None and result.bottleneck_report is not None:
        result.bottleneck_report.log_summary = log_summary
    return result


def analyze_log(
    csv_path: str,
    options: Optional[Settings] = None,
    threshold_ratio: Optional[float] = None,
) -> PipelineResult:
    """Event-log pathway: mining -> DFG model -> optimization -> exports."""
    opts = options or load_settings()
    ratio = threshold_ratio if threshold_ratio is not None else opts.dfg_threshold_ratio
    from process_miner.mining.xes import load_event_log

    log_text = _read(csv_path)
    log = load_event_log(log_text, source=csv_path)
    summary = compute_summary(log)
    model = discover_dfg(log, threshold_ratio=ratio, name=f"{_name_from_path(csv_path)} (discovered)")

    optimizer = OptimizationAgent()
    opt_out = optimizer.run(model, log_stats=summary, apply=opts.apply_optimizations)

    # DFG discovery already produced the model, so we run only the export stage
    pipe = Pipeline(opts)
    state: PipelineState = {
        "doc": IngestionAgent().run(csv_path),
        "model": model,
        "validation": validate_model(model),
        "report": opt_out.report,
        "tobe_model": opt_out.tobe_model,
        "artifacts": {},
        "warnings": [],
        "attempt": 0,
        "feedback": [],
        "timings": {},
        "engine": "builtin",
        "log_summary": summary,
    }
    pipe.stage_export(state)
    result: PipelineResult = state["result"]
    result.modeler_method = "dfg-mining"
    return result


def discover_im_log(
    csv_path: str,
    options: Optional[Settings] = None,
    noise_threshold: float = 0.05,
) -> PipelineResult:
    """Event-log pathway via the Inductive Miner (extractor E6).

    Variants -> block-structured process tree -> BPMN -> ProcessModel,
    then the same optimization + export stages as the DFG pathway, so the
    two discovery extractors produce directly comparable artifact bundles.
    """
    opts = options or load_settings()
    from process_miner.inductive import mine_with_report, variants_from_event_log
    from process_miner.mining.xes import load_event_log

    log_text = _read(csv_path)
    log = load_event_log(log_text, source=csv_path)
    summary = compute_summary(log)
    variants = variants_from_event_log(log)
    im = mine_with_report(variants, name=f"{_name_from_path(csv_path)} (inductive)",
                          noise_threshold=noise_threshold)
    model = im["model"]

    optimizer = OptimizationAgent()
    opt_out = optimizer.run(model, log_stats=summary, apply=opts.apply_optimizations)

    pipe = Pipeline(opts)
    state: PipelineState = {
        "doc": IngestionAgent().run(csv_path),
        "model": model,
        "validation": validate_model(model),
        "report": opt_out.report,
        "tobe_model": opt_out.tobe_model,
        "artifacts": {},
        "warnings": [],
        "attempt": 0,
        "feedback": [],
        "timings": {},
        "engine": "builtin",
        "log_summary": summary,
    }
    pipe.stage_export(state)
    result: PipelineResult = state["result"]
    result.modeler_method = "inductive-miner"
    return result


def validate_artifact(path: str):
    """Validate a saved model JSON or BPMN XML file."""
    import json as _json
    import xml.etree.ElementTree as ET

    from process_miner.models import ValidationIssue, ValidationReport

    text = _read(path)
    if path.endswith(".json"):
        model = ProcessModel.model_validate(_json.loads(text))
        return validate_model(model)

    root = ET.fromstring(text)
    issues: List[str] = []
    flow_node_tags = {
        "task", "userTask", "serviceTask", "manualTask", "scriptTask",
        "businessRuleTask", "sendTask", "receiveTask", "startEvent", "endEvent",
        "exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway",
        "intermediateCatchEvent", "intermediateThrowEvent",
    }

    def local(tag: str) -> str:
        return tag.split("}", 1)[-1]

    nodes = [e for e in root.iter() if local(e.tag) in flow_node_tags]
    flows = [e for e in root.iter() if local(e.tag) == "sequenceFlow"]
    ids = {e.get("id") for e in root.iter() if e.get("id")}
    for f in flows:
        if f.get("sourceRef") not in ids or f.get("targetRef") not in ids:
            issues.append(f"sequenceFlow {f.get('id')} references a missing element")
    if not any(local(e.tag) == "startEvent" for e in nodes):
        issues.append("BPMN XML has no startEvent")
    if not any(local(e.tag) == "endEvent" for e in nodes):
        issues.append("BPMN XML has no endEvent")
    if not nodes:
        issues.append("no flow nodes found")
    return ValidationReport(
        ok=len(issues) == 0,
        issues=[ValidationIssue(code="BPMN_XML", severity="error", message=m) for m in issues],
    )


def _read(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8", errors="replace")


def _name_from_path(path: str) -> str:
    from pathlib import Path

    return Path(path).stem.replace("_", " ").replace("-", " ").title()
