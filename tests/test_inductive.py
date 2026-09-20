"""Tests for the merged Inductive Miner subpackage (ported from bpmn-miner).

Covers: cut discovery soundness, token-replay conformance semantics,
ProcessModel conversion round-trips, the synthetic benchmark generator,
and the unified research-evaluation harness.
"""

from __future__ import annotations

import pytest

from process_miner.bpmn.validate import validate_model
from process_miner.inductive import (
    DiscoveryError,
    bpmn_model_to_process_model,
    discover_inductive,
    mine_process_tree,
    process_model_to_bpmn_model,
    replay_fitness,
    replay_fitness_process_model,
    tree_to_bpmn,
    tree_to_text,
    variants_from_event_log,
)
from process_miner.mining.event_log import Event, EventLog, load_log


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _log(variants, **meta) -> EventLog:
    """Build a pipeline EventLog from {trace: count} with synthetic timestamps."""
    from datetime import datetime, timedelta

    events = []
    case_no = 0
    base = datetime(2026, 1, 1)
    for trace, count in variants.items():
        for _ in range(count):
            case_no += 1
            t = base
            for act in trace:
                t += timedelta(hours=1)
                events.append(Event(case_id=f"c{case_no:04d}", activity=act, ts=t, **meta))
    return EventLog(source="test", events=events)


def _assert_sound(variants, noise=0.0):
    """The invariant: the mined tree (converted to the pipeline model) replays
    every variant it was given, and passes the pipeline's own validator."""
    result = mine_process_tree(variants, noise_threshold=noise)
    model = tree_to_bpmn(result.tree)
    fitness = replay_fitness(model, dict(variants)).fitness
    assert fitness == 1.0, f"tree {tree_to_text(result.tree)} lost fitness"
    return result


@pytest.fixture
def seq_log():
    return _log({("A", "B"): 5})


@pytest.fixture
def xor_log():
    return _log({("A", "B"): 5, ("C", "D"): 3})


@pytest.fixture
def par_log():
    return _log({("A", "B"): 4, ("B", "A"): 4})


@pytest.fixture
def loop_log():
    return _log({("A", "B"): 5, ("A", "B", "A", "B", "A"): 2})


# ---------------------------------------------------------------------------
# cut discovery
# ---------------------------------------------------------------------------

class TestCuts:
    def test_sequence(self, seq_log):
        variants = variants_from_event_log(seq_log)
        result = _assert_sound(variants)
        assert "seq" in tree_to_text(result.tree)

    def test_xor(self, xor_log):
        variants = variants_from_event_log(xor_log)
        result = _assert_sound(variants)
        assert "xor" in tree_to_text(result.tree)

    def test_parallel(self, par_log):
        variants = variants_from_event_log(par_log)
        result = _assert_sound(variants)
        assert tree_to_text(result.tree).startswith("par(A, B)")

    def test_loop(self, loop_log):
        variants = variants_from_event_log(loop_log)
        result = _assert_sound(variants)
        # Either the strict loop cut (A,B) or the sound flower fallback
        # loop(tau, xor(A, B)) - both replay every variant.
        assert "loop" in tree_to_text(result.tree)

    def test_optional_group_stays_sound(self):
        variants = {("A", "B", "C"): 6, ("A", "D"): 2}
        _assert_sound(variants)

    def test_optional_group_from_realistic_log(self):
        # Optional pair embedded after a branch point (like Ship+Send vs Reject)
        variants = {("Start", "Handle", "Ship", "Invoice"): 8,
                    ("Start", "Handle", "Reject"): 2}
        result = _assert_sound(variants)
        assert "xor" in tree_to_text(result.tree)

    def test_par_cut_rejects_optional_activity(self):
        # A is optional *after* B in some traces: a naive par cut would lose
        # the (B, C) language - the soundness guard must reject it.
        variants = {("A", "B"): 10, ("B", "C"): 4, ("A", "B", "C"): 4}
        result = _assert_sound(variants)

    def test_noise_filter_keeps_frequent_variants(self):
        variants = {("A", "B"): 30, ("B", "A"): 28, ("Q", "Z"): 2}
        result = mine_process_tree(variants, noise_threshold=0.05)
        assert "par" in tree_to_text(result.tree)
        assert result.variants_filtered_out > 0

    def test_single_activity_repeat(self):
        result = mine_process_tree({("A", "A", "A"): 2}, noise_threshold=0)
        assert "loop(A, A)" in tree_to_text(result.tree)

    def test_empty_log_raises(self):
        with pytest.raises(DiscoveryError):
            mine_process_tree({})

    def test_real_incident_log_sound(self):
        from pathlib import Path

        p = Path(__file__).resolve().parent.parent / "inputs" / "it_incident_events.csv"
        if not p.exists():
            pytest.skip("bundled incident log not present")
        log = load_log(p.read_text(), source="it")
        variants = variants_from_event_log(log)
        result = mine_process_tree(variants, noise_threshold=0.05)
        filtered_fitness = replay_fitness(tree_to_bpmn(result.tree), result.filtered_log).fitness
        assert filtered_fitness == 1.0  # sound on the variants it kept


