# Chapter 3: Research Methodology

This chapter describes the research design, corpus, gold standard, extractor configurations, evaluation measures, and statistical analysis plan. The goal is to provide sufficient detail that the study could be replicated by an independent researcher using the same or an equivalent dataset and evaluation harness.

## 3.1 Research Design

The study adopts a **comparative evaluation** design, following the tradition of empirical software engineering research (Wohlin et al., 2012). The object of study is a software pipeline — the ProcessMind framework — configured in five extraction modes (E1 through E6). Each configuration is evaluated against the same set of inputs (SOP documents and event logs) using the same measurement instruments. The dependent variables are extraction quality (task P/R/F1, actor F1, structure errors), discovery soundness (token-replay fitness, variant coverage, model size), and conformance quantification (DF precision/recall). The independent variable is the extractor configuration.

This design is appropriate because: (a) the research questions are comparative (how does configuration A compare with configuration B on the same inputs under the same measures?); (b) the inputs and measures are standardised, enabling deterministic comparison; and (c) the approach produces quantitative results that can be subjected to statistical analysis.

The study does not involve human subjects for the primary evaluation (the gold standard models are pre-annotated by the author; the evaluation is automated). A human-in-the-loop study is identified as future work (Chapter 7).

### 3.1.1 Research Questions and Their Operationalisation

**RQ1:** To what extent can unstructured SOP text be converted into structurally valid BPMN 2.0 models without human modelling effort?

*Operationalisation:* The E1 extractor (offline rule parser, no LLM) is applied to all four SOPs. RQ1 asks: what extraction quality does E1 achieve against the gold-annotated reference models? Structural validity is assessed by the automated BPMN validator.

**RQ2:** How does a deterministic rule-based extractor compare with an LLM-based multi-agent extractor on task, actor, and gateway recovery?

*Operationalisation:* E1 is compared against E2 (single-shot LLM, `qwen/qwen3-8b`, OpenRouter) and E3 (E2 with validate-and-retry self-correction, maximum 2 retries) on identical SOP inputs. Quantified by task P/R/F1, actor F1, and structure errors.

**RQ3:** Does multi-agent orchestration (model → validate → critique → retry) measurably improve output quality over single-prompt extraction?

*Operationalisation:* E2 (single-shot LLM) is compared against E3 (E2 + bounded self-correction loop) on identical SOP inputs. The quality delta is tested for statistical significance across the four documents.

**RQ4:** How do DFG-based discovery (E4) and sound block-structured discovery (E6, Inductive Miner) trade off fitness, precision, and model complexity on identical logs?

*Operationalisation:* Both E4 and E6 are run on every available event log. Token-replay fitness (cases accepted / total cases), variant coverage (variants accepted / total variants), and model size (node count, gateway count) are compared.

**RQ5:** Can documented-versus-enacted drift be detected and quantified automatically to produce defensible As-Is → To-Be recommendations?

*Operationalisation:* For each SOP-log pair, activities are aligned by lexical similarity; directly-follows relations of the documented and enacted models are compared; drift is classified and quantified; bottleneck evidence from the log is used to rank improvement recommendations.

## 3.2 Corpus

### 3.2.1 SOP Documents

The document corpus comprises four SOP scenarios authored for this study, spanning three enterprise domains:

| Scenario | Domain | Key Process Features |
|---|---|---|
| Vendor Onboarding | Procurement | Sequential steps, parallel compliance screening, rework loop, mixed human/system tasks |
| IT Incident Management | ITSM | Decision tree, escalation hierarchy, multiple rework paths, shared resources |
| Employee Leave Approval | HR | Approval chain, manager discretion, system automation steps |
| Legacy IT Purchase | Procurement | Passive voice, coreferences, run-on sentences, implicit control flow, no metadata header |

The first three SOPs use controlled vocabulary — imperative mood, explicit control-flow markers — and exercise the full feature surface: sequential flow, nested decisions, negation-pair continuations, parallel blocks, explicit and implicit joins, rework loops, and mixed human/system task identification. The Legacy IT Purchase SOP represents the opposite extreme: a real-world messy document with implicit structure, included as the primary external-validity proxy.

### 3.2.2 Event Logs

Two real and five synthetic event logs accompany the SOP scenarios:

| Log | Cases | Variants | Notes |
|---|---|---|---|
| Vendor Onboarding events | 250 | 4 | Planted parallel pair, rework loop, queue bottleneck |
| IT Incident Management events | 300 | 4 | Rework loop, escalation hierarchy |
| IT Incident Management XES | 300 | 4 | Same data in IEEE XES format |
| Invoice-to-Pay (synthetic) | 150 | 3 | Sequential with decision |
| Order-to-Cash (synthetic) | 149 | 5 | Parallel pair, noise variants |
| Procurement (synthetic) | 150 | 4 | Rework loop, noise variants |
| Noisy synthetic | 150 | 5 | High-noise variant mix, 40% trace deviation |

The five synthetic logs (generated by `inductive/datagen.py`) carry **planted ground truth**: known bottleneck activities with planted median wait times and rework rates, known rework loop activities with planted rework probabilities, and known parallel activity pairs. The seeded simulator ensures deterministic regeneration: given the same seed, the same log is reproduced.

### 3.2.3 Scope Limitations

