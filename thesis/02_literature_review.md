# Chapter 2: Literature Review

This chapter positions the thesis within five interconnected bodies of knowledge: business process management, process mining, text-to-process extraction, large language models in business process contexts, and multi-agent systems. The chapter establishes the theoretical foundations, reviews the state of the art, identifies the specific gap this thesis addresses, and concludes with a synthesis that motivates the five research questions.

---

## 2.1 Business Process Management and BPMN

### 2.1.1 Processes, Process Management, and the Modelling Bottleneck

A business process is a structured, time-ordered set of activities performed by people and/or systems to achieve a defined business goal (Dumas et al., 2018). Business Process Management (BPM) is the discipline that seeks to understand, improve, and sustain these processes through systematic methods, tools, and techniques (Hammer, 2015). The BPM lifecycle comprises four phases: process identification, process discovery (capturing the As-Is process), process analysis (measuring and diagnosing performance), and process improvement/transformation (designing and implementing the To-Be process), followed by process monitoring and control (Dumas et al., 2018).

Process discovery — understanding how work is actually performed — is a prerequisite for every subsequent phase. In practice, it is also the most expensive step. A typical process mapping exercise for a medium-sized enterprise involves multiple stakeholder interviews, workshop sessions with process participants, and iterative validation with process owners, often spanning days to weeks of analyst effort (Mendling et al., 2010). The result is typically a hand-drawn or tool-authored BPMN diagram representing the analyst's interpretation of the documented process — not the enacted process, and not a computationally exploitable artifact.

This manual discovery bottleneck has two compounding causes. First, documented processes (in the form of Standard Operating Procedures, runbooks, policy documents, and onboarding guides) are abundant but unstructured — written for human readers, not machines. Second, enacted processes are recorded in enterprise systems (ERP, CRM, ITSM) as event logs, but these logs record only *what happened*, not *why* or *what was intended*. Reconciling the documented intent with the enacted reality requires both sources simultaneously, yet no established method handles both within a single, automated pipeline.

### 2.1.2 BPMN 2.0 as the Representation Standard

The Business Process Model and Notation version 2.0 (BPMN), standardised by the Object Management Group (OMG, 2011), is the de facto graphical language for business process representation. A BPMN model comprises **tasks** (atomic activities, typed as user, service, send, or manual), **gateways** (decisional flow branching: XOR for data-based choice, OR for complex conditions, AND for parallel execution), **sequence flows** (directed edges connecting nodes), **lanes** (representing organisational actors or roles), and **events** (start, intermediate, and end markers).

BPMN's expressiveness includes rework loops (modelled via XOR gates that route back to an upstream activity), parallel blocks (AND gates that split and rejoin), and nested sub-processes. A well-formed BPMN model must satisfy structural validity properties: every node is reachable from the start event and can reach the end event; sequence flows reference valid source and target nodes; gateway directions (split, join, or mixed) are consistent with the surrounding flow structure; and the model's underlying state machine is sound (produces exactly one token at start, does not deadlock, and terminates properly) (Dumas et al., 2018). Structural validity is a prerequisite for meaningful analysis: an invalid BPMN model cannot be reliably simulated, analysed for bottlenecks, or used for conformance checking.

The practical standard for BPMN interchange is the BPMN 2.0 XML serialisation, which separates the abstract syntax (nodes, flows, gateway types) from the diagram interchange (DI) layer (shape positions, waypoints, lane stacking). This XML format is what process mining tools (PM4Py, ProM, Celonis) and modelling environments (Camunda Modeler, bpmn-js, Signavio) consume and produce, making format fidelity a core engineering requirement.

### 2.1.3 The As-Is / To-Be Improvement Pattern

The canonical BPM improvement pattern distinguishes the **As-Is** process (how work is currently performed) from the **To-Be** process (how it should be performed after improvement interventions) (Hammer & Champy, 1993). The As-Is model surfaces bottlenecks (sequential dependencies, approval chains, rework loops), unnecessary handoffs, and manual data entry points that are invisible when looking at any single system in isolation. The To-Be model applies improvement patterns — automation of manual tasks, parallelisation of sequential approvals, elimination of unnecessary rework — to produce a target state against which future performance can be measured.