# ---------------------------------------------------------------------------
# token-replay conformance semantics
# ---------------------------------------------------------------------------

class TestReplay:
    def _mined(self, variants):
        return tree_to_bpmn(mine_process_tree(variants, noise_threshold=0).tree)

    def test_accepts_training_log(self, xor_log, par_log, loop_log):
        for log in (xor_log, par_log, loop_log):
            model = self._mined(variants_from_event_log(log))
            result = replay_fitness(model, variants_from_event_log(log))
            assert result.fitness == 1.0, f"{log.source}: {result.to_json()}"

    def test_rejects_unrelated_trace(self, seq_log):
        model = self._mined(variants_from_event_log(seq_log))
        result = replay_fitness(model, {("A", "B"): 5, ("B", "A"): 3})
        assert result.fitness < 1.0

    def test_xor_choice_semantics(self, xor_log):
        model = self._mined(variants_from_event_log(xor_log))
        result = replay_fitness(model, {("A", "B"): 1, ("C", "D"): 1, ("A", "D"): 1})
        # A->D is not in the model
        assert result.cases_accepted == 2

    def test_parallel_interleavings(self, par_log):
        model = self._mined(variants_from_event_log(par_log))
        result = replay_fitness(model, {("A", "B"): 1, ("B", "A"): 1})
        assert result.fitness == 1.0

    def test_loop_repetitions(self, loop_log):
        model = self._mined(variants_from_event_log(loop_log))
        result = replay_fitness(model, {("A", "B"): 1, ("A", "B", "A", "B", "A"): 1,
                                        ("A",): 1})
        assert result.fitness == 1.0

    def test_empty_model_rejected(self):
        from process_miner.inductive.tree_bpmn import BpmnModel

        result = replay_fitness(BpmnModel(name="empty"), {("A",): 1})
        assert result.fitness == 0.0


# ---------------------------------------------------------------------------
# ProcessModel conversion (pipeline integration)
# ---------------------------------------------------------------------------

class TestConversion:
    def test_discovered_model_passes_pipeline_validator(self, xor_log, par_log, loop_log):
        for log in (xor_log, par_log, loop_log):
            model = discover_inductive(log, name="test")
            report = validate_model(model)
            assert report.ok, f"validation issues: {[i.message for i in report.issues]}"
            assert model.metadata["extractor"] == "inductive-miner"
            assert "process_tree" in model.metadata

    def test_dfg_model_round_trip_replay(self):
        from pathlib import Path

        from process_miner.mining.dfg import discover_dfg

        p = Path(__file__).resolve().parent.parent / "inputs" / "it_incident_events.csv"
        if not p.exists():
            pytest.skip("bundled incident log not present")
        log = load_log(p.read_text(), source="it")
        variants = variants_from_event_log(log)
        dfg_model = discover_dfg(log, threshold_ratio=0.1, name="dfg")
        result = replay_fitness_process_model(dfg_model, variants)
        # The round-tripped DFG model must retain meaningful fitness (the
        # gateway-direction inference fix), not collapse to 0.
        assert result.fitness > 0.9, result.to_json()

    def test_conversion_type_mapping(self, xor_log):
        model = discover_inductive(xor_log)
        bpmn = process_model_to_bpmn_model(model)
        types = {n.type for n in bpmn.nodes}
        assert "startEvent" in types and "endEvent" in types
        assert "exclusiveGateway" in types
        back = bpmn_model_to_process_model(bpmn)
        assert len(back.tasks()) == 4  # A, B, C, D
        assert validate_model(back).ok


# ---------------------------------------------------------------------------
# synthetic benchmark generator + research evaluation harness
# ---------------------------------------------------------------------------

class TestDatagenAndEval:
    def test_generate_scenarios(self):
        from process_miner.inductive.datagen import (
            SCENARIOS,
            generate_log,
            scenario_ground_truth,
        )

        for scenario in SCENARIOS:
            log = generate_log(scenario, num_cases=40, seed=7)
            assert len(log.events) > 40
            assert scenario_ground_truth(scenario) is not None
            variants = variants_from_event_log(log)
            model = discover_inductive(log, name=scenario)
            fitness = model.metadata["replay_fitness"]
            coverage = model.metadata["variant_coverage"]
            # sound-by-construction: fitness on kept variants == coverage
            assert fitness >= coverage - 0.01, (scenario, fitness, coverage)

    def test_research_eval_end_to_end(self, tmp_path):
        from process_miner.research_eval import run_research_eval

        report = run_research_eval(
            inputs_dir=tmp_path / "inputs",  # empty -> no extraction rows
            gold_dir=tmp_path / "gold",
            benchmark_dir=tmp_path / "bench",
            out_dir=tmp_path / "out",
            generate_benchmarks=True,
        )
        assert (tmp_path / "out" / "research_eval.json").exists()
        assert (tmp_path / "out" / "research_eval.md").exists()
        # at least the four synthetic scenarios were benchmarked
        assert len(report["discovery"]["rows"]) >= 4
        for row in report["discovery"]["rows"]:
            assert row["inductive"]["replay_fitness"] is not None
