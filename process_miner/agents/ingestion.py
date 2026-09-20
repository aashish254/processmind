"""Ingestion Agent.

Normalises raw inputs into an :class:`IngestedDocument`:

* reads files (.md / .txt / .csv) or accepts raw text,
* parses a lightweight metadata header (``Process:`` / ``Roles:`` / ...),
* strips markdown and joins wrapped lines,
* segments the narrative into candidate process steps (sentences),
* skips non-flow boilerplate sections (Purpose, Scope, Revision history...),
* detects event-log CSVs and routes them to the mining pathway.

The output is deliberately clean and deterministic so that both the LLM
modeler and the offline rule parser work from the same representation -
this is what makes the two extractors comparable in the evaluation harness.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from process_miner.models import DocumentStats, IngestedDocument, Section
from process_miner.mining.ingestion_columns import LOG_COLUMNS

METADATA_KEYS = {
    "process": "process",
    "process name": "process",
    "roles": "roles",
    "actors": "roles",
    "roles/actors": "roles",
    "domain": "domain",
    "system": "system",
    "systems": "system",
    "owner": "owner",
    "version": "version",
}

BOILERPLATE_SECTIONS = {
    "purpose",
    "scope",
    "objectives",
    "objective",
    "definitions",
    "definitions and acronyms",
    "references",
    "revision history",
    "document control",
    "appendix",
    "glossary",
    "controls",
    "control activities",
    "exceptions",
    "escalation",
    "sla",
    "kpis",
    "metrics",
    "notes",
    "roles and responsibilities",
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.*)$")
_LIST_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_META_LINE = re.compile(r"^\s*([A-Za-z /]+?)\s*:\s*(.+?)\s*$")


def _looks_like_sentence(line: str) -> bool:
    """Heuristic: metadata lines don't end with sentence punctuation."""
    s = line.strip()
    return s.endswith((".", "!", "?"))


