"""Inductive Miner subpackage - the block-structured discovery pathway.

Merged from the bpmn-miner capstone (cap 5) into ProcessMind:

* :mod:`.tree`       - mini Inductive Miner (Leemans-style cut hierarchy),
                       sound-by-construction process trees;
* :mod:`.tree_bpmn`  - process tree -> BPMN block structure;
* :mod:`.replay`     - token-based conformance replay fitness;
* :mod:`.convert`    - bridges to the pipeline's ``ProcessModel``;
* :mod:`.discovery`  - high-level discovery + fitness scoring entry points;
* :mod:`.datagen`    - synthetic benchmark logs with planted ground truth.
"""

from .convert import bpmn_model_to_process_model, process_model_to_bpmn_model
from .discovery import (
    discover_inductive,
    mine_with_report,
    replay_fitness_process_model,
)
from .replay import ReplayResult, replay_fitness
from .tree import (
    DiscoveryError,
    DiscoveryResult,
    ProcessTree,
    tree_to_text,
    variants_from_event_log,
)
from .tree_bpmn import BpmnFlow, BpmnModel, BpmnNode, tree_to_bpmn

__all__ = [
    "DiscoveryError",
    "DiscoveryResult",
    "ProcessTree",
    "ReplayResult",
    "BpmnModel",
    "BpmnNode",
    "BpmnFlow",
    "tree_to_bpmn",
    "tree_to_text",
    "variants_from_event_log",
    "mine_process_tree",
    "discover_inductive",
    "mine_with_report",
    "replay_fitness",
    "replay_fitness_process_model",
    "bpmn_model_to_process_model",
    "process_model_to_bpmn_model",
]


def mine_process_tree(variants, noise_threshold: float = 0.05, allow_flower: bool = True):
    """Re-export of the core miner for convenience."""
    from .tree import mine_process_tree as _mine

    return _mine(variants, noise_threshold=noise_threshold, allow_flower=allow_flower)
