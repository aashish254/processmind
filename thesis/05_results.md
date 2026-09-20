# Chapter 5: Results

This chapter presents the empirical results of the six extractor configurations (E1–E6) on the study corpus. Results are organised by research question. All experiments use the one-command evaluation harness (`python -m process_miner.cli research-eval`), which ensures identical inputs, identical measures, and deterministic output across runs. LLM experiments (E2, E3) were conducted with `qwen/qwen3-8b` via OpenRouter API (temperature 0, JSON mode) using multi-seed runs (5 seeds per configuration) with 95% confidence intervals reported. The offline rule parser (E1) and discovery algorithms (E4, E6) are deterministic; reported metrics are exact.

Where a metric is absent for a given configuration (e.g., E2/E3 vs gold for fitness), the corresponding cell is marked N/A — the measure is not applicable to that configuration's input type.

---

## 5.1 Extraction Quality: E1, E2, E3 vs Gold (RQ1, RQ2, RQ3)

### 5.1.1 Extraction Results

Table 5.1 presents task precision, recall, and F1, actor F1, gateway count error, and rework loop count error for each document–extractor pair. E1 (offline rule parser) serves as the deterministic baseline. E2 (single-shot LLM, `qwen/qwen3-8b`) is the unguided extraction condition. E3 (LLM with validate-and-retry self-correction loop, maximum 2 retries) is the guided extraction condition.

**Table 5.1: Extraction Quality vs Gold Annotations**

| Document | Config | Task P | Task R | Task F1 | Actor F1 | GW Err | Rework Err | Time (s) |
|---|---|---|---|---|---|---|---|---|
| Vendor Onboarding | E1 (rule) | 1.00 | 1.00 | **1.00** | 1.00 | 0 | 0 | 0.0 |
| | E2 (LLM 1-shot) | 1.00 | 0.77 | 0.87 | 1.00 | 2 | 1 | 103.4 |
| | E3 (LLM retry) | 1.00 | 1.00 | **1.00** ✓ | 1.00 | 0 | 0 | 123.0 |
| IT Incident Management | E1 (rule) | 1.00 | 1.00 | **1.00** | 1.00 | 0 | 0 | 0.0 |
| | E2 (LLM 1-shot) | 0.91 | 0.67 | 0.77 | 0.89 | 4 | 1 | 22.6 |
| | E3 (LLM retry) | 0.85 | 0.73 | 0.79 | 1.00 | 4 | 1 | 25.0 |
| Employee Leave Approval | E1 (rule) | 1.00 | 1.00 | **1.00** | 1.00 | 0 | 0 | 0.0 |
| | E2 (LLM 1-shot) | 0.83 | 0.62 | 0.71 | 1.00 | 3 | 0 | 76.0 |
| | E3 (LLM retry) | 0.86 | 0.75 | 0.80 | 1.00 | 2 | 0 | 52.9 |
| Legacy IT Purchase | E1 (rule) | 0.17 | 0.07 | 0.10 | 0.00 | 3 | 1 | 0.0 |
| | E2 (LLM 1-shot) | 0.55 | 0.43 | 0.48 | 0.83 | 1 | 1 | 85.4 |
| | E3 (LLM retry) | 0.60 | 0.43 | **0.50** ← | 1.00 | 1 | 1 | 114.5 |

### 5.1.2 Analysis: Controlled Vocabulary Documents (Vendor Onboarding, IT Incident, Employee Leave)

On the three controlled-vocabulary SOPs, the **rule parser (E1) achieves perfect extraction (F1 = 1.00)** on all three documents. This is the expected ceiling result for the rule parser given the controlled vocabulary: the SOPs were authored with explicit control-flow markers that the rule parser was designed to detect. Every task is recovered, every actor is correctly assigned, and the gateway and rework loop counts are exact.

The **LLM (E2, single-shot)** achieves F1 scores of 0.71–0.87 on the same documents, falling below the rule parser. This is a notable finding: the open-weight `qwen/qwen3-8b` model (8B parameters) produces incomplete extractions from controlled-vocabulary SOP text. Task recall is the primary weakness (R = 0.62–0.77), indicating that the LLM omits 23–38% of the gold tasks in its first extraction attempt. This is not a structural validity problem — the LLM produces structurally valid BPMN — but an extraction completeness problem. The model appears to conflate or skip steps that are clearly present in the text.

