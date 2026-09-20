# Chapter 1: Introduction

Business process knowledge in enterprises exists in two fundamentally different forms that rarely agree with each other. The **documented process** — captured in Standard Operating Procedures, runbooks, policy documents, and onboarding guides — is abundant, intent-rich, and written for human readers. The **enacted process** — recorded as event logs in ERP, CRM, and ITSM systems — is factual, structured, and machine-readable, but blind to intent. Reconciling the two is the daily work of business and systems analysts, and it is expensive: mapping a single process typically takes days to weeks of interviews, workshops, and iterative validation with process owners, and the result begins drifting out of date as soon as work practice changes.

Process mining offers an established algorithmic answer for the enacted side. Directly-follows graph (DFG) discovery and the Inductive Miner family of algorithms can extract structured process models from event logs with formal correctness guarantees. However, neither branch of process mining addresses the documented side, and neither can reconcile documented intent with enacted practice.

Large language models change this picture. Recent work on LLMs for business process management suggests they can read unstructured operational text and produce structured process descriptions. What is missing is a principled framework that treats LLM extraction, classical discovery, and log-document reconciliation as *comparable, measurable alternatives within one pipeline* — rather than ad-hoc demonstrations evaluated incommensurably.

---

## 1.1 Problem Statement

This thesis addresses the following problem:

> Can heterogeneous process knowledge sources — unstructured SOP text and structured event logs — be fused into valid, conformance-checked BPMN 2.0 models by an automated pipeline, and how do LLM-based extractors compare with deterministic process-mining baselines on validity, fidelity and conformance?

This problem has three components:
1. **Automated extraction** — converting SOP text into structurally valid BPMN without human modelling effort.
2. **Automated discovery** — extracting process structure from event logs using established and sound-by-construction algorithms.
3. **Automated reconciliation** — detecting and quantifying documented-versus-enacted drift, and generating defensible As-Is → To-Be improvement recommendations.

---

## 1.2 Research Questions

The thesis investigates five research questions:

**RQ1:** To what extent can unstructured SOP text be converted into structurally valid BPMN 2.0 models without human modelling effort?

**RQ2:** How does a deterministic rule-based extractor compare with an LLM-based multi-agent extractor on task, actor, and gateway recovery?

**RQ3:** Does multi-agent orchestration (model → validate → critique → retry) measurably improve output quality over single-prompt extraction?

**RQ4:** How do DFG-based discovery and sound block-structured discovery (Inductive Miner) trade off fitness, precision, and model complexity on identical event logs?

**RQ5:** Can documented-versus-enacted drift be detected and quantified automatically to produce defensible As-Is → To-Be recommendations?

---

## 1.3 Aim and Objectives

The aim of this thesis is to design, implement, and evaluate a unified pipeline that handles both documented and enacted process sources, and to provide the first comparative empirical evaluation of deterministic, LLM-based, and mining-based extraction under identical conditions.

The specific objectives are:

1. Build a multi-agent pipeline (`process_miner/`) that extracts BPMN from SOP text via deterministic rules and via LLM, discovers process models from event logs via DFG and Inductive Miner, validates all outputs structurally, and detects conformance drift between documented and enacted models.
2. Implement a one-command evaluation harness that runs all extractor configurations on identical inputs and reports identical measures, enabling direct comparison.
3. Evaluate the five extractor configurations on a corpus of four SOP scenarios and seven event logs (including synthetic benchmark logs with planted ground truth).
4. Answer RQ1–RQ5 with empirical evidence, interpret findings against the literature, and identify the most promising directions for future work.

---

## 1.4 Contributions

The thesis makes four primary contributions:

1. **A unified benchmark (E1–E6)** comparing five extractor configurations — deterministic rule parser, single-shot LLM, LLM with self-correction, DFG discovery, and Inductive Miner — under identical measures on identical inputs. This is the first study to evaluate these approaches commensurably.

2. **Empirical evidence on the self-correction question.** Whether bounded validate-and-retry self-correction yields statistically significant improvement over single-shot LLM extraction is an open question in the emerging LLM-BPM literature. This thesis provides the first controlled empirical answer.

3. **A sound-by-construction hybrid architecture.** Confining the LLM to semantic enrichment while deriving control-flow structure from the provably-sound Inductive Miner prevents the LLM from being the source of structural invalidity. The empirical confirmation (fitness = variant coverage across all logs) validates this design claim.

4. **Automated, quantitatively grounded As-Is → To-Be transformation.** Bottleneck evidence from event logs drives improvement recommendations; the output is a valid BPMN model, not a textual suggestion.

---

## 1.5 Thesis Structure

This thesis is structured as follows:

- **Chapter 2** reviews the literature on business process management, BPMN, process mining, text-to-process extraction, and LLMs for business process management, identifying the research gap.
- **Chapter 3** describes the research methodology — the comparative evaluation design, corpus, gold standard, extractor configurations, measures, and statistical analysis plan.
- **Chapter 4** describes the system design — the pipeline architecture, agent designs, BPMN engineering, process mining pathway, and orchestration engines.
- **Chapter 5** presents the empirical results — extraction quality for E1/E2/E3, discovery soundness for E4/E6, and conformance findings for RQ5.
- **Chapter 6** discusses the findings, threats to validity, limitations, and implications for research and practice.
- **Chapter 7** concludes the thesis, summarises findings and contributions, acknowledges limitations, and outlines future work.