class IngestionAgent:
    name = "ingestion"

    def run(self, source: str, doc_id: Optional[str] = None, kind: Optional[str] = None) -> IngestedDocument:
        """Ingest a file path, raw text, or CSV content.

        ``source`` is treated as a path if it points at an existing file,
        otherwise as raw document text.
        """
        path = None
        if "\n" not in source and len(source) < 1024:
            try:
                candidate = Path(source)
                if candidate.is_file():
                    path = candidate
            except OSError:
                path = None
        if path is not None:
            text = path.read_text(encoding="utf-8", errors="replace")
            name = path.stem.replace("_", " ").replace("-", " ").title()
            source_path = str(path)
            suffix = path.suffix.lower()
            if kind is None:
                kind = "log" if suffix in (".csv", ".xes") else "sop"
        else:
            text = source
            name = "Ad hoc document"
            source_path = None
            if kind is None:
                kind = "log" if self._looks_like_log_text(text) else "sop"

        doc_id = doc_id or re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "doc"

        if kind == "log":
            return self._ingest_log(text, doc_id, name, source_path)

        return self._ingest_sop(text, doc_id, name, source_path)

    # -- SOP pathway --------------------------------------------------------

    def _ingest_sop(self, text: str, doc_id: str, name: str, source_path: Optional[str]) -> IngestedDocument:
        metadata, body_lines = self._extract_metadata(text)
        process_name = metadata.get("process") or name
        sections, steps = self._segment(body_lines)

        words = len(re.findall(r"\S+", text))
        sentences = sum(len(_SENTENCE_SPLIT.split(re.sub(r"\s+", " ", s.body).strip())) for s in sections) or len(steps)

        return IngestedDocument(
            doc_id=doc_id,
            name=process_name,
            kind="sop",
            text=text,
            sections=sections,
            steps=steps,
            metadata=metadata,
            stats=DocumentStats(words=words, sentences=sentences, steps=len(steps)),
            source_path=source_path,
        )

    def _extract_metadata(self, text: str) -> Tuple[Dict[str, str], List[str]]:
        """Read ``Key: value`` metadata lines from the document head."""
        metadata: Dict[str, str] = {}
        lines = text.splitlines()
        body_start = 0
        for i, line in enumerate(lines[:12]):
            stripped = line.strip()
            if not stripped:
                if metadata:
                    body_start = i + 1
                    continue
                continue
            if stripped in {"---", "***", "___"}:
                body_start = i + 1
                continue
            m = _META_LINE.match(stripped)
            if not m:
                mhead = _MD_HEADING.match(line)
                if mhead:
                    title = mhead.group(1).strip().lower()
                    if title in BOILERPLATE_SECTIONS:
                        body_start = i  # let the segmenter own this section
                        break
                    body_start = i + 1
                    continue
                body_start = i
                break
            key = m.group(1).lower().strip()
            if key in METADATA_KEYS and not _looks_like_sentence(stripped):
                canonical = METADATA_KEYS[key]
                metadata[canonical] = m.group(2).strip()
                body_start = i + 1
            else:
                body_start = i
                break
        return metadata, lines[body_start:]

    def _segment(self, lines: List[str]) -> Tuple[List[Section], List[str]]:
        """Group lines into sections; pull candidate process steps."""
        sections: List[Section] = []
        steps: List[str] = []
        current = Section(title="Overview")
        buffer: List[str] = []

        def flush() -> None:
            if buffer:
                current.body = " ".join(buffer).strip()
                if not current.body:
                    current.body = ""
            sections.append(current)

        for raw in lines:
            heading = _MD_HEADING.match(raw)
            if heading:
                flush()
                buffer = []
                current = Section(title=heading.group(1).strip() or "Untitled")
                continue
            line = _LIST_PREFIX.sub("", raw.rstrip())
            if not line.strip():
                continue
            if self._is_section_header(line) and not heading:
                flush()
                buffer = []
                current = Section(title=line.strip().rstrip(":"))
                continue
            buffer.append(line.strip())

            if self._in_boilerplate(current.title):
                continue
            for sentence in self._sentences(line):
                if sentence.strip():
                    steps.append(sentence.strip())
        flush()

        # collapse wrapped fragments: a step not ending in punctuation absorbs the next
        merged: List[str] = []
        for s in steps:
            if merged and not re.search(r"[.!?:;]$",
                                        merged[-1]) and s[:1].islower():
                merged[-1] = f"{merged[-1]} {s}"
            else:
                merged.append(s)
        return sections, merged

    @staticmethod
    def _sentences(line: str) -> List[str]:
        if not line.strip():
            return []
        if _SENTENCE_SPLIT.search(line.strip() + " ") is None and len(line) < 400:
            return [line.strip()]
        parts = _SENTENCE_SPLIT.split(re.sub(r"\s+", " ", line).strip())
        return [p for p in parts if p.strip()]

    @staticmethod
    def _is_section_header(line: str) -> bool:
        stripped = line.strip()
        return (
            3 <= len(stripped) <= 60
            and stripped.endswith(":")
            and not _looks_like_sentence(stripped)
        )

    @staticmethod
    def _in_boilerplate(title: str) -> bool:
        return title.strip().lower() in BOILERPLATE_SECTIONS

    # -- event-log pathway ---------------------------------------------------

    def _ingest_log(self, text: str, doc_id: str, name: str, source_path: Optional[str]) -> IngestedDocument:
        if text.lstrip().startswith("<"):
            from process_miner.mining.xes import load_xes

            xes = load_xes(text, source=source_path or name)
            return IngestedDocument(
                doc_id=doc_id,
                name=name,
                kind="log",
                text=text,
                metadata={"format": "xes", "events": str(len(xes.events))},
                stats=DocumentStats(words=0, sentences=0, steps=len(xes.events)),
                source_path=source_path,
            )
        header, n_rows = self._validate_log(text)
        return IngestedDocument(
            doc_id=doc_id,
            name=name,
            kind="log",
            text=text,
            metadata={"format": "csv", "columns": ",".join(header)},
            stats=DocumentStats(words=0, sentences=0, steps=n_rows),
            source_path=source_path,
        )

    @staticmethod
    def _looks_like_log_text(text: str) -> bool:
        """XES XML or event-log CSV fingerprint; raises ValueError on malformed logs."""
        stripped = text.strip()
        if stripped.startswith("<"):
            if "<trace" not in stripped:
                return False
            from process_miner.mining.xes import load_xes

            load_xes(stripped)  # validates; raises on malformed XES
            return True
        return IngestionAgent._looks_like_csv(stripped)

    @staticmethod
    def _looks_like_csv(text: str) -> bool:
        """True when the first line smells like an event-log header (raises on bad logs)."""
        first = text.strip().splitlines()[0].lower() if text.strip() else ""
        if "," not in first:
            return False
        cells = {c.strip() for c in first.split(",")}
        known = LOG_COLUMNS["case_id"] | LOG_COLUMNS["activity"] | LOG_COLUMNS["timestamp"]
        if cells & known:
            IngestionAgent._validate_log(text)  # raises ValueError on malformed logs
            return True
        return False

    @staticmethod
    def _validate_log(text: str) -> Tuple[List[str], int]:
        reader = csv.reader(io.StringIO(text.strip()))
        rows = [r for r in reader if r and any(c.strip() for c in r)]
        if len(rows) < 2:
            raise ValueError("Event log CSV needs a header row and at least one data row")
        header = [h.strip().lower() for h in rows[0]]
        has_case = any(h in LOG_COLUMNS["case_id"] for h in header)
        has_activity = any(h in LOG_COLUMNS["activity"] for h in header)
        has_time = any(h in LOG_COLUMNS["timestamp"] for h in header)
        if not (has_case and has_activity and has_time):
            raise ValueError(
                "Event log CSV must contain case id, activity and timestamp columns; "
                f"got {header}"
            )
        return header, len(rows) - 1
