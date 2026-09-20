"""Offline Process Modeler - deterministic rule-based extraction.

Converts cleaned SOP steps into a :class:`ProcessModel` without any LLM.
It is the *baseline extractor* in the research evaluation (compare with the
LLM agent and the gold annotations) and the guaranteed fallback whenever no
LLM provider is configured.

Technique (documented in docs/RESEARCH.md):
* discourse-marker-driven control-flow reconstruction over the step stream,
* a frontier state machine that attaches each new step to the open ends of
  the graph, with an explicit stack for conditional branches,
* negation-aware decision continuation ("If complete, ..." after
  "If incomplete, ..." continues the No branch instead of nesting),
* actor (lane) detection from the SOP role registry plus generic role grammar,
* task-type / duration / automation inference from lexical cues.

Limitations (by design, they motivate the LLM agent): the parser trusts
explicit markers ("if", "otherwise", "while", "in both cases", "returns to"),
does not resolve coreferences, and models each sentence at face value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from process_miner.models import (
    IngestedDocument,
    NodeType,
    ProcessModel,
    TaskKind,
)

# ---------------------------------------------------------------------------
# Lexical resources
# ---------------------------------------------------------------------------

STOPWORDS = {"the", "a", "an", "of", "to", "and", "is", "are", "for", "in", "on"}

SYSTEM_ACTOR_WORDS = {
    "system", "portal", "erp", "crm", "api", "robot", "rpa", "engine",
    "platform", "bot", "tool", "middleware", "server", "scheduler", "itsm",
}

SEND_VERBS = {"sends", "emails", "notifies", "dispatches", "alerts", "informs", "messages", "forwards"}
RECEIVE_VERBS = {"receives", "acknowledges", "accepts"}
APPROVE_VERBS = {"approves", "authorizes", "authorises", "signs", "ratifies", "grants"}
REVIEW_VERBS = {"reviews", "assesses", "audits", "screens", "evaluates", "examines", "analyzes", "analyses", "investigates"}
CHECK_VERBS = {"validates", "verifies", "checks", "inspects", "confirms", "reconciles", "tests", "monitors"}
CREATE_VERBS = {"creates", "records", "enters", "logs", "registers", "updates", "submits", "fills", "uploads", "files"}

# base (imperative) forms used for "and"-splitting and name normalisation
VERB_BASES = {
    "send", "email", "notify", "dispatch", "alert", "inform", "message", "forward",
    "receive", "acknowledge", "accept",
    "approve", "authorize", "authorise", "sign", "ratify", "grant",
    "review", "assess", "audit", "screen", "evaluate", "examine", "analyze", "analyse", "investigate",
    "validate", "verify", "check", "inspect", "confirm", "reconcile", "test", "monitor",
    "create", "record", "enter", "log", "register", "update", "submit", "fill", "upload", "file",
    "perform", "prepare", "provide", "generate", "assign", "escalate", "resolve", "diagnose",
    "categorize", "categorise", "prioritize", "prioritise", "reopen", "respond", "document",
    "close", "archive", "onboard", "schedule", "request", "collect", "gather", "complete",
    "issue", "reject", "order", "ship", "deliver", "invoice", "pay", "reimburse", "block",
    "cancel", "resubmit", "repeat", "restart", "route", "move", "proceed", "continue",
    "transfer", "await", "wait", "contact", "advise", "decide", "determine", "classify",
    "prioritize", "communicate", "obtain", "store", "retain", "trigger", "initiate", "execute",
    "apply", "open", "conduct", "carry", "engage", "handle", "process", "manage", "allocate",
    "restore", "coordinate", "verify", "survey", "remind", "track", "schedule",
}

ALL_VERB_FORMS = set().union(
    SEND_VERBS, RECEIVE_VERBS, APPROVE_VERBS, REVIEW_VERBS, CHECK_VERBS, CREATE_VERBS
)
VERBISH_SKIP = {"the", "a", "an", "then", "next", "finally", "also", "subsequently", "immediately",
                "first", "lastly", "it", "they", "he", "she", "there", "this", "that", "however"}
NON_VERBS = {"is", "are", "was", "were", "has", "have", "had", "does", "do", "will", "shall", "must"}

AUTO_CUES = ("automatically", "auto-", "automated", "system-generated", "without human")

PARTICIPLE_TO_VERB = {
    "rejected": "Reject", "approved": "Approve", "created": "Create",
    "updated": "Update", "closed": "Close", "archived": "Archive",
    "sent": "Send", "recorded": "Record", "completed": "Complete",
    "escalated": "Escalate", "resolved": "Resolve", "assigned": "Assign",
}

GENERIC_ROLE_RE = re.compile(
    r"\b(?:The\s+|the\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+"
    r"(?:Team|Manager|Officer|Analyst|Specialist|Coordinator|Department|"
    r"Supervisor|Engineer|Technician|Lead|Administrator|Approver|Desk|Group))\b"
)

MARKER_PREFIXES = [
    r"^in both cases,?\s*",
    r"^in any case,?\s*",
    r"^either way,?\s*",
    r"^regardless of (?:the )?(?:outcome|result),?\s*",
    r"^otherwise,?\s*",
    r"^for [^,]{3,40},\s*",
    r"^in case of [^,]{3,40},\s*",
    r"^(?:finally|next|then|subsequently|afterwards|afterward|meanwhile|additionally|also),\s*",
    r"^(?:once|after|upon|when|while)\s+[^,]+,\s*",
]

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _stem(token: str) -> str:
    for suf in ("ation", "ition", "tion", "sion", "ing", "ised", "ized", "ed", "es", "ly", "s"):
        if token.endswith(suf) and len(token) - len(suf) >= 3:
            return token[: -len(suf)]
    return token


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def _token_similarity(frag_tokens: List[str], name: str) -> float:
    name_tokens = _tokens(name)
    if not frag_tokens or not name_tokens:
        return 0.0
    hits = 0
    for ft in frag_tokens:
        fs = _stem(ft)
        for nt in name_tokens:
            ns = _stem(nt)
            if fs == ns or (len(fs) >= 4 and len(ns) >= 4 and fs.startswith(ns[:4]) and ns.startswith(fs[:4])):
                hits += 1
                break
    return hits / max(len(frag_tokens), len(name_tokens))


def _deconjugate_verb(word: str) -> str:
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if re.search(r"(ches|shes|xes|oes|sses)$", w) and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        return w[:-1]
    return w


def _verbish(word: str) -> bool:
    w = word.lower().strip(",.;:!")
    if w in NON_VERBS:
        return False
    stem = _stem(w)
    candidates = {w, _deconjugate_verb(w), stem, stem + "e"}
    return any(c in VERB_BASES for c in candidates)


def _strip_prefixes(text: str) -> str:
    changed = True
    while changed:
        changed = False
        for pat in MARKER_PREFIXES:
            new = re.sub(pat, "", text, flags=re.I)
            if new != text:
                text = new
                changed = True
    return text.strip()


def _task_name(clause: str, actor: Optional[str]) -> str:
    """Normalise a clause into an imperative-style task name."""
    text = clause.strip().rstrip(".;:,")
    text = _strip_prefixes(text)
    # drop leading role mention when it matches the detected actor
    if actor:
        esc = re.escape(actor.lower())
        text = re.sub(rf"^(?:the\s+)?{esc}\s+(?:then\s+)?", "", text, flags=re.I)
    m = GENERIC_ROLE_RE.match(text)
    if m and m.start() == 0:
        text = text[m.end():].strip()
        text = re.sub(r"^(?:then\s+|automatically\s+|manually\s+)", "", text, flags=re.I)
    # passive voice -> imperative ("the application is rejected" -> "Reject the application")
    pm = re.match(r"^(?:the\s+)?(.+?)\s+(?:is|are|was|were)\s+(\w+)\s*(?:by\s+.+)?$", text, flags=re.I)
    if pm and pm.group(2).lower() in PARTICIPLE_TO_VERB:
        return f"{PARTICIPLE_TO_VERB[pm.group(2).lower()]} {pm.group(1).lower()}"
    words = text.split()
    if not words:
        return "Perform step"
    if words[0].lower() == "the" and len(words) > 1:
        words = words[1:]
    # skip a leading actor noun when the next word is the verb
    if len(words) > 1 and not _verbish(words[0]) and _verbish(words[1]):
        words = words[1:]
    words[0] = _deconjugate_verb(words[0]).capitalize()
    return " ".join(words) or "Perform step"


def _first_verb(clause: str) -> str:
    words = re.findall(r"[a-zA-Z]+", clause)
    for w in words:
        if w.lower() not in VERBISH_SKIP:
            return w.lower()
    return ""


def _split_clauses(text: str) -> List[str]:
    """Split a step into sequential action clauses ('then', ';', verb-initial 'and')."""
    parts = re.split(r"\s+then\s+|;\s*|\s+and\s+then\s+", text)
    out: List[str] = []
    for part in parts:
        pieces = re.split(r"\s+and\s+", part)
        acc = pieces[0]
        for piece in pieces[1:]:
            first = re.match(r"^[A-Za-z]+", piece.strip())
            if first and _verbish(first.group(0)):
                out.append(acc.strip())
                acc = piece
            else:
                acc += " and " + piece
        out.append(acc.strip())
    return [o for o in out if o.strip()]


def _tidy_tail(text: str) -> str:
    """Drop dangling connectors left after suffix truncation ('... and the process')."""
    words = text.split()
    drop = {"and", "then", "or", "the", "a", "an", "to", "with", "for", "process", "step"}
    while words and words[-1].lower().strip(",.;:") in drop:
        words.pop()
    return " ".join(words)


def _condition_tokens(cond: str) -> List[str]:
    return [t for t in re.findall(r"[a-z]+", cond.lower()) if t not in STOPWORDS]


def _negates(c1: str, c2: str) -> bool:
    """True when two conditions are affirmative/negative counterparts."""
    t1, t2 = _condition_tokens(c1), _condition_tokens(c2)
    if not t1 or len(t1) != len(t2):
        return False
    diff = 0
    for a, b in zip(t1, t2):
        if a == b:
            continue
        if len(a) >= 4 and len(b) >= 4 and (a.endswith(b) or b.endswith(a) or a.startswith(b) or b.startswith(a)):
            diff += 1
        else:
            return False
    return diff >= 1


@dataclass
class _GatewayCtx:
    gw_id: str
    condition: str
    yes_frontier: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    no_frontier: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    yes_filled: bool = False
    no_filled: bool = False
    yes_terminated: bool = False  # branch ends in a rework loop (no join expected)
    no_terminated: bool = False


@dataclass
class ParseResult:
    model: ProcessModel
    warnings: List[str]


# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------


class OfflineProcessParser:
    """Rule-based SOP -> ProcessModel extractor (no network, deterministic)."""

    def parse(self, doc: IngestedDocument) -> ParseResult:
        roles = [r.strip() for r in doc.metadata.get("roles", "").split(",") if r.strip()]
        model = ProcessModel(
            id=f"pm_{doc.doc_id}",
            name=doc.name,
            description=f"Extracted from {doc.source_path or 'ad hoc text'}",
            metadata={"extractor": "offline-rules", "doc_id": doc.doc_id, **doc.metadata},
        )
        start = model.add_node(
            self._start_event_name(doc),
            NodeType.START_EVENT,
            event_kind="message",
            source_text=doc.steps[0] if doc.steps else "",
        )
        frontier: List[Tuple[str, Optional[str]]] = [(start.id, None)]
        open_gws: List[_GatewayCtx] = []
        current_actor: Optional[str] = None
        warnings: List[str] = []
        self._rework_joins: Dict[str, str] = {}

        for step in doc.steps[:400]:
            low = step.lower()

            # -- control suffixes embedded in the sentence -------------------
            end_marker = re.search(
                r"(?:,\s*|\s+and\s+|\s+;\s*|\s+once\s+|\s+after\s+which\s+)(?:the\s+)?process\s+(?:is\s+complete|is\s+closed|ends)\b",
                low,
            )
            loop_marker = re.search(
                r"(?:returns?|goes?\s*back|jumps?\s*back|reverts?|is\s+routed\s*back)\s+to\s+(?:the\s+)?([a-z0-9 ]{4,60}?)(?:[.,;]|$|\s+and\s)",
                low,
            )
            action_part = step
            if loop_marker and (not end_marker or loop_marker.start() < end_marker.start()):
                action_part = _tidy_tail(step[: loop_marker.start()])
            elif end_marker:
                action_part = _tidy_tail(step[: end_marker.start()])

            # -- explicit join of conditional branches -----------------------
            if re.search(r"\bin both cases\b|\bregardless of\b|\beither way\b|\bin any case\b", low):
                if open_gws:
                    frontier = self._close_gateway(model, open_gws.pop(), warnings)
                else:
                    warnings.append(f"Join marker found without open gateway: '{step[:60]}'")
                remainder = action_part.strip()
                if remainder and not self._looks_like_action(remainder, current_actor, roles):
                    if end_marker:
                        frontier = self._attach_end(model, frontier)
                    continue  # marker-only sentence

            # -- decision -----------------------------------------------------
            if re.match(r"^(?:if|whether)\b", low) or re.search(r",\s*(?:if|whether)\b", low):
                dm = re.match(r"^(?:if|whether)\s+(.+?)(?:,|\s+then\b)(.*)$", action_part, flags=re.I | re.S)
                if dm is None:
                    dm = re.search(r",\s*(?:if|whether)\s+(.+?)(?:,|\s+then\b)(.*)$", action_part, flags=re.I | re.S)
                if dm is None:
                    warnings.append(f"Unparsable decision sentence skipped: '{step[:60]}'")
                    continue
                condition = dm.group(1).strip().rstrip(".")
                rest = (dm.group(2) or "").strip()

                # negation continuation: "If complete, ..." after "If incomplete, ..."
                if open_gws and _negates(open_gws[-1].condition, condition):
                    ctx = open_gws[-1]
                    if rest:
                        attach = self._attach_actions(model, rest, [(ctx.gw_id, "No")], current_actor, roles)
                        ctx.no_frontier = attach.ends
                        ctx.no_filled = True
                        current_actor = attach.actor or current_actor
                        frontier = attach.ends
                    else:
                        frontier = ctx.no_frontier or [(ctx.gw_id, "No")]
                    if end_marker:
                        frontier = self._attach_end(model, frontier)
                        if ctx.no_filled:
                            ctx.no_frontier = list(frontier)  # branch terminated at end event
                    continue

                if open_gws and open_gws[-1].yes_filled and open_gws[-1].no_filled:
                    frontier = self._close_gateway(model, open_gws.pop(), warnings)

                gw_label = re.sub(r"^the\s+", "", condition, flags=re.I)
                gw_name = gw_label[:1].upper() + gw_label[1:] + "?"
                gw = model.add_node(gw_name, NodeType.XOR_GATEWAY, source_text=step)
                for nid, label in frontier:
                    model.add_flow(nid, gw.id, label)
                ctx = _GatewayCtx(gw_id=gw.id, condition=condition)

                if rest and self._looks_like_action(rest, current_actor, roles):
                    attach = self._attach_actions(model, rest, [(gw.id, "Yes")], current_actor, roles)
                    ctx.yes_frontier = attach.ends
                    ctx.yes_filled = True
                    current_actor = attach.actor or current_actor
                    frontier = attach.ends
                    if loop_marker and attach.ends:
                        self._attach_rework(model, loop_marker.group(1), attach.ends, warnings)
                        ctx.yes_frontier = []  # branch continues only via the loop
                        ctx.yes_terminated = True
                else:
                    ctx.yes_frontier = [(gw.id, "Yes")]
                    frontier = [(gw.id, "Yes")]
                    if loop_marker:
                        self._attach_rework(model, loop_marker.group(1), frontier, warnings)
                open_gws.append(ctx)
                if end_marker:
                    frontier = self._attach_end(model, frontier)
                    if ctx.yes_filled:
                        ctx.yes_frontier = list(frontier)  # branch terminated at end event
                continue

            # -- otherwise / else branch --------------------------------------
            if re.match(r"^(?:otherwise|else|if not)\b", low):
                if open_gws:
                    ctx = open_gws[-1]
                    m = re.match(r"^(?:otherwise|else|if not)\b[,]?\s*", action_part.strip(), flags=re.I)
                    branch = action_part.strip()[m.end():].strip() if m else action_part.strip()
                    if branch and self._looks_like_action(branch, current_actor, roles):
                        attach = self._attach_actions(model, branch, [(ctx.gw_id, "No")], current_actor, roles)
                        ctx.no_frontier = attach.ends
                        ctx.no_filled = True
                        current_actor = attach.actor or current_actor
                        frontier = attach.ends
                        if loop_marker and attach.ends:
                            self._attach_rework(model, loop_marker.group(1), attach.ends, warnings)
                            ctx.no_frontier = []
                            ctx.no_terminated = True
                    else:
                        frontier = ctx.no_frontier or [(ctx.gw_id, "No")]
                    if end_marker:
                        frontier = self._attach_end(model, frontier)
                        if ctx.no_filled:
                            ctx.no_frontier = list(frontier)  # branch terminated at end event
                else:
                    warnings.append(f"'otherwise' without open gateway: '{step[:60]}'")
                continue

            # -- parallel work --------------------------------------------------
            if re.search(r"\bwhile\b|\bmeanwhile\b|\bat the same time\b|\bin parallel\b|\bsimultaneously\b", low):
                frontier = self._handle_parallel(model, action_part, frontier, current_actor, roles)
                if end_marker:
                    frontier = self._attach_end(model, frontier)
                continue

            # -- implicit join before a fresh sequential action -----------------
            if open_gws and open_gws[-1].yes_filled and open_gws[-1].no_filled:
                frontier = self._close_gateway(model, open_gws.pop(), warnings)

            # -- end-marker-only sentence ---------------------------------------
            if re.match(r"^(?:the\s+)?process\s+(?:is\s+complete|is\s+closed|ends)\b", low):
                frontier = self._attach_end(model, frontier)
                continue

            # -- plain action chain ----------------------------------------------
            if action_part.strip() and self._looks_like_action(action_part, current_actor, roles):
                attach = self._attach_actions(model, action_part, frontier, current_actor, roles)
                frontier = attach.ends
                current_actor = attach.actor or current_actor
                if loop_marker:
                    self._attach_rework(model, loop_marker.group(1), attach.ends, warnings)
                if end_marker:
                    frontier = self._attach_end(model, frontier)
            elif end_marker or loop_marker:
                if loop_marker:
                    self._attach_rework(model, loop_marker.group(1), frontier, warnings)
                if end_marker:
                    frontier = self._attach_end(model, frontier)

        # -- finalisation -------------------------------------------------------
        while open_gws:
            frontier = self._close_gateway(model, open_gws.pop(), warnings)
        if not frontier or not all(
            model.node(nid) is not None and model.node(nid).type == NodeType.END_EVENT
            for nid, _ in frontier
        ):
            self._attach_end(model, frontier)

        return ParseResult(model=model, warnings=warnings)

    # -- step handlers -------------------------------------------------------

    def _handle_parallel(
        self,
        model: ProcessModel,
        step: str,
        frontier: List[Tuple[str, Optional[str]]],
        current_actor: Optional[str],
        roles: List[str],
    ) -> List[Tuple[str, Optional[str]]]:
        parts = re.split(
            r",?\s+(?:while|meanwhile|and simultaneously|at the same time|in parallel)\s+",
            step,
            flags=re.I,
        )
        parts = [p.strip(" .;,") for p in parts if p.strip(" .;,")]
        if len(parts) < 2:
            parts = [step.strip(" .;,")]
        split_gw = model.add_node("", NodeType.AND_GATEWAY, source_text=step)
        for nid, label in frontier:
            model.add_flow(nid, split_gw.id, label)
        join_gw = model.add_node("", NodeType.AND_GATEWAY, source_text=step)
        branch_ends: List[Tuple[str, Optional[str]]] = []
        for part in parts:
            if not self._looks_like_action(part, current_actor, roles):
                continue
            attach = self._attach_actions(model, part, [(split_gw.id, None)], current_actor, roles)
            branch_ends.extend(attach.ends)
        if not branch_ends:
            return [(split_gw.id, None)]
        for nid, label in branch_ends:
            model.add_flow(nid, join_gw.id, label)
        return [(join_gw.id, None)]

    def _close_gateway(
        self,
        model: ProcessModel,
        ctx: _GatewayCtx,
        warnings: List[str],
    ) -> List[Tuple[str, Optional[str]]]:
        def alive(ends: List[Tuple[str, Optional[str]]]) -> List[Tuple[str, Optional[str]]]:
            out = []
            for nid, lab in ends:
                node = model.node(nid)
                if node is not None and node.type != NodeType.END_EVENT:
                    out.append((nid, lab))
            return out

        yes_alive = alive(ctx.yes_frontier)
        no_alive = alive(ctx.no_frontier)
        if yes_alive and no_alive:
            join_gw = model.add_node("", NodeType.XOR_GATEWAY, source_text=f"join of '{ctx.condition}'")
            for nid, label in yes_alive + no_alive:
                model.add_flow(nid, join_gw.id, label)
            return [(join_gw.id, None)]
        if yes_alive or no_alive:
            # the other branch already terminated in an end event; nothing to merge
            return yes_alive or no_alive
        if ctx.yes_frontier or ctx.no_frontier:
            terminated = (ctx.yes_frontier or ctx.no_frontier)[-1]
            return [terminated]
        return [(ctx.gw_id, None)]

    def _attach_rework(
        self,
        model: ProcessModel,
        fragment: str,
        ends: List[Tuple[str, Optional[str]]],
        warnings: List[str],
    ) -> None:
        frag_tokens = _tokens(fragment)
        target = None
        best = 0.0
        for t in model.tasks():
            if any(nid == t.id for nid, _ in ends):
                continue  # never loop to the node we are attaching from
            score = _token_similarity(frag_tokens, t.name)
            if score > best:
                best, target = score, t
        if not target or best < 0.45:
            warnings.append(f"Rework target not found for fragment '{fragment.strip()}'")
            return

        # merge into the target through an explicit XOR join (BPMN-clean rework loop)
        join_id = self._rework_joins.get(target.id)
        if join_id is None:
            incoming = [f for f in model.flows if f.target == target.id]
            if incoming:
                join = model.add_node("", NodeType.XOR_GATEWAY,
                                      source_text=f"rework merge into '{target.name}'")
                model.flows = [f for f in model.flows if f.target != target.id]
                for f in incoming:
                    model.add_flow(f.source, join.id, f.label)
                model.add_flow(join.id, target.id)
                join_id = join.id
            else:
                join_id = target.id
            self._rework_joins[target.id] = join_id
        for nid, _ in ends:
            model.add_flow(nid, join_id, "Rework")

    def _attach_end(
        self,
        model: ProcessModel,
        frontier: List[Tuple[str, Optional[str]]],
    ) -> List[Tuple[str, Optional[str]]]:
        valid = [(nid, lab) for nid, lab in frontier if model.node(nid) is not None]
        if valid and all(model.node(nid).type == NodeType.END_EVENT for nid, _ in valid):
            return valid
        end = model.add_node("Process end", NodeType.END_EVENT)
        if len(valid) > 1:
            join_gw = model.add_node("", NodeType.XOR_GATEWAY)
            for nid, label in valid:
                model.add_flow(nid, join_gw.id, label)
            model.add_flow(join_gw.id, end.id)
        else:
            for nid, label in valid:
                model.add_flow(nid, end.id, label)
        return [(end.id, None)]

    # -- task creation ---------------------------------------------------------

    @dataclass
    class _Attach:
        ends: List[Tuple[str, Optional[str]]]
        actor: Optional[str] = None

    def _attach_actions(
        self,
        model: ProcessModel,
        text: str,
        frontier: List[Tuple[str, Optional[str]]],
        current_actor: Optional[str],
        roles: List[str],
    ) -> "OfflineProcessParser._Attach":
        clauses = _split_clauses(text)
        ends: List[Tuple[str, Optional[str]]] = []
        actor = current_actor
        prev_id: Optional[str] = None
        for i, clause in enumerate(clauses):
            if not self._looks_like_action(clause, actor, roles):
                continue
            clause_actor = self._detect_actor(clause, roles) or actor
            name = _task_name(clause, clause_actor)
            automated = any(cue in clause.lower() for cue in AUTO_CUES) or bool(
                clause_actor and any(w in clause_actor.lower() for w in SYSTEM_ACTOR_WORDS)
            )
            kind = self._infer_kind(clause, clause_actor, automated)
            node = model.add_node(
                name,
                NodeType.TASK,
                kind=kind,
                actor=clause_actor,
                source_text=text.strip(),
                duration_minutes=self._infer_duration(clause, automated, kind),
                automated=automated,
            )
            if i == 0 or prev_id is None:
                for nid, label in frontier:
                    model.add_flow(nid, node.id, label)
            if prev_id:
                model.add_flow(prev_id, node.id)
            prev_id = node.id
            actor = clause_actor or actor
        if prev_id is not None:
            # a sequential chain continues from its LAST task only
            ends = [(prev_id, None)]
        else:
            ends = [(nid, lab) for nid, lab in frontier if model.node(nid) is not None]
        return self._Attach(ends=ends, actor=actor)

    def _looks_like_action(self, clause: str, actor: Optional[str], roles: List[str]) -> bool:
        low = clause.strip().lower().rstrip(".;:,")
        if not low or len(low) < 4:
            return False
        if re.match(r"^(?:the\s+)?process\s+(?:begins|starts|ends|is\s+complete|is\s+closed)", low):
            return False
        # passive voice: "the application is rejected"
        pm = re.match(r"^(?:the\s+)?[a-z ]+?\s+(?:is|are|was|were)\s+([a-z]+)$", low)
        if pm and (pm.group(1).endswith("ed") or pm.group(1) in PARTICIPLE_TO_VERB):
            return True
        text = clause.strip().rstrip(".;:,")
        text = _strip_prefixes(text)
        if actor:
            esc = re.escape(actor.lower())
            text = re.sub(rf"^(?:the\s+)?{esc}\s+(?:then\s+)?", "", text, flags=re.I)
        m = GENERIC_ROLE_RE.match(text)
        if m:
            text = text[m.end():].strip()
        # scan past role/system words ("The ERP System creates..." / "The Vendor
        # Portal notifies...") until the verb; a non-verb breaks the search.
        seen = 0
        for w in re.findall(r"[A-Za-z]+", text):
            lw = w.lower()
            if lw in VERBISH_SKIP:
                continue
            seen += 1
            if seen > 4:
                return False
            if _verbish(w):
                return True
            if lw in NON_VERBS:
                return False
        return False

    def _detect_actor(self, clause: str, roles: List[str]) -> Optional[str]:
        low = clause.lower()
        best: Optional[str] = None
        best_len = 0
        for role in roles:
            if role.lower() in low and len(role) > best_len:
                best, best_len = role, len(role)
        if best:
            return best
        m = GENERIC_ROLE_RE.search(clause)
        if m:
            return m.group(1).strip()
        if re.search(r"\bthe system\b", low):
            return "System"
        return None

    def _infer_kind(self, clause: str, actor: Optional[str], automated: bool) -> TaskKind:
        low = clause.lower()
        verb = _first_verb(clause)
        if verb in SEND_VERBS:
            return TaskKind.SEND
        if verb in RECEIVE_VERBS:
            return TaskKind.RECEIVE
        if automated:
            return TaskKind.SERVICE
        if actor and any(w in actor.lower() for w in SYSTEM_ACTOR_WORDS):
            return TaskKind.SERVICE
        if verb in APPROVE_VERBS or verb in REVIEW_VERBS:
            return TaskKind.USER
        if re.search(r"\bmanually\b|\bphysical", low):
            return TaskKind.MANUAL
        return TaskKind.USER

    def _infer_duration(self, clause: str, automated: bool, kind: TaskKind) -> float:
        if automated or kind == TaskKind.SERVICE:
            return 1.0
        verb = _first_verb(clause)
        for verbs, minutes in (
            (APPROVE_VERBS, 45.0),
            (REVIEW_VERBS, 30.0),
            (CHECK_VERBS, 15.0),
            (CREATE_VERBS, 10.0),
            (SEND_VERBS, 2.0),
            (RECEIVE_VERBS, 2.0),
        ):
            if verb in verbs:
                return minutes
        return 10.0

    def _start_event_name(self, doc: IngestedDocument) -> str:
        for step in doc.steps[:6]:
            low = step.lower()
            m = re.search(
                r"(?:begins|starts)\s+when\s+(?:(?:the|an|a)\s+)?([a-z ]+?)\s+(?:is|are)\s+(received|submitted|logged|raised|created|reported)",
                low,
            )
            if m:
                return f"{m.group(1).strip().capitalize()} {m.group(2)}"
            m = re.search(
                r"(?:begins|starts)\s+when\s+(?:a|an|the)\s+([a-z ]+?)\s+"
                r"(submits|sends|logs|raises|registers|requests|reports)\s+(?:a|an|the)\s+"
                r"([a-z ]+?)(?:\s+(?:through|via|in|to)\b.*)?$",
                low,
            )
            if m:
                past = {
                    "submits": "submitted", "sends": "sent", "logs": "logged",
                    "raises": "raised", "registers": "registered",
                    "requests": "requested", "reports": "reported",
                }[m.group(2)]
                return f"{m.group(3).strip().capitalize()} {past}"
        return "Process start"
