# Chapter 6: Discussion

This chapter interprets the empirical findings presented in Chapter 5, positions them within the literature reviewed in Chapter 2, examines threats to validity, acknowledges limitations, and outlines the implications for research and practice.

---

## 6.1 Interpretation of Findings

### 6.1.1 The Rule Parser's Double-Edged Determinism

The offline rule parser (E1) achieves perfect extraction (F1 = 1.00) on controlled-vocabulary documents — and near-zero (F1 = 0.10) on unstructured text. This is not a bug; it is a feature of the design. The rule parser is a pure implementation of explicit marker detection: it finds what it is designed to find, and finds nothing when the markers are absent.

The literature on text-to-process extraction (Chapter 2, §2.3) predicted this behaviour. Pre-LLM approaches were characterised by "moderate precision on well-structured documents and sharp degradation on informal text" (van der Aa et al., 2019). The ceiling result for E1 (F1 = 1.00 on the curated trio) is the maximum achievable for a marker-dependent extractor on documents authored with those markers. The floor result (F1 = 0.10 on the legacy SOP) is the honest external-validity datum: real-world documents are messy.

The implication is not that E1 should be abandoned, but that E1 and E2/E3 should be deployed selectively. A document quality classifier (a lightweight heuristic that scores vocabulary explicitness) could route documents to E1 or E2 automatically, choosing the faster (E1, ~0 seconds) path for well-structured documents and the more robust (E2, ~60–100 seconds) path for others.

### 6.1.2 The LLM's Extraction Completeness Problem

The `qwen/qwen3-8b` model's primary failure mode on controlled vocabulary documents is task omission (recall = 0.62–0.77), not structural invalidity. This is a notable finding because the dominant concern in the LLM-BPM literature is structural validity — whether LLM-generated BPMN models deadlock or have unreachable nodes (Bellan et al., 2023). The model produces structurally valid BPMN (gateway counts are the primary structure error) but does not recover all the tasks in the text.

This suggests that the LLM is performing a summarising extraction — identifying the most salient activities — rather than a complete extraction. The self-correction loop (E3) partially addresses this: on vendor onboarding, it recovers the full task set (R = 1.00 vs 0.77 for E2). But on the IT incident and employee leave documents, the loop recovers only a fraction of the omissions. This is consistent with the finding in the self-correction literature that marginal returns diminish after the second retry (Shinn et al., 2024) — the model does not know what it missed, only what it got wrong.

### 6.1.3 The Self-Correction Loop: Real but Uneven

E3 improves over E2 on all four documents (F1 gains of 0.02–0.13). The loop corrects actor assignments most reliably (IT incident: Actor F1 0.89 → 1.00; Legacy: 0.83 → 1.00). Task recovery improves less consistently — the feedback from the validator tells the model which nodes are structurally problematic, not which tasks are absent.

This suggests a design improvement: the current self-correction loop is feedback-driven (validator → LLM) rather than content-driven. A content-driven supplement — comparing the extraction output against the source text to identify missed sentences — might yield larger gains. This is identified as future work in §6.5.

The cost-benefit analysis is mixed: E3 adds 20–40% to the runtime of E2 (on top of the LLM call latency) for F1 gains of 0.02–0.13. On controlled vocabulary documents where E1 dominates (and E1 runs in 0 seconds), E3 is not cost-effective. On unstructured documents where E1 fails, E3 is the only viable option.

### 6.1.4 The Inductive Miner's Soundness Dividend

E6's fitness equals its variant coverage on all seven logs — the mathematical signature of soundness-by-construction. Every trace the model accepts is valid behaviour; every invalid trace is rejected. This is not an accident of the particular logs, but a property of the algorithm: language-preserving cuts guarantee this relationship.

The practical dividend is that E6 can be trusted to produce a model that, when simulated, will not deadlock or produce tokens that cannot be consumed. For downstream uses — bottleneck analysis, what-if simulation, conformance checking — this soundness guarantee means the model is safe to use as an analytical artifact without post-hoc verification.

E4's frequency-thresholded DFG trades this guarantee for readability. On the noisy log (40% trace deviation), E4's model is arguably more useful to an analyst than E6's: it shows only the dominant path, filtering out the noise. The trade-off is real and document-dependent. E6 is appropriate when behavioural completeness matters; E4 is appropriate when model readability is the priority.

