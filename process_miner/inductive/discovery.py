"""High-level Inductive Miner discovery on the pipeline's own EventLog.

This module wires the ported block-structured miner (``tree.py``) into the
merged ProcessMind pipeline:

    pipeline EventLog -> variants -> process tree -> BpmnModel
                      -> ProcessModel (full export pipeline)
                      -> token-replay fitness (soundness score)

The result metadata records the process tree, variant coverage, noise
threshold and replay fitness so every discovery run is self-documenting
for the research evaluation (``python -m process_miner.cli research-eval``).
"""

from __future__ import annotations

import time
from typing import Dict, Optional

from process_miner.models import ProcessModel

from .convert import bpmn_model_to_process_model, process_model_to_bpmn_model
from .replay import ReplayResult, replay_fitness
from .tree import (
    DiscoveryResult,
    DiscoveryError,
    ProcessTree,
    tree_to_text,
    variants_from_event_log,
)
from .tree_bpmn import tree_to_bpmn

__all__ = [
    "DiscoveryError",
    "DiscoveryResult",
    "ProcessTree",
    "ReplayResult",
    "discover_inductive",
    "replay_fitness_process_model",
    "tree_to_text",
]


def discover_inductive(
    log,
    name: str = "Discovered process (inductive)",
    noise_threshold: float = 0.05,
    allow_flower: bool = True,
) -> ProcessModel:
    """Discover a block-structured process model from a pipeline EventLog.

    Returns a :class:`process_miner.models.ProcessModel` so the discovered
    model can be exported (BPMN XML, SVG, draw.io, report), validated and
    optimised by the same stages the agents' models go through.
    """
    variants = variants_from_event_log(log)
    result = mine_with_report(variants, noise_threshold=noise_threshold,
                              allow_flower=allow_flower, name=name)
    return result["model"]


def mine_with_report(
    variants: Dict[tuple, int],
    name: str = "Discovered process (inductive)",
    noise_threshold: float = 0.05,
    allow_flower: bool = True,
) -> dict:
    """Mine, convert and score. Returns model + tree + fitness + timings.

    Kept separate from :func:`discover_inductive` so the research evaluation
    can record every intermediate artefact (tree text, coverage, fitness).
    """
    t0 = time.perf_counter()
    result = mine_process_tree_safe(variants, noise_threshold, allow_flower)
    tree: ProcessTree = result["tree"]
    bpmn = tree_to_bpmn(tree, name=name)
    model = bpmn_model_to_process_model(bpmn, extractor="inductive-miner")
    elapsed = time.perf_counter() - t0
    fitness = replay_fitness(bpmn, variants)
    model.metadata.update(
        {
            "process_tree": tree_to_text(tree),
            "tree_json": tree.to_json(),
            "variant_coverage": round(result["discovery"].coverage, 4),
            "variants_filtered_out": result["discovery"].variants_filtered_out,
            "flower_fallback": result["discovery"].flower_fallback,
            "noise_threshold": noise_threshold,
            "replay_fitness": round(fitness.fitness, 4),
            "replay_cases_accepted": fitness.cases_accepted,
            "replay_cases_total": fitness.cases_total,
            "discovery_seconds": round(elapsed, 4),
        }
    )
    return {
        "model": model,
        "tree": tree,
        "tree_text": tree_to_text(tree),
        "discovery": result["discovery"],
        "discovery_error": result["error"],
        "fitness": fitness,
        "seconds": elapsed,
    }


def mine_process_tree_safe(variants: Dict[tuple, int], noise_threshold: float,
                           allow_flower: bool) -> dict:
    """Run the miner, degrading gracefully on DiscoveryError.

    When no cut applies (and flower fallback is disabled) the miner raises;
    for the evaluation harness we surface the error instead of crashing.
    """
    from .tree import mine_process_tree

    try:
        discovery = mine_process_tree(variants, noise_threshold=noise_threshold,
                                      allow_flower=allow_flower)
        return {"tree": discovery.tree, "discovery": discovery, "error": None}
    except DiscoveryError as exc:
        # Degenerate fragment: emit a flower-equivalent tau model so the
        # evaluation row still records a (useless but sound) outcome.
        discovery = mine_process_tree(
            {k: v for k, v in variants.items() if k}, noise_threshold=0.0, allow_flower=True
        ) if any(variants) else None
        if discovery is None:
            raise
        return {"tree": discovery.tree, "discovery": discovery, "error": str(exc)}


def replay_fitness_process_model(model: ProcessModel, variants: Dict[tuple, int],
                                 state_cap: int = 50_000) -> ReplayResult:
    """Token-replay any pipeline ProcessModel against a variant multiset."""
    bpmn = process_model_to_bpmn_model(model)
    return replay_fitness(bpmn, variants, state_cap=state_cap)
