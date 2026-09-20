"""Optimization Agent - the "critic".

Two complementary analysis modes:

1. **Static model analysis** (always available): pattern-based detection of
   manual data entry, sequential approvals, manual handoffs, single points
   of failure and manual decisioning in the As-Is model.
2. **Event-log analysis** (when a log is supplied): queue-wait and rework
   findings computed from real execution statistics.

Recommendations are concrete, node-targeted transformations. The agent
*applies* them to produce the To-Be model (automating tasks, parallelizing
approval chains, integrating handoffs) and recomputes the same metrics for
both models, giving a defensible before/after comparison for the thesis.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel

from process_miner.models import (
    BottleneckReport,
    Finding,
    ModelMetrics,
    NodeType,
    ProcessModel,
    Recommendation,
    TaskKind,
)

DATA_ENTRY_VERBS = {"creates", "records", "enters", "logs", "registers", "updates", "fills", "uploads", "invoices", "documents"}
APPROVAL_WORDS = {"approve", "approval", "authorise", "authorize", "sign", "review", "verify", "endorse", "sign-off"}
HANDOFF_WORDS = {"email", "mail", "call", "phone", "fax", "letter", "courier", "spreadsheet"}
CHECK_WORDS = {"check", "validate", "verify", "inspect", "screen", "test", "audit", "reconcile"}


class OptimizerOutput(BaseModel):
    report: BottleneckReport
    tobe_model: Optional[ProcessModel] = None


class OptimizationAgent:
    name = "optimizer"

    def run(
        self,
        model: ProcessModel,
        log_stats: Optional[object] = None,
        apply: bool = True,
    ) -> OptimizerOutput:
        findings: List[Finding] = []
        recommendations: List[Recommendation] = []

        findings.extend(self._static_findings(model))

        log_summary = None
        if log_stats is not None:
            log_summary = log_stats
            findings.extend(self._log_findings(log_summary))

        recommendations = self._recommendations(model, findings, log_summary)

        tobe: Optional[ProcessModel] = None
        if apply:
            tobe = self._apply_recommendations(model, recommendations)
        report = BottleneckReport(
            findings=findings,
            recommendations=recommendations,
            metrics_asis=model.summary_metrics(),
            metrics_tobe=(tobe or model).summary_metrics(),
            log_summary=log_summary,
        )
        return OptimizerOutput(report=report, tobe_model=tobe)

    # ------------------------------------------------------------------
    # Static findings
    # ------------------------------------------------------------------

    def _static_findings(self, model: ProcessModel) -> List[Finding]:
        findings: List[Finding] = []
        tasks = model.tasks()

        manual_entry = [t for t in tasks if not t.automated and _first_word_in(t.name, DATA_ENTRY_VERBS)]
        if manual_entry:
            findings.append(
                Finding(
                    id="F_MANUAL_ENTRY",
                    category="manual_data_entry",
                    severity="medium",
                    title=f"{len(manual_entry)} manual data-entry step(s)",
                    description=(
                        "Staff re-type information that already exists in source systems. "
                        "This is slow, error-prone and automatable."
                    ),
                    evidence=[t.name for t in manual_entry],
                    affected_nodes=[t.id for t in manual_entry],
                )
            )

        approval_chain = self._longest_sequential_chain(model, APPROVAL_WORDS)
        if len(approval_chain) >= 2:
            names = [model.node(nid).name for nid in approval_chain]
            findings.append(
                Finding(
                    id="F_SEQ_APPROVAL",
                    category="sequential_approval",
                    severity="high",
                    title=f"{len(approval_chain)} sequential approval/review steps on the critical path",
                    description=(
                        "Approvals run one after another even though they mostly depend on the "
                        "same input. Running them in parallel compresses cycle time."
                    ),
                    evidence=names,
                    affected_nodes=approval_chain,
                )
            )

        handoffs = [
            t for t in tasks
            if any(re.search(rf"\b{w}\b", t.name.lower()) for w in HANDOFF_WORDS)
        ]
        if handoffs:
            findings.append(
                Finding(
                    id="F_MANUAL_HANDOFF",
                    category="manual_handoff",
                    severity="medium",
                    title=f"{len(handoffs)} manual communication handoff(s)",
                    description="Work moves between roles via email/phone instead of system integration, causing latency and lost context.",
                    evidence=[t.name for t in handoffs],
                    affected_nodes=[t.id for t in handoffs],
                )
            )

        actor_load: dict = {}
        for t in tasks:
            if t.automated:
                continue  # systems cannot be a staffing single point of failure
            lane = t.actor or "Unassigned"
            if any(w in lane.lower() for w in ("system", "portal", "erp", "platform", "bot", "rpa")):
                continue
            actor_load[lane] = actor_load.get(lane, 0) + 1
        total = max(sum(1 for t in tasks if not t.automated), 1)
        hot_actor, hot_count = max(actor_load.items(), key=lambda kv: kv[1]) if actor_load else (None, 0)
        if hot_actor and hot_count / total > 0.5 and len(actor_load) > 1:
            findings.append(
                Finding(
                    id="F_SPOF",
                    category="single_point_of_failure",
                    severity="medium",
                    title=f"'{hot_actor}' performs {hot_count}/{total} tasks",
                    description="One role carries the majority of the work; absence or backlog directly stalls the process.",
                    evidence=[f"{k}: {v} tasks" for k, v in actor_load.items()],
                    affected_nodes=[t.id for t in tasks if (t.actor or "Unassigned") == hot_actor],
                )
            )

        manual_checks = [t for t in tasks if not t.automated and _first_word_in(t.name, CHECK_WORDS)]
        if len(manual_checks) >= 2:
            findings.append(
                Finding(
                    id="F_MANUAL_DECISION",
                    category="manual_decisioning",
                    severity="low",
                    title=f"{len(manual_checks)} manual verification steps",
                    description="Multiple human verification steps could be supported or replaced by business-rule/LLM automation with human review.",
                    evidence=[t.name for t in manual_checks],
                    affected_nodes=[t.id for t in manual_checks],
                )
            )

        return findings

    def _longest_sequential_chain(self, model: ProcessModel, keywords: set) -> List[str]:
        """Longest path of consecutive *human* tasks matching the keywords."""
        best: List[str] = []
        for start in model.tasks():
            if start.automated or not _name_has_keywords(start.name, keywords):
                continue
            chain = [start.id]
            cur = start.id
            while True:
                nxt = [t for t in model.out_nodes(cur)
                       if model.node(t) and model.node(t).type == NodeType.TASK
                       and not model.node(t).automated
                       and _name_has_keywords(model.node(t).name, keywords)]
                if len(nxt) != 1:
                    break
                cur = nxt[0]
                chain.append(cur)
            if len(chain) > len(best):
                best = chain
        return best

    def _log_findings(self, log_summary) -> List[Finding]:
        findings: List[Finding] = []
        bottlenecks = [a for a in log_summary.activities if a.median_wait_minutes >= 60][:3]
        for i, a in enumerate(bottlenecks):
            findings.append(
                Finding(
                    id=f"F_QUEUE_{i}",
                    category="queue_wait",
                    severity="high" if a.median_wait_minutes >= 2880 else "medium",
                    title=f"Queueing before '{a.name}' (median wait {self._fmt_wait(a.median_wait_minutes)})",
                    description=(
                        f"'{a.name}' is executed {a.frequency} times across {a.cases} cases and items wait "
                        f"a median of {self._fmt_wait(a.median_wait_minutes)} before it starts."
                    ),
                    evidence=[f"median wait: {self._fmt_wait(a.median_wait_minutes)}", f"frequency: {a.frequency}"],
                    affected_nodes=[a.name],
                )
            )
        rework = [a for a in log_summary.activities if a.rework_rate >= 0.15][:2]
        for i, a in enumerate(rework):
            findings.append(
                Finding(
                    id=f"F_REWORK_{i}",
                    category="rework_loop",
                    severity="medium",
                    title=f"Rework loop on '{a.name}' ({a.rework_rate:.0%} of executions are repeats)",
                    description=f"Activity '{a.name}' repeats within the same case {a.rework_count} times, indicating upstream quality issues.",
                    evidence=[f"repeat executions: {a.rework_count}", f"rework rate: {a.rework_rate:.0%}"],
                    affected_nodes=[a.name],
                )
            )
        return findings

    @staticmethod
    def _fmt_wait(minutes: float) -> str:
        if minutes >= 1440:
            return f"{minutes / 1440:.1f} days"
        if minutes >= 60:
            return f"{minutes / 60:.1f} hours"
        return f"{minutes:.0f} min"

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _recommendations(
        self,
        model: ProcessModel,
        findings: List[Finding],
        log_summary: Optional[object],
    ) -> List[Recommendation]:
        recs: List[Recommendation] = []
        tasks = model.tasks()

        manual_entry = [t for t in tasks if not t.automated and _first_word_in(t.name, DATA_ENTRY_VERBS)]
        if manual_entry:
            saved = sum(t.duration_minutes * 0.7 for t in manual_entry)
            recs.append(
                Recommendation(
                    id="R_AUTOMATE_ENTRY",
                    title="Automate manual data entry with RPA / system integration",
                    category="automation",
                    description=(
                        "Replace manual re-keying with service tasks (RPA bots or direct API calls to the "
                        "system of record): " + ", ".join(t.name for t in manual_entry) + "."
                    ),
                    affected_nodes=[t.id for t in manual_entry],
                    resolves_findings=["F_MANUAL_ENTRY"],
                    expected_impact="~70% effort reduction on data-entry steps; fewer input errors",
                    estimated_minutes_saved=round(saved, 1),
                    confidence=0.85,
                )
            )

        approval_chain = self._longest_sequential_chain(model, APPROVAL_WORDS)
        if len(approval_chain) >= 2:
            chain_time = sum(model.node(nid).duration_minutes for nid in approval_chain)
            recs.append(
                Recommendation(
                    id="R_PARALLEL_APPROVALS",
                    title="Run approvals in parallel with an AND gateway",
                    category="parallelization",
                    description=(
                        f"Execute '{model.node(approval_chain[0]).name}' and "
                        f"'{model.node(approval_chain[1]).name}' concurrently instead of sequentially."
                    ),
                    affected_nodes=approval_chain,
                    resolves_findings=["F_SEQ_APPROVAL"],
                    expected_impact=f"critical path shrinks by ~{max(0, chain_time - max(model.node(n).duration_minutes for n in approval_chain)):.0f} min",
                    estimated_minutes_saved=round(
                        max(0.0, chain_time - max(model.node(n).duration_minutes for n in approval_chain)), 1
                    ),
                    confidence=0.8,
                )
            )

        handoffs = [
            t for t in tasks
            if any(re.search(rf"\b{w}\b", t.name.lower()) for w in HANDOFF_WORDS)
        ]
        if handoffs:
            recs.append(
                Recommendation(
                    id="R_INTEGRATE_HANDOFF",
                    title="Integrate communication handoffs into the platform",
                    category="integration",
                    description=(
                        "Replace email/phone handoffs with automated notifications from the workflow engine: "
                        + ", ".join(t.name for t in handoffs) + "."
                    ),
                    affected_nodes=[t.id for t in handoffs],
                    resolves_findings=["F_MANUAL_HANDOFF"],
                    expected_impact="removes human latency from notification steps; full audit trail",
                    estimated_minutes_saved=round(sum(t.duration_minutes * 0.8 for t in handoffs), 1),
                    confidence=0.75,
                )
            )

        if log_summary is not None:
            top = next((a for a in log_summary.activities if a.median_wait_minutes >= 240), None)
            if top is not None:
                recs.append(
                    Recommendation(
                        id="R_SLA_QUEUE",
                        title=f"Add SLA / priority queueing before '{top.name}'",
                        category="policy",
                        description=(
                            f"Median wait before '{top.name}' is {self._fmt_wait(top.median_wait_minutes)}. "
                            "Introduce SLA timers with escalation and a prioritised work queue."
                        ),
                        affected_nodes=[top.name],
                        resolves_findings=["F_QUEUE_0"],
                        expected_impact="reduces idle time; makes waiting visible and manageable",
                        estimated_minutes_saved=round(top.median_wait_minutes * 0.3, 1),
                        confidence=0.6,
                    )
                )
            rework_act = next((a for a in log_summary.activities if a.rework_rate >= 0.15), None)
            if rework_act is not None:
                recs.append(
                    Recommendation(
                        id="R_UPSTREAM_VALIDATION",
                        title=f"Add upstream validation to cut rework on '{rework_act.name}'",
                        category="validation",
                        description=(
                            f"'{rework_act.name}' repeats within cases at a {rework_act.rework_rate:.0%} rate. "
                            "Validate inputs at intake to prevent the loop."
                        ),
                        affected_nodes=[rework_act.name],
                        resolves_findings=["F_REWORK_0"],
                        expected_impact="fewer loop iterations per case",
                        estimated_minutes_saved=round(rework_act.rework_count * 10, 1),
                        confidence=0.65,
                    )
                )

        return recs

    # ------------------------------------------------------------------
    # To-Be transformation
    # ------------------------------------------------------------------

    def _apply_recommendations(self, model: ProcessModel, recs: List[Recommendation]) -> ProcessModel:
        tobe = model.clone()
        tobe.id = model.id + "_tobe"
        tobe.name = model.name + " (To-Be)"
        tobe.metadata = {**model.metadata, "state": "to_be"}

        by_id = {r.id: r for r in recs}

        for rec_id in ("R_AUTOMATE_ENTRY", "R_INTEGRATE_HANDOFF"):
            rec = by_id.get(rec_id)
            if not rec:
                continue
            for nid in rec.affected_nodes:
                node = tobe.node(nid)
                if node is not None and node.type == NodeType.TASK:
                    node.kind = TaskKind.SERVICE
                    node.automated = True
                    node.duration_minutes = max(1.0, node.duration_minutes * 0.3)
                    node.description = (node.description + " [To-Be: automated]").strip()
                    rec.applied = True

        rec = by_id.get("R_PARALLEL_APPROVALS")
        if rec and len(rec.affected_nodes) >= 2:
            first_id, second_id = rec.affected_nodes[0], rec.affected_nodes[1]
            if self._parallelize_pair(tobe, first_id, second_id):
                rec.applied = True

        return tobe

    def _parallelize_pair(self, model: ProcessModel, a_id: str, b_id: str) -> bool:
        a, b = model.node(a_id), model.node(b_id)
        if a is None or b is None:
            return False
        # only when b directly follows a
        link = next((f for f in model.flows if f.source == a_id and f.target == b_id), None)
        if link is None:
            return False

        # boundary flows: everything entering a/b from outside and leaving them
        boundary_in = [f for f in model.flows
                       if f.target in (a_id, b_id) and f.source not in (a_id, b_id)]
        boundary_out = [f for f in model.flows
                        if f.source in (a_id, b_id) and f.target not in (a_id, b_id)]
        pred_sources = sorted({f.source for f in boundary_in})
        succ_targets = sorted({f.target for f in boundary_out})

        drop_ids = {link.id} | {f.id for f in boundary_in} | {f.id for f in boundary_out}
        model.flows = [f for f in model.flows if f.id not in drop_ids]

        split = model.add_node("", NodeType.AND_GATEWAY)
        join = model.add_node("", NodeType.AND_GATEWAY)
        for p in pred_sources:
            model.add_flow(p, split.id)
        model.add_flow(split.id, a_id)
        model.add_flow(split.id, b_id)
        model.add_flow(a_id, join.id)
        model.add_flow(b_id, join.id)
        for s in succ_targets:
            model.add_flow(join.id, s)
        return True


def _norm_verb(w: str) -> str:
    """'Creates' -> 'creat', 'create' -> 'creat', 'Enters' -> 'entr'."""
    return w.lower().strip(",.;:").rstrip("s").rstrip("e")


def _first_word_in(name: str, verbs: set) -> bool:
    first = name.strip().lower().split()
    if not first:
        return False
    norm = _norm_verb(first[0])
    return any(_norm_verb(v) == norm for v in verbs)


def _name_has_keywords(name: str, keywords: set) -> bool:
    low = name.lower()
    return any(k in low for k in keywords)
