"""Synthetic event-log generator with *planted* ground truth.

Ported from the bpmn-miner capstone (cap 5) and adapted to produce the
pipeline's own pydantic :class:`process_miner.mining.event_log.EventLog`,
so generated scenarios feed every extractor (DFG, Inductive Miner, LLM
agents) without adapters.

Research role: each scenario plants known structure (a rework loop, a
branch, a parallel pair in procurement; queue bottlenecks in the wait
ranges) so detection can be judged against ground truth - the benchmark
corpus for the merged study's discovery experiment (docs/RESEARCH.md §5).
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from process_miner.mining.event_log import Event, EventLog

# scenario spec: variants with weights, per-activity wait ranges (seconds),
# resources, and intentional bottleneck configuration
SCENARIOS: Dict[str, dict] = {
    "order_to_cash": {
        "variants": [
            (("Receive Order", "Credit Check", "Approve Order", "Ship Item", "Send Invoice",
              "Payment Received", "Close Order"), 55),
            (("Receive Order", "Credit Check", "Approve Order", "Clarify Details",
              "Approve Order", "Ship Item", "Send Invoice", "Payment Received",
              "Close Order"), 15),
            (("Receive Order", "Credit Check", "Reject Order", "Close Order"), 10),
            (("Receive Order", "Credit Check", "Approve Order", "Ship Item", "Send Invoice",
              "Payment Overdue", "Send Reminder", "Payment Received", "Close Order"), 12),
            (("Receive Order", "Credit Check", "Approve Order", "Ship Item", "Send Invoice",
              "Payment Overdue", "Write Off", "Close Order"), 8),
        ],
        "waits": {
            "Receive Order": (60, 300), "Credit Check": (1800, 28800),   # bottleneck
            "Approve Order": (900, 7200), "Clarify Details": (600, 3600),
            "Reject Order": (300, 1800), "Ship Item": (3600, 86400),
            "Send Invoice": (60, 600), "Payment Received": (86400, 604800),
            "Payment Overdue": (86400, 259200), "Send Reminder": (3600, 86400),
            "Write Off": (3600, 43200), "Close Order": (60, 3600),
        },
        "resources": {
            "Credit Check": "Credit Team", "Approve Order": "Sales Manager",
            "Ship Item": "Warehouse", "Send Invoice": "Finance",
            "Payment Received": "Finance", "Payment Overdue": "Finance",
            "Send Reminder": "Finance", "Write Off": "Controller",
        },
        "planted": {
            "bottlenecks": ["Credit Check", "Payment Received"],
            "rework_loops": [("Approve Order", "Clarify Details")],
        },
    },
    "procurement": {
        "variants": [
            (("Submit Requisition", "Approve Budget", "Select Vendor", "Create PO",
              "Confirm Delivery", "Register Invoice", "Pay Invoice"), 40),
            (("Submit Requisition", "Select Vendor", "Approve Budget", "Create PO",
              "Confirm Delivery", "Register Invoice", "Pay Invoice"), 40),
            (("Submit Requisition", "Approve Budget", "Request Quotes", "Select Vendor",
              "Create PO", "Confirm Delivery", "Register Invoice", "Pay Invoice"), 15),
            (("Submit Requisition", "Approve Budget", "Cancel Requisition"), 5),
        ],
        "waits": {"Submit Requisition": (60, 600), "Approve Budget": (3600, 172800),
                  "Request Quotes": (86400, 432000), "Select Vendor": (86400, 604800),
                  "Create PO": (600, 7200), "Confirm Delivery": (86400, 432000),
                  "Register Invoice": (3600, 86400), "Pay Invoice": (86400, 604800),
                  "Cancel Requisition": (600, 3600)},
        "resources": {"Submit Requisition": "Requester", "Approve Budget": "Controller",
                      "Request Quotes": "Procurement", "Select Vendor": "Procurement",
                      "Create PO": "Procurement", "Confirm Delivery": "Warehouse",
                      "Register Invoice": "Finance", "Pay Invoice": "Finance"},
        "planted": {
            "bottlenecks": ["Select Vendor", "Pay Invoice"],
            "parallel_pair": ("Approve Budget", "Select Vendor"),
        },
    },
    "invoice_ap": {
        "variants": [
            (("Receive Invoice", "Match PO", "Post Invoice", "Schedule Payment",
              "Pay Invoice"), 70),
            (("Receive Invoice", "Match PO", "Resolve Discrepancy", "Match PO",
              "Post Invoice", "Schedule Payment", "Pay Invoice"), 20),
            (("Receive Invoice", "Match PO", "Return to Vendor"), 10),
        ],
        "waits": {"Receive Invoice": (60, 1800), "Match PO": (300, 7200),
                  "Resolve Discrepancy": (3600, 86400), "Return to Vendor": (600, 3600),
                  "Post Invoice": (60, 1800), "Schedule Payment": (3600, 86400),
                  "Pay Invoice": (86400, 432000)},
        "resources": {"Receive Invoice": "AP Clerk", "Match PO": "AP System",
                      "Resolve Discrepancy": "AP Clerk", "Return to Vendor": "AP Clerk",
                      "Post Invoice": "AP System", "Schedule Payment": "Finance",
                      "Pay Invoice": "Finance"},
        "planted": {
            "bottlenecks": ["Pay Invoice", "Resolve Discrepancy"],
            "rework_loops": [("Match PO", "Resolve Discrepancy")],
        },
    },
    "noisy": {
        "variants": [
            (("Start", "Task A", "Task B", "Task C", "End"), 40),
            (("Start", "Task A", "Task C", "End"), 25),
            (("Start", "Task B", "Task A", "Task C", "End"), 20),
            (("Start", "Task A", "Task X", "Task B", "Task C", "End"), 3),
            (("Start", "Task Q", "End"), 2),
        ],
        "waits": {"Start": (1, 10), "Task A": (300, 3600), "Task B": (600, 7200),
                  "Task C": (120, 1800), "Task X": (60, 600), "Task Q": (60, 600),
                  "End": (1, 10)},
        "resources": {"Task A": "Team 1", "Task B": "Team 2", "Task C": "Team 3"},
        "planted": {
            "noise_variants": [("Start", "Task A", "Task X", "Task B", "Task C", "End"),
                               ("Start", "Task Q", "End")],
        },
    },
}


def generate_log(scenario: str = "order_to_cash", num_cases: int = 120, seed: int = 42) -> EventLog:
    """Generate an event log for a scenario, honouring case counts proportionally."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIOS)}")
    spec = SCENARIOS[scenario]
    rng = random.Random(seed)
    variants = spec["variants"]
    total_weight = sum(w for _, w in variants)
    events: List[Event] = []
    base = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
    case_no = 0
    for trace, weight in variants:
        count = round(num_cases * weight / total_weight)
        for _ in range(count):
            case_no += 1
            case_id = f"{scenario[:3].upper()}-{case_no:05d}"
            t = base + timedelta(seconds=rng.uniform(0, 14 * 86400))
            for activity in trace:
                lo, hi = spec["waits"].get(activity, (60, 3600))
                t = t + timedelta(seconds=rng.uniform(lo, hi))
                resource = spec["resources"].get(activity)
                events.append(Event(case_id=case_id, activity=activity, ts=t,
                                    resource=resource, lifecycle=None))
    return EventLog(source=f"synthetic:{scenario}", events=events)


def scenario_ground_truth(scenario: str) -> dict:
    """Planted ground truth for a scenario (bottlenecks, rework, parallelism)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    return SCENARIOS[scenario].get("planted", {})


def save_csv(log: EventLog, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["case_id", "activity", "timestamp", "resource"])
        for ev in sorted(log.events, key=lambda e: (e.case_id, e.ts)):
            writer.writerow([ev.case_id, ev.activity, ev.ts.isoformat(), ev.resource or ""])
    return path


def ensure_benchmark_corpus(out_dir: str | Path = "data/benchmarks",
                            num_cases: int = 150) -> List[Tuple[str, Path]]:
    """Generate (once) the CSV benchmark corpus used by ``research-eval``."""
    out = Path(out_dir)
    paths: List[Tuple[str, Path]] = []
    for scenario in sorted(SCENARIOS):
        target = out / f"{scenario}_log.csv"
        if not target.exists():
            save_csv(generate_log(scenario, num_cases=num_cases), target)
        paths.append((scenario, target))
    return paths
