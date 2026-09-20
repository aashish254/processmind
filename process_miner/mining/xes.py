"""XES (eXtensible Event Log) support — load and write the IEEE XES standard.

The loader understands the common XES shape (namespaced or not):

```xml
<log>
  <trace>
    <string key="concept:name" value="Case 1"/>
    <event>
      <string key="concept:name" value="Receive Application"/>
      <date key="time:timestamp" value="2026-01-05T08:12:00.000+00:00"/>
      <string key="org:resource" value="Vendor Portal"/>
    </event>
  </trace>
</log>
```

Attribute lookup is alias-based (concept:name / case:id, time:timestamp / time,
org:resource / resource, lifecycle:transition) so files exported by ProM,
PM4Py, Celonis and DisCOVER all load. The writer emits a minimal valid XES
document for round-tripping.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel

from process_miner.mining.event_log import Event, EventLog, load_log, parse_timestamp

_CASE_KEYS = {"concept:name", "case:id", "case:id:concept:name"}
_ACTIVITY_KEYS = {"concept:name"}
_TIME_KEYS = {"time:timestamp", "time", "complete time"}
_RESOURCE_KEYS = {"org:resource", "resource"}
_LIFECYCLE_KEYS = {"lifecycle:transition", "lifecycle", "concept:instance"}


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _attrs(element) -> Dict[str, str]:
    """Collect key/value pairs from XES attribute children of an element."""
    out: Dict[str, str] = {}
    for child in element:
        tag = _local(child.tag)
        if tag in {"string", "date", "int", "float", "boolean", "id"}:
            key = child.get("key")
            if key:
                out[key.lower()] = child.get("value", "")
    return out


def _pick(attrs: Dict[str, str], keys: set) -> Optional[str]:
    for k in keys:
        if k in attrs and attrs[k] != "":
            return attrs[k]
    return None


def load_xes(text: str, source: str = "") -> EventLog:
    try:
        root = ET.fromstring(text.strip())
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XES XML: {exc}") from exc
    if _local(root.tag) != "log":
        raise ValueError(f"Expected a <log> root element, got <{_local(root.tag)}>")

    events: List[Event] = []
    for t_idx, trace in enumerate((el for el in root if _local(el.tag) == "trace"), start=1):
        trace_attrs = _attrs(trace)
        case_id = _pick(trace_attrs, _CASE_KEYS) or f"case_{t_idx}"
        for event in (el for el in trace if _local(el.tag) == "event"):
            attrs = _attrs(event)
            activity = _pick(attrs, _ACTIVITY_KEYS)
            ts_raw = _pick(attrs, _TIME_KEYS)
            if not activity or not ts_raw:
                continue  # events without name/timestamp cannot be mined
            try:
                ts = parse_timestamp(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            resource = _pick(attrs, _RESOURCE_KEYS)
            lifecycle = _pick(attrs, _LIFECYCLE_KEYS)
            events.append(
                Event(
                    case_id=case_id,
                    activity=activity,
                    ts=ts,
                    resource=resource,
                    lifecycle=lifecycle,
                )
            )
    if not events:
        raise ValueError("No parsable events found in XES log")
    return EventLog(source=source, events=events)


def to_xes(log: EventLog, log_name: str = "ProcessMind export") -> str:
    """Serialize an EventLog as a minimal valid XES document."""

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    cases: Dict[str, List[Event]] = {}
    for e in sorted(log.events, key=lambda e: (e.case_id, e.ts)):
        cases.setdefault(e.case_id, []).append(e)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<log xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '     xsi:schemaLocation="http://www.xes-standard.org/ xes.xsd"',
        '     version="2.0">',
        f'  <string key="concept:name" value="{esc(log_name)}"/>',
    ]
    for case_id, evs in cases.items():
        lines.append('  <trace>')
        lines.append(f'    <string key="concept:name" value="{esc(case_id)}"/>')
        for e in evs:
            ts = e.ts if e.ts.tzinfo else e.ts.replace(tzinfo=timezone.utc)
            lines.append('    <event>')
            lines.append(f'      <string key="concept:name" value="{esc(e.activity)}"/>')
            lines.append(f'      <date key="time:timestamp" value="{ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]}+00:00"/>')
            if e.resource:
                lines.append(f'      <string key="org:resource" value="{esc(e.resource)}"/>')
            if e.lifecycle:
                lines.append(f'      <string key="lifecycle:transition" value="{esc(e.lifecycle)}"/>')
            lines.append('    </event>')
        lines.append('  </trace>')
    lines.append('</log>')
    return "\n".join(lines) + "\n"


def load_event_log(text: str, source: str = "") -> EventLog:
    """Dispatch on content: XES (XML) or CSV."""
    if text.lstrip().startswith("<"):
        return load_xes(text, source)
    return load_log(text, source)
