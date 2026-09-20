"""Process Modeler Agent.

Extracts a :class:`ProcessModel` from an ingested document using, in order:

1. the configured LLM provider (schema-guided extraction with a bounded
   validate-and-retry self-correction loop), or
2. the deterministic offline rule parser (always available).

Every extraction path funnels through the same validator, so downstream
stages can rely on structurally sound models regardless of the extractor
used. The chosen ``method`` is recorded for the research evaluation.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from process_miner.agents.offline_parser import OfflineProcessParser
from process_miner.bpmn.validate import repair_model, validate_model
from process_miner.llm.prompts import (
    FEEDBACK_TMPL,
    PROCESS_EXTRACTION_SYSTEM,
    PROCESS_EXTRACTION_USER_TMPL,
)
from process_miner.llm.providers import LLMError, LLMProvider
from process_miner.models import (
    IngestedDocument,
    NodeType,
    ProcessModel,
    TaskKind,
    ValidationReport,
)

_TYPE_MAP = {
    "start": NodeType.START_EVENT,
    "end": NodeType.END_EVENT,
    "task": NodeType.TASK,
    "activity": NodeType.TASK,
    "xor": NodeType.XOR_GATEWAY,
    "exclusive": NodeType.XOR_GATEWAY,
    "gateway": NodeType.XOR_GATEWAY,
    "and": NodeType.AND_GATEWAY,
    "parallel": NodeType.AND_GATEWAY,
    "event": NodeType.INTERMEDIATE_EVENT,
    "intermediate": NodeType.INTERMEDIATE_EVENT,
}

_KIND_MAP = {k.value: k for k in TaskKind}


class _IRNode(BaseModel):
    name: str
    type: str = "task"
    actor: Optional[str] = None
    kind: Optional[str] = None
    automated: bool = False
    description: str = ""


class _IRFlow(BaseModel):
    source: str
    target: str
    label: Optional[str] = None


class _IR(BaseModel):
    name: str = "Process"
    description: str = ""
    actors: List[str] = Field(default_factory=list)
    nodes: List[_IRNode] = Field(default_factory=list)
    flows: List[_IRFlow] = Field(default_factory=list)


class ModelerOutput(BaseModel):
    model: ProcessModel
    method: str
    validation: ValidationReport
    warnings: List[str] = Field(default_factory=list)
    repaired: bool = False


class ProcessModelerAgent:
    name = "process_modeler"

    def __init__(self, provider: Optional[LLMProvider] = None, max_llm_retries: int = 2):
        self.provider = provider
        self.max_llm_retries = max_llm_retries
        self.offline = OfflineProcessParser()

    def run(self, doc: IngestedDocument, feedback: Optional[List[str]] = None) -> ModelerOutput:
        if doc.kind == "log":
            raise ValueError("Event logs are handled by the mining pathway, not the modeler agent")

        if self.provider is not None:
            try:
                return self._run_llm(doc, feedback)
            except LLMError as exc:
                out = self._run_offline(doc)
                out.warnings.insert(0, f"LLM extraction failed, fell back to offline rules: {exc}")
                return out
        return self._run_offline(doc)

    # -- LLM pathway ----------------------------------------------------------

    def _run_llm(self, doc: IngestedDocument, feedback: Optional[List[str]]) -> ModelerOutput:
        assert self.provider is not None
        warnings: List[str] = []
        feedback_text = ""
        if feedback:
            feedback_text = FEEDBACK_TMPL.format(errors="\n".join(f"- {e}" for e in feedback))
        user = PROCESS_EXTRACTION_USER_TMPL.format(document=doc.text[:12000], feedback=feedback_text)

        model: Optional[ProcessModel] = None
        report: Optional[ValidationReport] = None
        for attempt in range(self.max_llm_retries + 1):
            raw = self.provider.complete_json(PROCESS_EXTRACTION_SYSTEM, user)
            model, conv_warnings = self._ir_to_model(raw, doc)
            warnings.extend(conv_warnings)
            report = validate_model(model)
            if report.ok:
                return ModelerOutput(model=model, method=f"llm:{self.provider.name}", validation=report, warnings=warnings)
            user = PROCESS_EXTRACTION_USER_TMPL.format(
                document=doc.text[:12000],
                feedback=FEEDBACK_TMPL.format(errors="\n".join(i.message for i in report.errors)),
            )

        assert model is not None and report is not None
        repaired = repair_model(model)
        final_report = validate_model(repaired)
        return ModelerOutput(
            model=repaired,
            method=f"llm:{self.provider.name}+repair",
            validation=final_report,
            warnings=warnings + [f"Auto-repaired model after LLM extraction ({len(report.errors)} errors)"],
            repaired=True,
        )

    def _ir_to_model(self, raw: Dict[str, Any], doc: IngestedDocument) -> Tuple[ProcessModel, List[str]]:
        warnings: List[str] = []
        try:
            ir = _IR.model_validate(raw)
        except ValidationError as exc:
            raise LLMError(f"Extraction JSON does not match schema: {exc}") from exc

        model = ProcessModel(
            id=f"pm_{doc.doc_id}",
            name=ir.name or doc.name,
            description=ir.description,
            metadata={"extractor": f"llm", "doc_id": doc.doc_id, **doc.metadata},
        )

        # dedupe nodes by (name, type); map names -> ids
        name_to_id: Dict[Tuple[str, str], str] = {}
        for ir_node in ir.nodes:
            ntype = _TYPE_MAP.get(ir_node.type.strip().lower(), NodeType.TASK)
            key = (ir_node.name.strip().lower(), ntype.value)
            if key in name_to_id:
                continue
            kind = _KIND_MAP.get((ir_node.kind or "").strip().lower())
            node = model.add_node(
                ir_node.name.strip(),
                ntype,
                kind=kind,
                actor=(ir_node.actor or None),
                automated=bool(ir_node.automated),
                description=ir_node.description,
                source_text=f"llm:{ir_node.name}",
            )
            if node.type == NodeType.TASK and node.automated and node.kind is None:
                node.kind = TaskKind.SERVICE
            name_to_id[key] = node.id

        unresolved: List[str] = []
        for ir_flow in ir.flows:
            src = self._resolve(ir_flow.source, name_to_id)
            tgt = self._resolve(ir_flow.target, name_to_id)
            if src is None or tgt is None:
                unresolved.append(f"{ir_flow.source} -> {ir_flow.target}")
                continue
            model.add_flow(src, tgt, ir_flow.label)
        if unresolved:
            warnings.append(f"{len(unresolved)} flows referenced unknown node names and were dropped")
        return model, warnings

    @staticmethod
    def _resolve(name: str, name_to_id: Dict[Tuple[str, str], str]) -> Optional[str]:
        key = (name.strip().lower(), NodeType.TASK.value)
        if key in name_to_id:
            return name_to_id[key]
        # tolerate type mismatches: first node whose name matches
        for (nname, _), nid in name_to_id.items():
            if nname == key[0]:
                return nid
        return None

    # -- offline pathway --------------------------------------------------------

    def _run_offline(self, doc: IngestedDocument) -> ModelerOutput:
        parsed = self.offline.parse(doc)
        report = validate_model(parsed.model)
        repaired = False
        if not report.ok:
            parsed.model = repair_model(parsed.model)
            report = validate_model(parsed.model)
            repaired = True
        return ModelerOutput(
            model=parsed.model,
            method="offline-rules",
            validation=report,
            warnings=list(parsed.warnings),
            repaired=repaired,
        )
