# Zenodo Preprint Upload — Copy-Paste Cheat Sheet
## (Upload thesis/thesis.pdf → fill the form with the text below)

**Upload type:** Publication
**Publication type:** Working paper / Preprint

---

**Title:**
```
LLM-Assisted Business Process Discovery: Combining Multi-Agent Extraction with Sound Process Mining for Automated BPMN Reconstruction
```

**Creators / Authors:** (Zenodo should auto-suggest you; add your ORCID so it links)
```
Aashish Kumar Mahato — Independent Researcher — ORCID: 0009-0007-8952-6357
```

**Description / Abstract:**
```
This thesis investigates whether heterogeneous process knowledge sources — unstructured Standard Operating Procedure (SOP) text and structured event logs — can be fused into valid, conformance-checked BPMN 2.0 models by an automated pipeline. Five extractor configurations are implemented in the ProcessMind framework: a deterministic rule parser (E1), single-shot LLM extraction (E2), LLM with self-correction (E3), DFG discovery (E4), and an Inductive Miner (E6). A one-command evaluation harness enables comparative evaluation under identical conditions on a four-SOP/seven-log corpus. Key findings: the rule parser achieves perfect extraction on controlled vocabulary (F1=1.00) but collapses on unstructured text (F1=0.10); the LLM recovers substantially on unstructured text (F1=0.48-0.50); the self-correction loop adds 0.02-0.09 F1 improvement on the genuine LLM extraction path; the Inductive Miner is empirically sound-by-construction (fitness = variant coverage across all logs, up to 0.947 on a 40% noisy log vs 0.667 for DFG); and bottleneck-grounded To-Be recommendations reduce estimated critical path by 17-31%. All code, data, and the one-command reproducible harness are openly available.
```

**Keywords** (add each, press Enter after each):
```
business process management
BPMN
process mining
large language models
multi-agent systems
process discovery
conformance checking
```

**License:** `Creative Commons Attribution 4.0 International (CC-BY-4.0)`

**Related identifiers** (optional but good — add the GitHub repo):
```
https://github.com/aashish254/processmind   —  is supplemented by / is compiled from
```

**Publication date:** 2026-09-20

---

## After you click "Publish"
Copy the DOI Zenodo gives you (e.g. `10.5281/zenodo.XXXXXXX`) and either:
- paste it to me and I'll add it to the README + push, or
- edit `README.md`, replace both `10.5281/zenodo.XXXXXXX` in the DOI badge, then `git add -A && git commit -m "Add Zenodo DOI" && git push`.