1. **Controlled vocabulary** — the three primary SOPs use explicit markers. The Legacy IT Purchase SOP (F1 = 0.10 for E1) partially addresses external validity. The gap between controlled and real-world SOP quality is the main threat to validity.
2. **English language** — all documents and logs are English-language.
3. **Single annotator** — gold models were produced by the author. No inter-annotator agreement study has been conducted.

## 3.3 Gold Standard Annotation

For each SOP, a reference (gold) BPMN model was produced by reading the SOP text and constructing the process model that represents the intended reading. The annotation criteria:

- **Activities:** Every task step explicitly described in the SOP is an activity. Implicit steps (understandable but not stated) are excluded.
- **Actors (Lanes):** Every distinct role or system identified in the SOP. Lane names are standardised against a controlled vocabulary.
- **Gateways:** XOR where the SOP contains decision language (if, otherwise, in case) or branch-dependent continuation. AND where the SOP contains parallel language (while, meanwhile, at the same time).
- **Rework loops:** Annotated where the SOP contains a return-to construct that creates a backward edge.
- **Task types:** userTask (human-performed), serviceTask (automated system action), sendTask (outgoing communication), manualTask (physical action without system).

Gold models are stored as `ProcessModel` JSON in `eval/gold/`. The annotation is co-designed with the corpus: the primary SOPs use controlled vocabulary, and the gold model is the intended reading of that vocabulary. Consequently, an F1 of 1.00 for E1 on the primary trio is the **ceiling under controlled vocabulary**, not a general result.

## 3.4 Extractor Configurations

Five extractor configurations are evaluated:

| Config | Source | Mechanism | Orchestration | Soundness Guarantee |
|---|---|---|---|---|
| E1 | SOP text | Offline deterministic rule parser | BuiltinEngine | Structural validation only |
| E2 | SOP text | Schema-guided LLM (`qwen/qwen3-8b`), single-shot | BuiltinEngine | Validation + single-pass |
| E3 | SOP text | E2 + bounded validate→feedback retry (max 2) | LangGraphEngine | Validation + bounded retry |
| E4 | Event log | DFG discovery with frequency thresholding | BuiltinEngine | None (frequency heuristic) |
| E6 | Event log | Leemans-style xor→seq→par→loop cut hierarchy | BuiltinEngine | Sound by construction |

**E1** uses explicit control-flow markers: `if/otherwise` for XOR, `while/meanwhile` for AND, `returns to` for rework. Actor detection uses a role registry plus generic role grammar.

**E2** uses a schema-guided prompt with the full `ProcessModel` JSON schema, 3–5 in-context examples, BPMN semantic instructions, and a JSON-only output requirement. OpenAI-compatible API via OpenRouter (`qwen/qwen3-8b`, temperature 0).

**E3** extends E2 with a validate-and-retry loop managed by the LangGraphEngine. If structural validation fails, the validator's error list is formatted as feedback and the LLM is re-prompted. Maximum 2 retries.

**E4** computes the directly-follows graph from the event log, applies a frequency threshold (default 0.01), induces XOR gateways from the out-degree of activity nodes, and detects AND gateway pairs via the footprint discriminator (mutual A→B and B→A only when A and B share entry/exit context outside the pair).

**E6** applies the Leemans-style cut hierarchy (xor → seq → par → loop) recursively. A soundness guard rejects parallel cuts when any trace touches only one side of the partition. Flower model (accepts all traces) is returned if no cut applies.

## 3.5 Measures

### 3.5.1 Extraction Quality Measures

All extraction measures use the `evaluate_model()` function from the evaluation harness.

**Task recovery** uses greedy token-stem matching with threshold 0.5. The extracted task name and gold task name are stemmed; a match is accepted if the Jaccard similarity of the stemmed token sets ≥ 0.5. Task precision = matched tasks / extracted tasks; task recall = matched tasks / gold tasks; task F1 = harmonic mean.

**Actor recovery** uses containment matching: a gold actor is matched if a similar actor name appears in the extracted model (fuzzy containment, e.g., "Finance" ~ "Finance Manager"). Actor F1 = containment-harmonic mean.

**Gateway error** = absolute difference in XOR gateway count plus absolute difference in AND gateway count between extracted and gold models.

**Rework error** = absolute difference in rework loop count between extracted and gold models.

### 3.5.2 Discovery Soundness Measures

**Token-replay fitness** = cases accepted / total cases. A case is accepted if the replay engine can fire all its events without deadlock, token deficit, or token overflow. Bounded backtracking search is used.

**Variant coverage** = variants accepted / total variants. A variant is a unique trace in the log.

**Model size** = number of task nodes and total gateway count (XOR + AND).

### 3.5.3 Conformance Measures

**DF precision** = fraction of documented model's directly-follows relations found in the enacted model's directly-follows relations.

**DF recall** = fraction of enacted model's directly-follows relations found in the documented model's directly-follows relations.

Activities are aligned by greedy token-stem matching (threshold 0.5) before DF comparison.

## 3.6 Statistical Analysis

For E1 vs E2 vs E3, the primary analysis is descriptive (mean, standard deviation across 5 seeds for E2 and E3). The E1 extractor is deterministic (no variance). Where significance testing is applicable (E2 vs E3), a paired t-test or Wilcoxon signed-rank test is used with α = 0.05. Effect size is reported as Cohen's d.

For discovery comparisons (E4 vs E6), fitness differences are reported as percentage-point gaps per log; the mean gap across logs is reported as a summary statistic.

Confidence intervals are computed via bootstrap resampling (1,000 resamples, bias-corrected percentile method) for the E2 and E3 seed runs.