Automating the As-Is / To-Be workflow requires, at minimum: (a) automated extraction of a structurally valid As-Is BPMN model from available process descriptions; (b) automated analysis of that model against performance evidence (event logs); and (c) generation of a corresponding To-Be BPMN model with improvement recommendations applied. This thesis addresses all three sub-problems within a single pipeline.

---

## 2.2 Process Mining: Discovery, Conformance, and Enhancement

Process mining is the family of techniques that extracts process knowledge from event logs recorded by information systems (van der Aalst, 2016). Three primary use cases are distinguished: **process discovery** (deriving a process model from an event log without any a priori model), **conformance checking** (comparing an a priori model against observed behaviour in a log), and **process enhancement** (extending or improving a model using information extracted from the log). This section reviews the discovery and conformance branches, as these are the process-mining pillars this thesis builds on.

### 2.2.1 Event Logs and the Directly-Follows Relationship

An event log is a collection of traces (ordered sequences of events for individual process instances, identified by a case ID), where each event records an activity name, a timestamp, and optionally a resource (the actor or system that performed it). The IEEE standard for event log interchange is XES (Verbeek et al., 2010), supported by virtually all commercial and open-source process mining platforms.

The fundamental relationship in process discovery is **directly-follows**: given activities A and B, A is directly followed by B if there exists at least one trace where B occurs immediately after A, with no intervening activities. The **directly-follows graph (DFG)** is a directed graph where nodes are activities and edges are weighted by the count (or fraction) of traces exhibiting each directly-follows relationship. The DFG is the input to the most widely used discovery algorithms.

### 2.2.2 Discovery: From DFG to Block-Structured Process Trees

**Heuristic mining** (Weijters & van der Aalst, 2003) applies frequency thresholds to the DFG to filter noise, then induces gateway types (XOR vs AND) from the DFG footprint matrix (whether A→B and B→A both appear). This produces a BPMN model with induced gateways. While fast and scalable, heuristic mining has two well-known weaknesses: gateway induction from DFG patterns is heuristic (a mutual A→B and B→A relationship could indicate either an AND block or a rework loop), and the resulting model may not be sound — deadlocks, unreachable nodes, and improper termination are common (Mendling et al., 2010).

The **Inductive Miner** (Leemans et al., 2013) addresses the soundness problem by discovering block-structured process trees — hierarchical representations where leaf nodes are activities and operator nodes are xor, sequence, parallel (and), or loop. The algorithm applies recursive cuts to the activity set: an xor cut separates mutually exclusive activity sets; a sequence cut separates activities that always occur in order; a parallel cut separates activities that can occur in any order; and a loop cut identifies a do-part and a redo-part. The key theoretical result is that the Inductive Miner's cuts are **language-preserving**: the language of the discovered tree equals the language of the input log (the set of traces it accepts). Consequently, a model produced by the Inductive Miner is sound by construction, not by post-hoc validation.

The **flower model** (the Inductive Miner with no cuts applied) accepts all possible traces and is trivially sound but uninformative — it represents the ceiling of model permissiveness. In practice, applying the Inductive Miner to a log with moderate noise (a fraction of traces that deviate from the dominant path) may produce a model with lower fitness (fewer traces accepted) but substantially higher precision (the model accepts fewer extraneous behaviours). This fitness/precision trade-off is a core empirical object of this thesis (Research Question 4).

### 2.2.3 Conformance Checking

Conformance checking quantifies the degree to which observed behaviour (in a log) conforms to a reference model (a BPMN or Petri net). The most widely used measure is **token-based replay fitness** (van der Aalst et al., 2012): a token is placed at the start event, events from the log are replayed one by one by consuming tokens at the appropriate place; if a token is unavailable or an event cannot be fired, the replay fails. The fitness score is the ratio of successfully replayed cases to total cases, or equivalently, the fraction of tokens that are not missing or left over at the end of replay.