### 6.1.5 Vocabulary Drift as the Dominant Conformance Problem

IT incident (82% DF recall) and vendor onboarding (50% DF recall) differ primarily in vocabulary alignment, not process structure. The activities in the IT incident SOP and log share surface vocabulary ("Investigate Issue", "Apply Standard Fix"); the activities in the vendor onboarding SOP and log do not ("Perform Background Screening" vs "Compliance Screening"). The 32 percentage-point gap in recall is attributable to this mismatch.

This confirms the limitation of token-stem matching for activity alignment and motivates the embedding-based approach identified in the research plan: sentence-embedding similarity (e.g., using a model fine-tuned on process terminology) would align "Perform Background Screening" with "Compliance Screening" at high similarity even though their lexical overlap is low.

---

## 6.2 Threats to Validity

### 6.2.1 Construct Validity

*Do the measures capture what the research questions ask?*

Task P/R/F1 measures are standard information retrieval metrics, but they assess *extraction completeness* against a reference model — not the *business process quality* of the extracted model. An F1 of 1.00 means the model matches the gold annotation; it does not mean the gold annotation perfectly represents the true underlying process. This is the standard limitation of using F1 against a reference standard.

Token-replay fitness is an established process mining metric (van der Aalst et al., 2012), but it is a necessary but not sufficient condition for model quality — a model that accepts all traces may still be overly permissive (the flower model has fitness = 1.0 for any log). Variant coverage is reported alongside fitness to address this.

Conformance DF precision and recall are indicators, not alignment-based fitness measures. The literature notes that alignment-based fitness is more precise but computationally expensive; the bounded replay search used here is a pragmatic compromise.

### 6.2.2 Internal Validity

*Are the observed differences caused by the extractor configuration, or by confounding factors?*

The E2 vs E3 comparison is subject to a confound: E3 makes up to 3 LLM calls (initial + 2 retries), while E2 makes 1. Any quality improvement in E3 could be attributed to additional LLM calls rather than the self-correction mechanism specifically. A controlled comparison with an E2+passive-retry condition (calling the LLM the same number of times without validation feedback) would isolate the effect of the feedback mechanism from the effect of additional calls.

The LLM is non-deterministic even at temperature 0, due to implementation-level nondeterminism in modern LLMs. Multi-seed runs (5 seeds) with reported confidence intervals mitigate this but do not eliminate it. A fully rigorous comparison would require 30+ seeds per condition.

### 6.2.3 External Validity

*Can the findings be generalised beyond the study corpus?*

The curated SOP corpus uses controlled vocabulary — F1 = 1.00 for E1 on the curated trio is a ceiling, not a typical result. The legacy IT Purchase SOP (F1 = 0.10 for E1) is a partial antidote, but a single messy document cannot characterise the full distribution of real-world SOP quality.

The LLM experiments were conducted with `qwen/qwen3-8b` (8B parameters, OpenRouter API). Results will differ for GPT-4o, Claude Sonnet, Gemini, and other models. The relative ordering of findings (E1 dominates on controlled vocab; LLM dominates on unstructured; self-correction adds modest gains) may generalise, but the specific F1 values will not.

The event logs are largely synthetic (5 of 7 logs are generated by the seeded simulator). The planted ground truth enables evaluation against known answers, but the synthetic logs do not capture the multi-tenancy, concept drift, and lifecycle complexity of real enterprise event logs.

### 6.2.4 Reliability

*Can the results be replicated?*

The rule parser (E1), DFG miner (E4), and Inductive Miner (E6) are deterministic. Identical inputs produce byte-identical outputs; all seeds and parameters are documented. The LLM experiments report 5-seed means with standard deviations, providing a replication target.

---

## 6.3 Limitations

1. **Corpus scope.** Four SOPs and seven event logs are insufficient to characterise the full distribution of real-world document and log quality. The gap between the controlled-vocabulary results (F1 = 1.00) and the unstructured result (F1 = 0.10) is the honest characterisation of the current corpus's scope.

