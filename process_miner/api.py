"""FastAPI service (optional dependency).

Endpoints:
    GET  /api/v1/health          - liveness + engine info
    POST /api/v1/mine            - SOP text -> model JSON + BPMN XML + findings
    POST /api/v1/analyze-log     - event-log CSV upload -> stats + discovered model
    GET  /api/v1/openapi.json    - schema

Run:  uvicorn process_miner.api:app --reload
"""

from __future__ import annotations

import json
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, UploadFile, File
    from pydantic import BaseModel, Field
except ImportError as _exc:  # pragma: no cover
    raise ImportError("Install fastapi to use the API: pip install fastapi uvicorn") from _exc

from process_miner import __version__
from process_miner.bpmn.builder import to_bpmn_xml
from process_miner.config import load_settings
from process_miner.export.mermaid import to_mermaid
from process_miner.export.svg import to_svg
from process_miner.graph import analyze_log, run_pipeline, validate_artifact
from process_miner.mining.dfg import discover_dfg
from process_miner.mining.event_log import compute_summary, load_log


class MineRequest(BaseModel):
    text: str = Field(..., min_length=30, description="Raw SOP / process narrative text")
    optimize: bool = True
    engine: str = "auto"


class MineResponse(BaseModel):
    name: str
    engine: str
    modeler_method: str
    model: dict
    bpmn_xml: str
    mermaid: str
    findings: list
    recommendations: list
    validation_ok: bool


def create_app() -> "FastAPI":
    app = FastAPI(
        title="ProcessMind API",
        description="Enterprise AI Process Mining & BPMN Automation",
        version=__version__,
    )
    settings = load_settings()

    @app.get("/api/v1/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "engine": settings.engine,
            "llm_provider": settings.llm.provider if settings.llm.enabled else "offline",
        }

    @app.post("/api/v1/mine", response_model=MineResponse)
    def mine(req: MineRequest) -> MineResponse:
        opts = load_settings()
        opts.apply_optimizations = req.optimize
        opts.engine = req.engine
        try:
            result = run_pipeline(req.text, options=opts)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if result.model is None or result.bottleneck_report is None:  # pragma: no cover
            raise HTTPException(status_code=500, detail="pipeline produced no model")
        return MineResponse(
            name=result.name,
            engine=result.engine,
            modeler_method=result.modeler_method,
            model=json.loads(result.model.model_dump_json()),
            bpmn_xml=to_bpmn_xml(result.model),
            mermaid=to_mermaid(result.model),
            findings=[f.model_dump() for f in result.bottleneck_report.findings],
            recommendations=[r.model_dump() for r in result.bottleneck_report.recommendations],
            validation_ok=bool(result.validation and result.validation.ok),
        )

    @app.post("/api/v1/analyze-log")
    async def analyze(file: UploadFile = File(...), threshold: float = 0.1) -> dict:
        raw = await file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="CSV must be UTF-8") from exc
        try:
            from process_miner.mining.xes import load_event_log

            log = load_event_log(text, source=file.filename or "upload")
            summary = compute_summary(log)
            model = discover_dfg(log, threshold_ratio=threshold, name=f"{file.filename} (discovered)")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "summary": json.loads(summary.model_dump_json()),
            "model": json.loads(model.model_dump_json()),
            "bpmn_xml": to_bpmn_xml(model),
            "svg": to_svg(model),
        }

    @app.get("/api/v1/examples/{name}")
    def example(name: str) -> dict:
        """Run the pipeline on a bundled example document."""
        from pathlib import Path

        path = Path("inputs") / f"{name}"
        if not path.exists():
            candidates = list(Path("inputs").glob("*.md"))
            matches = [c for c in candidates if name in c.stem]
            if not matches:
                raise HTTPException(status_code=404, detail=f"no example named {name}")
            path = matches[0]
        result = run_pipeline(str(path), options=settings)
        return json.loads(result.model_dump_json())

    return app


app = create_app()