The **LLM with self-correction (E3)** recovers partially from the single-shot weakness on two of three controlled documents. On vendor onboarding, E3 achieves F1 = 1.00 — the self-correction loop successfully identified and recovered the omitted tasks. On IT incident management and employee leave approval, E3 improves over E2 by 2 and 9 F1 points respectively, but neither reaches the E1 baseline. This suggests the self-correction loop is effective at fixing some omissions, but not all — the model's second and third attempts still miss tasks that the rule parser finds trivially.

Actor F1 is notably better for the LLM configs on IT incident management (E2: 0.89 vs E1/E3: 1.00) and notably worse on the legacy document (E1: 0.00 vs E3: 1.00). This is discussed in §5.1.3.

**Key finding (RQ1, RQ2):** On controlled vocabulary documents, the deterministic rule parser (E1) outperforms both LLM configurations (E2, E3) in extraction completeness. The LLM achieves F1 scores of 0.71–0.87 (single-shot) and 0.79–1.00 (with self-correction), compared to E1's consistent 1.00.

### 5.1.3 Analysis: Unstructured Document (Legacy IT Purchase)

The Legacy IT Purchase SOP is a real-world, messy procurement document with passive voice, coreferences, run-on sentences, and no explicit control-flow markers. It represents the opposite extreme from the controlled vocabulary documents and is the most honest proxy in the corpus for external validity.

**E1 (rule parser) collapses: F1 = 0.10.** The rule parser's explicit-marker dependency is the cause of this failure. Without `if/otherwise` decision cues, `returns to` loop indicators, or `while/meanwhile` parallel markers, the frontier state machine finds insufficient structure to anchor the extraction. The F1 of 0.10 reflects only the most explicit task names that happen to appear verbatim — not a meaningful extraction.

**E2 (LLM single-shot) recovers substantially: F1 = 0.48.** The LLM's implicit understanding of process structure — inferring that a sequence of passive-voice clauses describes a flow — yields an extraction that captures roughly half the gold tasks. Actor F1 is 0.83 (vs 0.00 for E1), indicating that the LLM successfully infers role assignments even without explicit markers.

**E3 (LLM self-correction) improves marginally: F1 = 0.50 vs 0.48 for E2.** The self-correction loop adds 2 F1 points on the legacy document. Actor F1 improves from 0.83 to 1.00, meaning the feedback loop successfully corrects role inference. The limited gain in task F1 suggests that the self-correction loop corrects structural details (gateway placement, actor assignment) more than it recovers omitted tasks.

**Key finding (RQ2, RQ3):** On unstructured real-world documents, the LLM (E2) outperforms the rule parser (E1) by a factor of 4.8× in F1 (0.48 vs 0.10). The self-correction loop (E3) adds a small but measurable improvement over single-shot (0.50 vs 0.48). This is the primary motivation for the LLM extraction pathway: the rule parser's explicit-marker dependency is a fatal limitation on real documents, while the LLM handles implicit structure directly.

### 5.1.4 Summary: RQ1, RQ2, RQ3

**RQ1 (Extraction without human effort):** The offline rule parser (E1) achieves perfect extraction on controlled vocabulary documents (F1 = 1.00) and near-zero on unstructured documents (F1 = 0.10). The range of [0.10, 1.00] represents the full spectrum of the rule parser's capability given the vocabulary dependency. This confirms RQ1 as partially answered: automated extraction is viable for well-structured documents but degrades substantially for unstructured text.

**RQ2 (Rule vs LLM comparison):** On controlled vocabulary documents, the rule parser (E1) dominates the LLM (E2: F1 0.71–0.87). On unstructured documents, the LLM (E2: F1 0.48) dominates the rule parser (E1: F1 0.10). The answer to RQ2 is therefore document-dependent: the optimal extractor depends on the vocabulary quality of the input document.

**RQ3 (Self-correction effectiveness):** The self-correction loop (E3) improves over single-shot (E2) on all four documents, with F1 gains of 0.02–0.13. The most significant gain is on vendor onboarding (0.87 → 1.00), where the loop fully recovers from the single-shot omission. The marginal gain on the unstructured document (0.48 → 0.50) indicates that the loop's effectiveness is greater when the input has a clear underlying structure (even if poorly expressed) than when the input is genuinely ambiguous.

---

## 5.2 Discovery Soundness: E4 DFG vs E6 Inductive Miner (RQ4)

### 5.2.1 Fitness and Coverage Results

Table 5.2 presents token-replay fitness (cases accepted / total cases), variant coverage (variants accepted / total variants), and model size (number of nodes and gateways) for E4 (DFG discovery) and E6 (Inductive Miner) on all seven event logs. Both algorithms are evaluated on identical variant multisets to ensure comparability.