More recent approaches use **alignment-based fitness** (van der Aalst et al., 2012), which finds the optimal alignment between a trace and the reference model by inserting dummy moves (deviations) where the trace deviates from the model. Alignment-based fitness is more precise than token-based replay but substantially more computationally expensive. Both approaches are used in this thesis: token-based replay for the experimental evaluation of the Inductive Miner (speed and boundedness favour replay for large logs), and alignment-based notions for the conformance checking between documented and enacted models (precision and recall on the directly-follows relationship).

### 2.2.4 The Process Mining Tool Ecosystem

The open-source **PM4Py** library (Berti et al., 2019) provides Python implementations of the Inductive Miner, DFG discovery, conformance checking, and bottleneck analysis, and is the closest existing tool to the discovery pathway in this thesis. **ProM** (van Dongen et al., 2005) is the reference Java-based process mining workbench, with hundreds of plug-ins. Commercial platforms (Celonis, SAP Signavio, Disco) provide enterprise-scale mining with curated connectors to ERP and CRM systems.

A critical observation, established in the literature and confirmed in this thesis's experiments, is that **all process mining tools require event logs as input**. None can ingest an SOP document and produce a model. This is the fundamental gap that the text-extraction pathway of this thesis addresses: extending the process mining paradigm to sources that do not have an event log structure.

---

## 2.3 Text-to-Process Extraction

The conversion of unstructured process descriptions into structured process models is a long-standing problem in the BPM field, approached from natural language processing, information extraction, and more recently, machine learning perspectives.

### 2.3.1 Early Approaches: NLP and Heuristics

The earliest text-to-process systems relied on syntactic pattern matching: detecting trigger phrases (after, then, when), decision cues (if, otherwise, in case), parallel markers (while, meanwhile, at the same time), and loop indicators (return to, restart from) to infer control flow structure (Friedrich et al., 2011). These approaches achieved moderate precision on well-structured documents (formal SOPs, regulatory procedures) but degraded sharply on informal text with implicit control flow, coreferences, and passive voice constructions.

Semantic approaches used dependency parsing to identify subject-verb-object structures, semantic role labelling to identify actors and actions, and named entity recognition to detect process activities (Lleo et al., 2014). Rule-based systems could achieve high recall on documents that matched the expected vocabulary but required extensive domain-specific rule authoring for each new document type.

Supervised learning approaches treated activity extraction as a sequence labelling problem (e.g., using conditional random fields or recurrent neural networks trained on annotated SOP corpora). These required labelled training data (typically hundreds of manually annotated SOPs) and generalisation to new domains remained a challenge. The F1 scores reported in the literature for task extraction from SOP text typically ranged from 0.6 to 0.8 on in-domain test sets, with significant degradation on out-of-domain text (van der Aa et al., 2019).

### 2.3.2 Process Extraction as Structured Output

A more recent tradition frames text-to-process as a schema-guided information extraction problem. Given a predefined process meta-model (activities, gateways, actors, sequence flows), extraction systems parse the text and populate the meta-model instance. The meta-model may be a BPMN fragment (Friedrich et al., 2011), a declarative constraint set (van der Aa et al., 2019), or a custom schema. This framing has the advantage of producing directly machine-readable output, but requires the meta-model to be specified a priori and limits extraction to the predefined vocabulary.

The most significant weakness of all pre-LLM approaches is their treatment of **process structure** — particularly gateway semantics and rework loops — which is typically either hard-coded as rule patterns or absent from the extraction output. The reconstruction of valid BPMN control flow from extracted activities is treated as a post-processing step, if addressed at all. This means that even when a text extraction system successfully identifies activities and actors, it may not produce a structurally valid process model.

### 2.3.3 The State of the Art Before LLMs

Before the widespread availability of large language models, the highest-quality text-to-process extraction required a combination of: (a) robust sentence-level NLP (tokenisation, dependency parsing, coreference resolution); (b) domain-specific rule authoring for control flow markers; (c) ontology-based activity normalisation; and (d) a manually specified meta-model template. The result was a pipeline that was expensive to build for each new domain, brittle to vocabulary variation, and produced models of uncertain structural validity without a post-hoc validation step.

