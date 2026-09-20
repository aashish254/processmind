"""Generate realistic synthetic event logs for the two enterprise scenarios.

Deterministic (seeded) so the checked-in CSVs in inputs/ are reproducible.
The logs deliberately contain:

* a long queueing bottleneck ("Await Vendor Documents" / "Await User Response"),
* a rework loop ("Validate Documents" / "Apply Fix" repeated),
* parallel-permitted but sequential-executed approvals,
* a realistic long-tail of activity timestamps.

Usage: python scripts/generate_logs.py [--out inputs]
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


def _ts(base: datetime, minutes: int) -> str:
    return (base + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")


def generate_vendor_onboarding(n_cases: int = 250, seed: int = 42) -> list:
    rng = random.Random(seed)
    rows = []
    start = datetime(2026, 1, 5, 8, 0)
    for c in range(1, n_cases + 1):
        case = f"VND-{c:04d}"
        t = start + timedelta(minutes=rng.randint(0, 60 * 24 * 60))  # spread over ~60 days
        incomplete_docs = rng.random() < 0.30

        rows.append([case, "Receive Application", _ts(t, 0), "Vendor Portal"])
        t = t + timedelta(minutes=rng.randint(2, 10))
        rows.append([case, "Verify Documents", _ts(t, 0), "Vendor Portal"])
        if incomplete_docs:
            t = t + timedelta(minutes=rng.randint(1 * 24 * 60, 6 * 24 * 60))  # vendor takes days to resubmit
            rows.append([case, "Await Vendor Documents", _ts(t, 0), "Vendor Portal"])
            t = t + timedelta(minutes=rng.randint(2, 10))
            rows.append([case, "Verify Documents", _ts(t, 0), "Vendor Portal"])
        if rng.random() < 0.08:  # occasional second rework loop
            t = t + timedelta(minutes=rng.randint(1 * 24 * 60, 3 * 24 * 60))
            rows.append([case, "Await Vendor Documents", _ts(t, 0), "Vendor Portal"])
            t = t + timedelta(minutes=rng.randint(2, 10))
            rows.append([case, "Verify Documents", _ts(t, 0), "Vendor Portal"])

        t = t + timedelta(minutes=rng.randint(30, 8 * 60))
        rows.append([case, "Review Application", _ts(t, 0), "Procurement Officer"])

        # Screening and risk assessment are documented as PARALLEL work in the SOP;
        # teams execute them in either order (planted parallelism for AND discovery).
        w1 = rng.randint(2 * 24 * 60, 8 * 24 * 60)  # first-executed queue wait
        w2 = rng.randint(1 * 24 * 60, 6 * 24 * 60)  # second-executed queue wait
        if rng.random() < 0.5:
            screening_ts = _ts(t + timedelta(minutes=w1), 0)
            risk_ts = _ts(t + timedelta(minutes=w1 + w2), 0)
            first, second = "Compliance Screening", "Financial Risk Assessment"
        else:
            risk_ts = _ts(t + timedelta(minutes=w1), 0)
            screening_ts = _ts(t + timedelta(minutes=w1 + w2), 0)
            first, second = "Financial Risk Assessment", "Compliance Screening"
        rows.append([case, first, screening_ts if first == "Compliance Screening" else risk_ts, "Compliance Team" if first == "Compliance Screening" else "Finance Manager"])
        rows.append([case, second, screening_ts if second == "Compliance Screening" else risk_ts, "Compliance Team" if second == "Compliance Screening" else "Finance Manager"])
        t = t + timedelta(minutes=w1 + w2)

        t = t + timedelta(minutes=rng.randint(4 * 60, 3 * 24 * 60))  # approval wait
        approved = rng.random() > 0.12
        rows.append([case, "Approve Vendor", _ts(t, 0), "Finance Manager"])
        if not approved:
            t = t + timedelta(minutes=rng.randint(10, 60))
            rows.append([case, "Reject Application", _ts(t, 0), "Procurement Officer"])
            continue
        t = t + timedelta(minutes=rng.randint(5, 60))
        rows.append([case, "Create Vendor Record", _ts(t, 0), "ERP System"])
        t = t + timedelta(minutes=rng.randint(2, 30))
        rows.append([case, "Send Welcome Pack", _ts(t, 0), "ERP System"])
        t = t + timedelta(minutes=rng.randint(2, 30))
        rows.append([case, "Archive Application", _ts(t, 0), "ERP System"])
    return rows


def generate_it_incidents(n_cases: int = 300, seed: int = 7) -> list:
    rng = random.Random(seed)
    rows = []
    start = datetime(2026, 2, 1, 0, 0)
    for c in range(1, n_cases + 1):
        case = f"INC-{c:04d}"
        t = start + timedelta(minutes=rng.randint(0, 60 * 24 * 28))
        rows.append([case, "Log Incident", _ts(t, 0), "Service Desk Agent"])
        t = t + timedelta(minutes=rng.randint(5, 90))
        rows.append([case, "Categorize Incident", _ts(t, 0), "ITSM Platform"])
        t = t + timedelta(minutes=rng.randint(2, 20))
        rows.append([case, "Assign Priority", _ts(t, 0), "ITSM Platform"])
        t = t + timedelta(minutes=rng.randint(10, 6 * 60))
        rows.append([case, "Investigate Issue", _ts(t, 0), "Service Desk Agent"])

        major = rng.random() < 0.18
        if major:
            t = t + timedelta(minutes=rng.randint(15, 120))
            rows.append([case, "Open War Room", _ts(t, 0), "Incident Manager"])
        else:
            t = t + timedelta(minutes=rng.randint(15, 240))
            rows.append([case, "Apply Standard Fix", _ts(t, 0), "Service Desk Agent"])

        t = t + timedelta(minutes=rng.randint(10, 180))
        rows.append([case, "Restore Service", _ts(t, 0), "Network Team"])

        fix_worked = rng.random() > 0.22
        if not fix_worked:
            t = t + timedelta(minutes=rng.randint(30, 12 * 60))
            rows.append([case, "Escalate Ticket", _ts(t, 0), "Service Desk Agent"])
            t = t + timedelta(minutes=rng.randint(30, 8 * 60))
            rows.append([case, "Investigate Issue", _ts(t, 0), "Incident Manager"])
            t = t + timedelta(minutes=rng.randint(20, 240))
            rows.append([case, "Apply Standard Fix", _ts(t, 0), "Service Desk Agent"])
            t = t + timedelta(minutes=rng.randint(10, 120))
            rows.append([case, "Restore Service", _ts(t, 0), "Network Team"])

        t = t + timedelta(minutes=rng.randint(30, 26 * 60))  # the planted queueing bottleneck: user response
        rows.append([case, "Await User Response", _ts(t, 0), "End User"])
        t = t + timedelta(minutes=rng.randint(5, 60))
        rows.append([case, "Confirm Fix", _ts(t, 0), "End User"])
        t = t + timedelta(minutes=rng.randint(5, 4 * 60))
        rows.append([case, "Close Ticket", _ts(t, 0), "Service Desk Agent"])
        t = t + timedelta(minutes=rng.randint(1, 60))
        rows.append([case, "Send Satisfaction Survey", _ts(t, 0), "ITSM Platform"])
    return rows


HEADER = ["case_id", "activity", "timestamp", "resource"]


def write_csv(rows: list, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="inputs")
    parser.add_argument("--vendor-cases", type=int, default=250)
    parser.add_argument("--it-cases", type=int, default=300)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(generate_vendor_onboarding(args.vendor_cases), out / "vendor_onboarding_events.csv")
    write_csv(generate_it_incidents(args.it_cases), out / "it_incident_events.csv")
    print(f"wrote {out / 'vendor_onboarding_events.csv'} ({args.vendor_cases} cases)")
    print(f"wrote {out / 'it_incident_events.csv'} ({args.it_cases} cases)")


if __name__ == "__main__":
    main()
