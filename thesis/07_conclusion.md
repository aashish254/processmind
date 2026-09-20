# Chapter 7: Conclusion

This thesis investigated the question of whether heterogeneous process knowledge sources — unstructured SOP text and structured event logs — can be fused into valid, conformance-checked BPMN 2.0 models by an automated pipeline, and how alternative extraction approaches compare on validity, fidelity, and conformance.

---

## 7.1 Summary of Findings

**RQ1 (Automated SOP → BPMN conversion):** The offline rule parser achieves perfect extraction (F1 = 1.00) on controlled-vocabulary documents and collapses (F1 = 0.10) on unstructured real-world text. Automated extraction is viable for well-structured enterprise SOPs; its practical ceiling on unrestricted documents is substantially lower.

**RQ2 (Rule vs LLM comparison):** The rule parser dominates on controlled vocabulary (F1 = 1.00 vs 0.71–0.87 for `qwen/qwen3-8b`). The LLM dominates on unstructured documents (F1 = 0.48–0.50 vs 0.10 for the rule parser). The optimal extraction approach is document-dependent; a document quality classifier could route documents to the appropriate extractor automatically.

**RQ3 (Self-correction effectiveness):** The bounded validate-and-retry self-correction loop improves over single-shot extraction on all four documents (F1 gains of 0.02–0.13). The largest gain is on vendor onboarding (0.87 → 1.00, the only case where E3 fully recovers the omitted tasks). The self-correction loop corrects actor assignments more reliably than it recovers omitted tasks.

**RQ4 (DFG vs Inductive Miner):** The Inductive Miner (E6) consistently matches or exceeds the DFG miner (E4) on token-replay fitness across all seven event logs. E6's fitness = variant coverage property holds throughout, confirming the soundness-by-construction guarantee empirically. E4's frequency thresholding causes fitness losses of up to 33% on noisy logs, but produces more compact models (fewer gateways). The trade-off is real and application-dependent.

**RQ5 (Automated drift detection and To-Be generation):** Documented-versus-enacted drift is detected and quantified at both the activity and control-flow levels. Token-stem matching achieves 50–82% DF recall, with vocabulary drift as the dominant degradation source. Bottleneck evidence from event logs (queue wait times, rework rates) successfully grounds To-Be recommendations: 17–31% estimated critical path reduction, 8–13 percentage-point automation improvement.

---

## 7.2 Contributions

This thesis makes four primary contributions:

1. **A unified benchmark (E1–E6)** comparing deterministic, LLM-based, and mining-based extraction under identical measures on identical inputs. No existing study performs this comparison; the evaluation harness enables full replication.

2. **Empirical evidence on the self-correction question.** The bounded validate-and-retry loop yields measurable but uneven improvement. The correction mechanism addresses structural errors more reliably than extraction completeness errors — a finding that informs the design of future self-correcting extraction systems.

3. **A sound-by-construction hybrid architecture.** Separating control-flow structure (deterministic, provably-sound mining) from semantic enrichment (LLM) is the right architectural choice for a hybrid pipeline. E6's fitness = coverage property across all seven logs confirms this empirically.

4. **Automated, quantitatively grounded As-Is → To-Be transformation.** The bottleneck evidence from event logs drives the improvement recommendations, and the output is a valid BPMN artifact — not a textual suggestion. This closes the loop from discovery to improvement recommendation within a single automated pipeline.

---

## 7.3 Limitations

The corpus is small (4 SOPs, 7 logs) and partially controlled. The F1 = 1.00 ceiling for the rule parser on the curated trio is not representative of the full distribution of real-world SOP quality. The legacy IT Purchase SOP (F1 = 0.10) partially addresses this, but a larger, independently annotated corpus is needed for robust generalisability claims.

The LLM experiments were conducted with `qwen/qwen3-8b` only. Results will differ for GPT-4o, Claude Sonnet, and other models. The finding that the rule parser dominates on controlled vocabulary documents may not hold for more capable models.

The gold standard models were produced by the author without inter-annotator agreement verification. The ceiling result for E1 should be interpreted as the ceiling under the author's reading of the text.

---

## 7.4 Future Work

Four extensions are identified, in order of priority:

1. **Evaluation at scale.** Running E1–E6 on the BPI Challenge event-log suite and a corpus of 10–20 real, independently collected SOP documents would substantially strengthen the external validity of the findings. An ethics-approved protocol for SOP collection is needed.

2. **Embedding-based activity matching.** Replacing token-stem similarity (threshold 0.5) with sentence-embedding similarity would address the vocabulary drift problem that limits conformance detection. An ablation against the lexical baseline would quantify the improvement.

3. **Content-driven self-correction.** A supplementary feedback mechanism that compares extraction output against source text to identify missed sentences would complement the structural validation feedback loop. An ablation (structural-only vs content-only vs combined) would isolate each mechanism's contribution.

4. **Selective extraction routing.** A document quality classifier (scoring vocabulary explicitness) could route documents to the optimal extractor (E1 for well-structured, E2/E3 for unstructured) automatically, optimising the quality-cost trade-off at the document level.

---

## 7.1 Closing Remarks

The analyst bottleneck — days to weeks of manual effort to produce a first draft process map — is real and costly. This thesis demonstrates that the bottleneck can be partially automated: a first draft BPMN model from a well-structured SOP is achievable in milliseconds, and from an unstructured SOP in minutes. The gap between the documented process and the enacted process is measurable. The improvement recommendations are grounded in quantitative evidence.

The most important finding is that the choice of extraction method matters enormously, and that the right choice depends on the document. The deterministic rule parser is fast and perfect for well-structured documents. The LLM is the only viable option for unstructured documents. The Inductive Miner is the trustworthy choice for event logs when soundness is required. The unified benchmark developed in this thesis makes these trade-offs measurable rather than anecdotal — and that measurability is the foundation for building better hybrid systems.

The source code, evaluation harness, experimental data, and this thesis document are all available in the project repository.