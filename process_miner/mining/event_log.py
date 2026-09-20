"""Event-log mining: CSV/XES-lite ingestion, statistics, bottleneck scoring.

Accepts flat CSV logs (case id / activity / timestamp [/ resource / lifecycle)
- the shape most ERP/ITSM exports (SAP, ServiceNow, Jira) produce. Computes:

* per-activity frequency, case coverage and queueing times,
* rework (repetition) rates within cases,
* start/end activity sets and top process variants,
* a composite bottleneck score per activity (wait + rework).

Timestamps accept ISO-8601 and common European/US formats.
"""

from __future__ import annotations

import csv
import io
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from process_miner.models import ActivityStats, LogSummary, Variant

from .ingestion_columns import LOG_COLUMNS  # re-export for convenience


class Event(BaseModel):
    case_id: str
    activity: str
    ts: datetime
    resource: Optional[str] = None
    lifecycle: Optional[str] = None


class EventLog(BaseModel):
    source: str = ""
    events: List[Event]

    @property
    def cases(self) -> Dict[str, List[Event]]:
        grouped: Dict[str, List[Event]] = defaultdict(list)
        for e in self.events:
            grouped[e.case_id].append(e)
        return grouped


def parse_timestamp(value: str) -> datetime:
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    fmts = [
        "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
        "%d.%m.%Y %H:%M", "%Y/%m/%d %H:%M:%S",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(v, f)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Unparseable timestamp: {value!r}")


def load_log(csv_text: str, source: str = "") -> EventLog:
    reader = csv.reader(io.StringIO(csv_text.strip()))
    rows = [r for r in reader if r and any(c.strip() for c in r)]
    if len(rows) < 2:
        raise ValueError("Event log needs a header row plus at least one event")
    header = [h.strip().lower() for h in rows[0]]

    def col(candidates: set) -> Optional[int]:
        for i, h in enumerate(header):
            if h in candidates:
                return i
        return None

    i_case = col(LOG_COLUMNS["case_id"])
    i_act = col(LOG_COLUMNS["activity"])
    i_ts = col(LOG_COLUMNS["timestamp"])
    i_res = col(LOG_COLUMNS["resource"])
    i_life = col(LOG_COLUMNS["lifecycle"])
    if i_case is None or i_act is None or i_ts is None:
        raise ValueError(f"Missing required columns in header {header}")

    events: List[Event] = []
    for lineno, row in enumerate(rows[1:], start=2):
        if len(row) <= max(i_case, i_act, i_ts):
            continue
        try:
            ts = parse_timestamp(row[i_ts])
        except ValueError:
            continue  # skip rows with corrupt timestamps rather than failing the run
        events.append(
            Event(
                case_id=row[i_case].strip(),
                activity=row[i_act].strip(),
                ts=ts,
                resource=row[i_res].strip() if i_res is not None and i_res < len(row) else None,
                lifecycle=row[i_life].strip().lower() if i_life is not None and i_life < len(row) else None,
            )
        )
    if not events:
        raise ValueError("No parsable events found in log")
    return EventLog(source=source, events=events)


def compute_summary(log: EventLog) -> LogSummary:
    cases = log.cases
    freq: Counter = Counter()
    case_cover: Counter = Counter()
    waits: Dict[str, List[float]] = defaultdict(list)
    rework_counts: Dict[str, int] = defaultdict(int)
    variants: Counter = Counter()
    start_acts: Counter = Counter()
    end_acts: Counter = Counter()

    for case_id, evs in cases.items():
        evs_sorted = sorted(evs, key=lambda e: e.ts)
        seq = [e.activity for e in evs_sorted]
        variants[tuple(seq)] += 1
        if seq:
            start_acts[seq[0]] += 1
            end_acts[seq[-1]] += 1
        seen_in_case: Counter = Counter()
        for e in evs_sorted:
            freq[e.activity] += 1
            seen_in_case[e.activity] += 1
        for act, count in seen_in_case.items():
            case_cover[act] += 1
            if count > 1:
                rework_counts[act] += count - 1
        for prev, cur in zip(evs_sorted, evs_sorted[1:]):
            gap = (cur.ts - prev.ts).total_seconds() / 60.0
            if gap > 0:
                waits[cur.activity].append(gap)

    n_cases = len(cases)
    total_wait = {a: sum(v) for a, v in waits.items()}
    stats: List[ActivityStats] = []
    for act, f in freq.items():
        w = waits.get(act, [])
        median_w = statistics.median(w) if w else 0.0
        mean_w = statistics.fmean(w) if w else 0.0
        rework = rework_counts.get(act, 0)
        rework_rate = rework / f if f else 0.0
        stats.append(
            ActivityStats(
                name=act,
                frequency=f,
                cases=case_cover.get(act, 0),
                median_wait_minutes=round(median_w, 1),
                mean_wait_minutes=round(mean_w, 1),
                total_wait_minutes=round(total_wait.get(act, 0.0), 1),
                rework_count=rework,
                rework_rate=round(rework_rate, 3),
            )
        )

    _score_bottlenecks(stats)
    stats.sort(key=lambda a: a.bottleneck_score, reverse=True)

    top_variants = sorted(variants.items(), key=lambda kv: kv[1], reverse=True)[:5]
    variant_models = [
        Variant(sequence=list(seq), count=count, share=round(count / n_cases, 3) if n_cases else 0.0)
        for seq, count in top_variants
    ]

    return LogSummary(
        source=log.source,
        cases=n_cases,
        events=len(log.events),
        activities_count=len(stats),
        activities=stats,
        variants=variant_models,
        top_bottlenecks=[a.name for a in stats[:3] if a.bottleneck_score > 0],
        start_activities=[a for a, _ in start_acts.most_common()],
        end_activities=[a for a, _ in end_acts.most_common()],
    )


def _score_bottlenecks(stats: List[ActivityStats]) -> None:
    """Composite score: 70% normalised median wait + 30% rework rate."""
    if not stats:
        return
    max_wait = max((a.median_wait_minutes for a in stats), default=0.0) or 1.0
    for a in stats:
        wait_component = min(1.0, a.median_wait_minutes / max_wait)
        a.bottleneck_score = round(0.7 * wait_component + 0.3 * min(1.0, a.rework_rate), 3)


def directly_follows(log: EventLog) -> Tuple[Counter, Counter, Counter]:
    """Return (dfg edge counts, start activity counts, end activity counts)."""
    dfg: Counter = Counter()
    starts: Counter = Counter()
    ends: Counter = Counter()
    for evs in log.cases.values():
        seq = [e.activity for e in sorted(evs, key=lambda e: e.ts)]
        if not seq:
            continue
        starts[seq[0]] += 1
        ends[seq[-1]] += 1
        for a, b in zip(seq, seq[1:]):
            dfg[(a, b)] += 1
    return dfg, starts, ends