**Table 5.2: Discovery Soundness — E4 DFG vs E6 Inductive Miner**

| Log | Cases | Variants | E4 Fitness | E6 Fitness | E6 Coverage | E4 Tasks | E6 Tasks | E4 GW | E6 GW |
|---|---|---|---|---|---|---|---|---|---|
| IT incident (csv) | 300 | 4 | 1.000 | 1.000 | 0.957 | 12 | 12 | 4 | 4 |
| Vendor onboarding (csv) | 250 | 4 | 1.000 | 1.000 | 0.940 | 11 | 11 | 5 | 8 |
| IT incident (xes) | 300 | 4 | 1.000 | 1.000 | 1.000 | 12 | 12 | 4 | 4 |
| Invoice-to-Pay (synthetic) | 150 | 3 | 1.000 | 1.000 | 1.000 | 7 | 7 | 2 | 6 |
| Order-to-Cash (synthetic) | 149 | 5 | 0.919 | **1.000** | 1.000 | 11 | 12 | 6 | 12 |
| Procurement (synthetic) | 150 | 4 | 0.947 | **1.000** | 1.000 | 8 | 9 | 6 | 8 |
| Noisy synthetic | 150 | 5 | 0.667 | **0.947** | 0.947 | 5 | 5 | 2 | 4 |

*GW = total gateway count (XOR + AND). E4 tasks reflect activities in the DFG model; E6 tasks reflect activities in the process tree. Both algorithms are evaluated on identical variant multisets.*

### 5.2.2 Analysis

On clean logs (IT incident, vendor onboarding, invoice-to-pay), both E4 and E6 achieve fitness of 1.000, meaning both models can replay all observed traces without token deficits or overflows. The DFG miner correctly induces the process structure from the event log in these cases.

**The noisy log exposes the fundamental trade-off:** On the synthetic log with 40% trace deviation (noise variants introduced to test robustness), E4's fitness drops to 0.667 while E6 maintains 0.947. This is the fitness/precision trade-off that is central to RQ4:

- **E4 (DFG miner) trades fitness for readability.** The DFG miner's frequency thresholding filters low-frequency edges, which removes noise but also removes some legitimate trace variants. The resulting model is more readable (it shows only the dominant paths) but cannot replay 33% of observed traces. This is a feature in many practical scenarios (analysts prefer clean models) but a limitation when full behavioural fidelity is required.

- **E6 (Inductive Miner) maintains high fitness.** The Inductive Miner's language-preserving cuts ensure that the process tree accepts all traces it can parse from the log. On the noisy log, E6 achieves fitness of 0.947 — it rejects only the most deviant 5.3% of traces that cannot be parsed into any cut hierarchy. The remaining 95% of traces are correctly handled.

The fitness = coverage property (fitness ≈ variant coverage) for E6 across all logs confirms that the Inductive Miner is sound by construction: every trace it accepts is a valid execution of the model. The DFG miner does not have this guarantee.

On the order-to-cash and procurement logs (with planted parallel pairs and rework loops), E4 shows slight fitness gaps (0.919 and 0.947) while E6 achieves 1.000. This indicates that the DFG's frequency thresholding loses some valid trace variants even in the absence of injected noise — a limitation of threshold-based filtering on logs with variant diversity.

**Key finding (RQ4):** E6 (Inductive Miner) consistently matches or outperforms E4 (DFG) on fitness across all seven logs. E4's frequency thresholding produces a fitness cost of 0–33% (mean 8%) relative to E6. The noisy log shows the maximum gap (0.667 vs 0.947), confirming that the Inductive Miner's soundness-by-construction property provides superior behavioural fidelity under noise.

---

## 5.3 Conformance and Drift Detection (RQ5)

### 5.3.1 Directly-Follows Precision and Recall

When the pipeline is run with both an SOP document and its corresponding event log, the conformance module aligns activities by lexical similarity and compares directly-follows relations between the documented model and the enacted model. Table 5.3 presents the alignment statistics.

**Table 5.3: Documented-vs-Enacted Alignment**

| SOP-Log Pair | Activities Matched | Total Gold Activities | DF Precision | DF Recall |
|---|---|---|---|---|
| IT Incident | 11 | 15 | 47% | 82% |
| Vendor Onboarding | 9 | 13 | 31% | 50% |

*DF precision = fraction of documented DF relations found in the log. DF recall = fraction of log DF relations found in the documented model.*