2. **Gold standard co-design.** The gold models were produced by the author. No inter-annotator agreement study has been conducted. The F1 ceiling (1.00 on the curated trio) should be interpreted as the extraction system's ceiling under the author's reading of the text — a different annotator might produce a different gold model.

3. **Single LLM model.** The E2/E3 experiments used `qwen/qwen3-8b`. This model was chosen for availability and speed; it is not the state-of-the-art for structured extraction (GPT-4o, Claude Sonnet are larger and generally more capable). The thesis should be interpreted as reporting results for one open-weight 8B model, not for LLMs in general.

4. **No real-world SOP corpus.** All four SOPs were authored for the study. An evaluation on real, publicly available SOP documents (e.g., from government procurement portals, IT service management libraries) would provide stronger external validity evidence.

5. **Conformance indicator limitation.** The directly-follows precision and recall are described as "indicators" rather than fitness measures, following the nomenclature in the source code. More rigorous alignment-based fitness would strengthen the conformance results.

6. **Token-replay boundedness.** The replay search is bounded (limited backtrack depth). For very large logs with complex interleaving, the bounded search may fail to find valid alignments that exist. The bounding parameter was not tuned in this study.

---

## 6.4 Implications

### 6.4.1 For Research

**The unified benchmark fills a gap.** The absence of a unified benchmark comparing deterministic, LLM-based, and mining-based extraction under identical measures was identified in the literature review. E1–E6 with the evaluation harness provides this benchmark. Future researchers can extend it with additional extractor configurations, additional corpora, and additional measures.

**The self-correction question is answered (partially).** The bounded self-correction loop yields measurable but uneven improvement. The loop corrects structural errors more reliably than it recovers omitted tasks. This suggests that self-correction should be complemented with content-comparison feedback (comparing extraction output against source text) rather than relying solely on validation feedback.

**The soundness-by-construction architecture is empirically validated.** E6's fitness = coverage property holds across all seven logs, confirming that separating structure discovery from semantic enrichment is the right architectural choice for a hybrid pipeline.

### 6.4.2 For Practice

**The pipeline can produce a first draft BPMN from an SOP in seconds.** The offline rule parser runs in milliseconds; the LLM path runs in 1–2 minutes. For well-structured documents (the majority in formal enterprise settings), E1 produces a complete, structurally valid BPMN model without human intervention.

**The As-Is / To-Be transformation is automatable.** The bottleneck evidence from event logs grounds the improvement recommendations quantitatively, and the To-Be model is itself a valid BPMN artifact. An analyst can review the recommended changes, modify or reject them, and export the result to a modelling tool.

**The vocabulary gap is the main obstacle to fully automated conformance checking.** The 32-percentage-point gap in DF recall between IT incident and vendor onboarding — driven entirely by vocabulary mismatch — shows that aligning SOP language with log language is the bottleneck for automated drift detection. Embedding-based matching would address this directly.

---

## 6.5 Future Work

The three axes identified in the research proposal are supported by the findings:

1. **Evaluation at scale.** The current corpus (4 SOPs, 7 logs) is insufficient for characterising real-world performance. The highest-priority extension is to run E1–E6 on the BPI Challenge event-log suite (real-world industrial logs) and a corpus of 10–20 real SOP documents collected under an ethics-approved protocol.

2. **Embedding-based activity matching.** The token-stem similarity threshold of 0.5 is the identified weakness in the conformance alignment. Replacing it with sentence-embedding similarity (e.g., using a domain-adapted embedding model) would align "Perform Background Screening" with "Compliance Screening" at high similarity, improving the DF recall on vocabulary-mismatched SOP-log pairs.

3. **Content-driven self-correction.** The current self-correction loop uses validation feedback (structural errors) but not content feedback (missed source-text sentences). A second feedback loop that compares extraction output against source text to identify uncovered sentences would complement the structural feedback loop. An ablation comparing structural-only, content-only, and combined feedback would quantify the marginal contribution of each.

A fourth extension, motivated by the discussion above:
4. **Selective extraction routing.** A document quality classifier that scores vocabulary explicitness could automatically route documents to E1 (fast, perfect on structured) or E2/E3 (slower, robust on unstructured), optimising the speed-quality trade-off at the document level.