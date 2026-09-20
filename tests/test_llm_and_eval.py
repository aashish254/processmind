"""Tests for the LLM provider layer (offline behavior, JSON repair) and evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from process_miner.config import LLMConfig
from process_miner.llm.providers import (
    LLMError,
    build_provider,
    extract_json,
)
from process_miner.models import NodeType, ProcessModel


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_code_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_prose():
    assert extract_json('Here you go:\n{"a": {"b": 2}} hope that helps') == {"a": {"b": 2}}


def test_extract_json_trailing_comma():
    assert extract_json('{"a": [1, 2,],}') == {"a": [1, 2]}


def test_extract_json_failure():
    with pytest.raises(LLMError):
        extract_json("no json here at all")


def test_build_provider_offline():
    assert build_provider(LLMConfig(provider="none")) is None
    assert build_provider(LLMConfig(provider="openai", api_key="")) is None


def test_build_provider_openai():
    p = build_provider(LLMConfig(provider="openai", api_key="sk-test", model="gpt-x"))
    assert p is not None
    assert p.name == "openai-compatible"


def test_build_provider_anthropic():
    p = build_provider(LLMConfig(provider="anthropic", api_key="k", model="m"))
    assert p.name == "anthropic"


def test_modeler_offline_without_provider(vendor_doc):
    from process_miner.agents.modeler import ProcessModelerAgent

    out = ProcessModelerAgent(provider=None).run(vendor_doc)
    assert out.method == "offline-rules"


def test_modeler_falls_back_on_llm_error(vendor_doc):
    from process_miner.agents.modeler import ProcessModelerAgent
    from process_miner.llm.providers import LLMProvider

    class ExplodingProvider(LLMProvider):
        name = "exploding"

        def complete_json(self, system, user):
            raise LLMError("boom")

    out = ProcessModelerAgent(provider=ExplodingProvider()).run(vendor_doc)
    assert out.method == "offline-rules"
    assert any("fell back" in w for w in out.warnings)


def test_modeler_uses_llm_ir(vendor_doc):
    """The LLM IR -> ProcessModel conversion must resolve names to ids."""
    from process_miner.agents.modeler import ProcessModelerAgent

    agent = ProcessModelerAgent()
    ir = {
        "name": "IR process",
        "description": "d",
        "actors": ["Bot", "Human"],
        "nodes": [
            {"name": "Kick off", "type": "start"},
            {"name": "Do work", "type": "task", "actor": "Human"},
            {"name": "System step", "type": "task", "actor": "Bot", "automated": True, "kind": "service"},
            {"name": "Done?", "type": "xor"},
            {"name": "Finish", "type": "end"},
            {"name": "Finish", "type": "end"},  # duplicate: must be deduped
        ],
        "flows": [
            {"source": "Kick off", "target": "Do work"},
            {"source": "Do work", "target": "System step"},
            {"source": "System step", "target": "Done?"},
            {"source": "Done?", "target": "Finish", "label": "Yes"},
            {"source": "Done?", "target": "Finish", "label": "No"},
            {"source": "Do work", "target": "Ghost node"},  # unresolvable: dropped
        ],
    }
    import xml.etree.ElementTree as ET  # noqa: F401

    model, warnings = agent._ir_to_model(ir, vendor_doc)
    assert len(model.end_events()) == 1  # dedupe worked
    assert any("unknown node names" in w for w in warnings)
    kinds = {n.kind.value for n in model.tasks() if n.kind}
    assert "service" in kinds
    assert validate_ok(model)


def validate_ok(m: ProcessModel) -> bool:
    from process_miner.bpmn.validate import validate_model

    return validate_model(m).ok


def test_evaluation_perfect_on_gold(tmp_path):
    """Gold co-designed with the SOPs -> F1 must be 1.0 on the curated corpus."""
    from process_miner.evaluation import evaluate_extractor

    gold = Path(__file__).resolve().parent.parent / "eval" / "gold"
    inputs = Path(__file__).resolve().parent.parent / "inputs"
    scores = evaluate_extractor(inputs, gold)
    assert len(scores) == 4  # includes the messy legacy document
    curated = [s for s in scores if not s["doc"].startswith("legacy")]
    assert len(curated) == 3
    for s in curated:
        assert s["task_f1"] == 1.0, s
        assert s["gateway_error"] == 0
    legacy = next(s for s in scores if s["doc"].startswith("legacy"))
    assert legacy["task_f1"] < 0.9  # honest degradation on legacy prose


def test_evaluation_fuzzy_matching():
    from process_miner.evaluation import match_tasks

    matches, missed, extra = match_tasks(
        ["Approve vendor request", "Send welcome pack", "Extra step"],
        ["Approve the vendor request", "Send the welcome pack to the vendor", "Missing thing"],
    )
    assert len(matches) == 2
    assert missed == ["Missing thing"]
    assert extra == ["Extra step"]


def test_metrics_model():
    from process_miner.evaluation import _prf

    assert _prf(2, 0, 0) == (1.0, 1.0, 1.0)
    assert _prf(1, 1, 1)[2] == pytest.approx(0.5)