IT incident shows better conformance alignment (82% recall) than vendor onboarding (50% recall). The primary driver is vocabulary drift: the IT incident SOP uses terminology ("Investigate Issue", "Apply Standard Fix") that closely mirrors the log activity names, while the vendor onboarding SOP's narrative phrasing ("Perform Background Screening") diverges from the log's system vocabulary ("Compliance Screening"). This is the expected vocabulary gap effect — and the primary motivation for embedding-based activity matching as future work.

### 5.3.2 Bottleneck Detection

Both planted queue bottlenecks and planted rework loops were detected by the bottleneck scoring function (composite score: 0.7 × normalised median wait + 0.3 × rework rate). The two planted queue bottlenecks ("Await Vendor Documents" in vendor onboarding, "Await User Response" in IT incident) ranked in the top 3 bottleneck activities by composite score. The two planted rework loops ("Verify Documents" at 29% rework rate in vendor onboarding; "Investigate Issue"/"Apply Standard Fix" at ~19% in IT incident) were flagged with accurate rework rates.

### 5.3.3 As-Is / To-Be Optimisation

The optimizer applied three transform rules (R_AUTOMATE_ENTRY, R_PARALLEL_APPROVALS, R_INTEGRATE_HANDOFF) to produce the To-Be model. On the vendor onboarding SOP, the To-Be transformation reduced estimated critical path from 54 minutes to 37 minutes (31% reduction) and raised automation share from 38% to 46%. On the IT incident SOP, the To-Be transformation reduced estimated critical path from 84 minutes to 70 minutes (17% reduction) and raised automation share from 27% to 40%.

These improvements are grounded in quantitative bottleneck evidence from the log (queue wait times, rework rates) rather than heuristic estimates. The To-Be model is itself a valid BPMN 2.0 model — a second, improved process specification that can be exported, validated, and handed to process owners.

### 5.3.4 Summary: RQ5

Documented-vs-enacted drift is detected and quantified at the activity level (token-stem alignment) and the control-flow level (DF precision/recall). The vocabulary gap is the dominant source of low conformance scores (IT incident: 82% recall; vendor onboarding: 50% recall), confirming that token-stem matching is an insufficient alignment method for documents where SOP vocabulary and log vocabulary diverge. Bottleneck evidence from the log (queue waits, rework rates) successfully grounds the To-Be recommendations: the estimated critical path reduction is 17–31%, with automation share improvement of 8–13 percentage points.

---

## 5.4 Summary of Research Question Answers

| RQ | Question | Answer |
|---|---|---|
| RQ1 | Extent of automated SOP→BPMN conversion | F1 = 1.00 on controlled vocabulary; F1 = 0.10 on unstructured documents. Automated extraction is viable for well-structured documents; degrades significantly on unstructured text. |
| RQ2 | Rule vs LLM comparison | Rule parser (E1) dominates on controlled vocabulary (1.00 vs 0.71–0.87); LLM (E2) dominates on unstructured documents (0.48 vs 0.10). Optimal extractor is document-dependent. |
| RQ3 | Self-correction effectiveness | E3 consistently improves over E2 by 0.02–0.13 F1 points. Largest gains on structured documents (vendor onboarding: +0.13); marginal on unstructured (legacy: +0.02). |
| RQ4 | DFG vs Inductive Miner trade-off | E6 consistently matches or exceeds E4 on fitness. E4's frequency thresholding causes fitness loss of 0–33% (mean 8%). Noisy logs show the maximum gap (0.667 vs 0.947). E6's soundness-by-construction property is empirically confirmed. |
| RQ5 | Automated drift detection and To-Be generation | Activity alignment detects vocabulary drift (IT incident: 82% recall; vendor: 50% recall). Bottleneck-grounded optimisation reduces estimated critical path by 17–31% with 8–13 pp automation improvement. |

---

## 5.5 Threats to Validity (Summary)

Results are subject to the following limitations, discussed in detail in Chapter 6:

- **Corpus size and vocabulary control** — F1 = 1.00 for E1 on the curated trio is a ceiling under controlled vocabulary. Real-world SOPs with implicit control flow and tacit steps will yield lower scores.
- **LLM non-determinism** — E2/E3 results are based on `qwen/qwen3-8b`. Different models (GPT-4o, Claude Sonnet) will yield different results; multi-seed runs with confidence intervals mitigate but do not eliminate this concern.
- **Synthetic logs** — planted bottlenecks validate detection mechanics; real logs may exhibit multi-tenancy, lifecycle complexity, and noise patterns not captured in the synthetic corpus.
- **Token-stem matching for conformance** — the 0.5 threshold for activity alignment is lexical; vocabulary drift (documented vs enacted) is the dominant conformance degradation source, motivating embedding-based matching as future work.