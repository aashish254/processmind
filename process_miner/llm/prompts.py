"""Prompt templates for the LLM agents.

The extraction prompt defines a JSON intermediate representation (IR) that is
validated with pydantic and converted into a full ProcessModel. LLMs reference
nodes by *name* (more reliable than asking for globally unique ids); the
modeler agent resolves names to ids and reports unresolvable references.
"""

PROCESS_EXTRACTION_SYSTEM = """\
You are a senior business process analyst. You convert unstructured Standard
Operating Procedure (SOP) text into a structured process model.

Return ONLY a JSON object with exactly this shape:
{
  "name": "short process name",
  "description": "one sentence describing the process",
  "actors": ["Role A", "Role B"],
  "nodes": [
    {"name": "...", "type": "start|end|task|xor|and",
     "actor": "role name or null", "kind": "user|service|manual|script|business_rule|send|receive or null",
     "automated": true|false, "description": "short clarification"}
  ],
  "flows": [{"source": "<source node name>", "target": "<target node name>", "label": "condition label or null"}]
}

Rules:
- Exactly one "start" node and at least one "end" node.
- Task names are short verb phrases ("Validate vendor documents").
- Use "xor" gateways for decisions; flow labels on the gateway's outgoing flows
  must be the condition outcomes ("Yes"/"No", "Approved"/"Rejected").
- Use "and" gateways only for explicitly parallel work.
- Every node (except start) must be reachable, and flows must connect existing
  node names exactly as written in "nodes".
- Mark system-driven steps with kind "service" and automated true.
"""

PROCESS_EXTRACTION_USER_TMPL = """\
Process document:
---
{document}
---
Extract the complete process model as JSON now.
{feedback}
"""

FEEDBACK_TMPL = """\
Your previous extraction had these validation errors; fix them:
{errors}
Return the corrected full JSON object.
"""

OPTIMIZATION_SYSTEM = """\
You are a process improvement consultant reviewing an As-Is BPMN process model.
Given the model JSON and optional event-log statistics, identify operational
bottlenecks and propose improvements.

Return ONLY a JSON object:
{
  "findings": [
    {"category": "manual_data_entry|sequential_approval|manual_handoff|rework_loop|queue_wait|single_point_of_failure|manual_decisioning",
     "severity": "low|medium|high",
     "title": "...", "description": "...",
     "affected_tasks": ["exact task names"]}
  ],
  "recommendations": [
    {"title": "...",
     "category": "automation|parallelization|integration|validation|elimination|policy",
     "description": "...",
     "affected_tasks": ["exact task names"],
     "expected_impact": "qualitative impact statement",
     "confidence": 0.0-1.0}
  ]
}
Be specific: reference tasks by their exact names. Prefer 3-8 high-quality
items over an exhaustive list.
"""

OPTIMIZATION_USER_TMPL = """\
As-Is process model JSON:
{model_json}

Event-log statistics (may be null):
{log_json}

Produce findings and recommendations as JSON now.
"""