The research proposed in this thesis was conceived against exactly this background: the offline rule parser (the E1 extractor) is a modern implementation of the best pre-LLM approach, producing structurally valid BPMN through deterministic rules. The LLM extractors (E2 and E3) represent the post-2022 state of the art, where a general-purpose language model is prompted to produce structured BPMN output directly, with bounded self-correction to enforce structural validity.

---

## 2.4 Large Language Models for Business Process Management

The emergence of large language models (LLMs) capable of following complex instruction hierarchies and producing structured output (OpenAI, 2023; Anthropic, 2024) opened a new possibility space for text-to-process extraction. Three threads of research are directly relevant: schema-guided extraction, multi-agent orchestration, and the structural validity problem.

### 2.4.1 Schema-Guided Extraction with LLMs

Modern LLMs (GPT-4, Claude, Gemini) can be instructed to produce structured JSON output conforming to a specified schema via in-context examples and explicit schema descriptions. In the BPM domain, this has been applied to: extracting activities and actors from SOP text (the approach used by this thesis's E2 extractor); generating BPMN XML from process descriptions; and inferring process constraints (pre-conditions, post-conditions) from natural language specifications.

The key advantages of LLM-based extraction over rule-based approaches are: (a) vocabulary generalisation — LLMs handle paraphrasing, synonymy, and domain-specific terminology without explicit rule authoring; (b) implicit common-sense inference — LLMs can infer implicit actors (e.g., "the system sends an automated email" implies a sendTask rather than a userTask) without explicit rules; and (c) the ability to produce a first draft from zero examples (zero-shot), with quality improving when few-shot examples are provided.

The key limitations are: (a) non-determinism — the same prompt with the same input may produce structurally different outputs across calls, even at temperature 0; (b) hallucination — LLMs may produce activities or gateways not grounded in the input text; (c) the structural validity problem — an LLM may produce a BPMN model that is syntactically valid JSON but semantically invalid as a process model (deadlocks, missing gateway joins, unreachable nodes); and (d) cost and latency — each LLM call has a monetary cost and introduces latency that a deterministic rule parser does not.

### 2.4.2 The Structural Validity Problem

A recurring finding in the emerging LLM-BPM literature is that LLM-generated process models frequently fail basic structural validity checks. Bellan et al. (2023), in a critical analysis of ChatGPT-generated process models, report that while the models often *look* plausible to a human reader, they routinely exhibit structural problems — reversed gateway directions (an XOR split used where a join is required), unreachable or dangling nodes, and deadlocks — even in cases where the same model is described as "structurally valid" by a non-expert evaluator. Precise error rates vary widely by prompt, model, and task, which is itself a finding: LLM structural validity is inconsistent and cannot be assumed.

This finding motivates the **separated architecture** that is the central design claim of this thesis: structure discovery and semantic enrichment must be separated. The LLM should be confined to enrichment tasks (naming activities, identifying actors, suggesting recommendations) where errors are recoverable and human-reviewable. Control flow structure — the soundness-critical element — should come from deterministic, provably-sound algorithms. This separation is implemented in the pipeline: the LLM (E2/E3) proposes a ProcessModel; the structural validator checks it; if it fails, the model is repaired or the extraction is retried with feedback.

### 2.4.3 Multi-Agent Orchestration and Self-Correction

The multi-agent paradigm — where multiple LLM agents with specialised roles interact to solve a complex task — has been applied to BPM extraction through architectures comprising an ingestion agent (document normalisation), a modelling agent (structured extraction), a validation agent (structural checking), and a feedback/correction agent (iterative repair). LangGraph (LangChain, 2024) implements this as a state machine where edges between stage nodes can be conditional: if the validation agent reports structural errors, the state transitions back to the modelling agent with the feedback; otherwise, the pipeline proceeds. This validate-and-retry pattern is the design of the thesis's E3 extractor configuration.

The research question of whether bounded self-correction (E3) yields measurable quality improvement over single-shot extraction (E2) is contested in the emerging literature. Some studies report that self-correction loops improve output quality by 10–20% on structured extraction tasks (Shinn et al., 2024); others find that the improvement is marginal and cost-prohibitive (Huang et al., 2024). This thesis contributes empirical evidence on this question under controlled conditions (Research Question 3).

---

## 2.5 Research Gap and Thesis Positioning

The literature reviewed in the preceding sections reveals a specific, well-defined gap at the intersection of process mining and LLM-based extraction:

1. **Process mining handles enacted processes but not documented processes.** The Inductive Miner and DFG discovery are well-established, sound algorithms for extracting control flow from event logs. They cannot, by design, process SOP text.

2. **Text-to-process extraction handles documented processes but not enacted processes.** Existing NLP and LLM approaches can extract activities and actors from SOP text, but do not produce sound process models without post-hoc validation, and cannot reconcile the documented process with the enacted process from an event log.

3. **No unified benchmark exists for comparing extraction methods.** The process mining literature evaluates discovery algorithms against event logs; the text-extraction literature evaluates extraction quality against gold annotations; and the LLM-BPM literature evaluates model quality by human assessment. No study compares deterministic, LLM-based, and mining-based extraction under identical measures on identical inputs.

4. **The bounded self-correction question is unresolved.** Whether a multi-agent validate-retry loop (E3) yields statistically significant improvement over single-shot LLM extraction (E2) is an open empirical question.

5. **Documented-versus-enacted drift is detected but not quantified for To-Be generation.** Conformance checking tools can compare a model against a log, but they do not generate improvement recommendations grounded in the drift evidence.

### 2.5.1 The Contribution of This Thesis

This thesis addresses the gap identified above through a unified pipeline and empirical evaluation. The key contributions are:

1. **A unified benchmark (E1–E6)** comparing five extractor configurations — deterministic rule parser (E1), single-shot LLM (E2), LLM with self-correction (E3), DFG discovery from log (E4), and Inductive Miner from log (E6) — under identical evaluation measures on identical inputs. No existing study performs this comparison; the closest analogues evaluate either E1 vs E4 or E2 in isolation, but never all five together.

2. **Empirical evidence on the self-correction question** (RQ3): whether bounded validate-and-retry (E3) significantly outperforms single-shot LLM extraction (E2) on task extraction quality, and whether the quality improvement — if any — justifies the additional LLM call cost.

3. **A sound-by-construction hybrid architecture** (E6): the Inductive Miner's control flow is provably sound; the LLM is confined to semantic enrichment. This separates the LLM from the soundness-critical computation and is the thesis's primary architectural contribution.

4. **Automated documented-versus-enacted drift detection** with quantitative measures (DF precision/recall) and a bottleneck-grounded optimizer that produces defensible To-Be recommendations from the drift evidence (RQ5).

5. **An open-source reference implementation** with 162 passing tests, deterministic outputs, and a one-command evaluation harness, enabling full replication of the experimental results.

The five research questions (Chapter 3) are each motivated by a specific aspect of this gap. The evaluation design (Chapter 4) operationalises the gap closure through the six extractor configurations and the unified evaluation harness.

---

## 2.6 Chapter Summary

This chapter established the theoretical and empirical foundations for the thesis. Section 2.1 introduced BPM concepts and BPMN as the representation standard, with the As-Is / To-Be improvement pattern as the motivational use case. Section 2.2 reviewed process mining, covering the DFG and Inductive Miner discovery families, conformance checking via token replay, and the tool ecosystem — establishing that all process mining tools require event logs and cannot process SOP text. Section 2.3 reviewed text-to-process extraction, tracing the evolution from syntactic pattern matching through supervised learning to the pre-LLM state of the art, with its documented weaknesses in structural validity and vocabulary generalisation. Section 2.4 reviewed LLM-based extraction, multi-agent orchestration, and the emerging evidence on the structural validity problem and the self-correction question. Section 2.5 synthesised these four bodies of knowledge into the specific research gap this thesis addresses: the absence of a unified benchmark comparing deterministic, LLM-based, and mining-based extraction under identical measures; the unresolved self-correction question; and the lack of automated, drift-grounded To-Be generation.

The following chapter presents the five research questions that operationalise this gap closure.