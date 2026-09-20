# User Stories & Acceptance Criteria — ProcessMind

Format: `ID — As a <role>, I want <capability>, so that <benefit>` with Gherkin-style acceptance criteria. Traceability to SRS functional requirements in brackets.

---

## Analyst stories

**US-01 — Ingest an SOP document** [FR-01]
> As a systems analyst, I want to point the tool at an SOP file so that I get a structured process model without manual modelling.

```gherkin
Given an SOP markdown file with a metadata header and a Procedure section
When I run `mine inputs/vendor_onboarding_sop.md`
Then the document metadata contains the process name and role list
And no Purpose/Scope/Controls content appears in the extracted steps
And every extracted node records its originating sentence
```

**US-02 — Generate BPMN 2.0 automatically** [FR-06]
> As an analyst, I want a `.bpmn` file that opens directly in my existing tooling.

```gherkin
Given a successfully extracted process model
When the export stage runs
Then the `.bpmn` file parses as XML with BPMN and BPMNDI namespaces
And every node has a shape and every flow an edge with waypoints
And bpmn-js imports the file without errors
```

**US-04 — Find bottlenecks with evidence** [FR-10]
> As a stakeholder, I want bottlenecks quantified, not guessed.

```gherkin
Given an As-Is model and a matching event log
When the Optimizer runs
Then static findings include manual data entry and sequential approvals where present
And log findings include the top queue waits with median values
And every finding cites affected task names and numeric evidence
```

**US-05 — Produce a To-Be model** [FR-10]
> As an analyst, I want concrete, applied improvement transformations.

```gherkin
Given findings with applicable recommendations
When optimization is applied
Then the To-Be model passes the same structural validation
And automated tasks are service tasks with reduced durations
And parallelised approvals are wired with AND split/join gateways
And before/after metrics show the expected delta (e.g. automation rate up)
```

**US-10 — Trust the output** [NFR-2, NFR-8]
> As an auditor, I want determinism and provenance.

```gherkin
Given the same input document and options
When the pipeline runs twice
Then all generated artifacts are identical
And a `_result.json` manifest lists every artifact with timings and warnings
```

## Process miner stories

**US-03 — Mine a process from an event log** [FR-07..FR-09]
> As a process miner, I want to discover the enacted process from raw logs.

```gherkin
Given a CSV with case_id, activity, timestamp and optional resource columns
When I run `analyze-log events.csv`
Then corrupt timestamp rows are skipped and the rest parsed
And a validated BPMN model with XOR split/join gateways is produced
And per-activity waits, rework rates and top-5 variants are reported
```

## Reviewer / examiner stories

**US-06 — Run without any LLM** [NFR-1]
> As a reviewer without API keys, I want the full pipeline to work offline.

```gherkin
Given no LLM environment variables are set
When any pipeline command runs
Then the extractor method is recorded as "offline-rules"
And no network call is attempted and the run completes successfully
```

**US-07 — Choose the orchestration engine** [FR-15]
> As a researcher, I want to swap orchestration frameworks without changing results.

```gherkin
Given a fixed input document
When the pipeline runs with --engine builtin and --engine langgraph
Then both runs report equal model summary metrics and equal finding titles
```

**US-08 — Evaluate extraction quality** [FR-11, FR-12]
> As an examiner, I want quantified extraction quality against gold models.

```gherkin
Given gold annotations for each corpus document
When I run `eval`
Then task precision/recall/F1, actor F1, gateway and rework errors are computed
And eval_report.json and eval_report.md are written
```

## Developer stories

**US-09 — Serve results over HTTP** [FR-13]
> As a developer, I want to integrate ProcessMind into other tooling.

```gherkin
Given the FastAPI app is running
When POST /api/v1/mine receives valid SOP text
Then it returns model JSON, BPMN XML, mermaid, findings and recommendations
When it receives malformed input
Then it responds 422 with a descriptive message
```

**US-11 — Regenerate the test data**
> As a developer, I want the synthetic event logs reproducible.

```gherkin
Given scripts/generate_logs.py with fixed seeds
When the logs are regenerated
Then the CSVs are byte-identical to the committed ones
```

## Story map (release view)

| Milestone | Stories |
|---|---|
| v1.0 (this capstone) | US-01..US-11 — all implemented and tested (125 tests) |
| Future | human-in-the-loop model repair UI; conformance diff (documented vs discovered); multi-language SOPs |
