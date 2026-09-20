"""E1 vs E2 vs E3 comparison — runs all extractors on all SOPs.

Reproduces the LLM comparison results in the thesis (Table 5.1, Appendix B.2)
by scoring each extractor configuration against the gold annotations.

Usage (from the project root):

    export OPENAI_API_KEY=sk-or-v1-...               # required: any OpenAI-compatible key
    export PM_LLM_BASE_URL=https://openrouter.ai/api/v1   # optional (this is the default)
    export PM_LLM_MODEL=qwen/qwen3-8b                # optional (this is the default)
    ./.venv/bin/python scripts/run_llm_experiments.py

Writes: outputs/llm_comparison.json

Note: the E2/E3 numbers in the thesis were produced with qwen/qwen3-8b via
OpenRouter at temperature 0. The pipeline records the extraction method per
run ("offline-rules" if the modeler fell back to the rule parser,
"llm:openai-compatible" otherwise) — check the "method" field when
interpreting E3 scores, since a fallback run reflects the E1 ceiling rather
than LLM self-correction.
"""
import json
import os
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.chdir(str(PROJECT))

from process_miner.evaluation import evaluate_model
from process_miner.models import IngestedDocument
from process_miner.agents.modeler import ProcessModelerAgent
from process_miner.agents.ingestion import IngestionAgent
from process_miner.llm.providers import build_provider
from process_miner.config import LLMConfig

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    sys.exit(
        "OPENAI_API_KEY is not set. Export any OpenAI-compatible API key first, e.g.:\n"
        "  export OPENAI_API_KEY=sk-or-v1-...\n"
        "  export PM_LLM_BASE_URL=https://openrouter.ai/api/v1\n"
        "  export PM_LLM_MODEL=qwen/qwen3-8b"
    )

LLM_CONFIG = LLMConfig(
    provider="openai",
    model=os.environ.get("PM_LLM_MODEL", "qwen/qwen3-8b"),
    api_key=api_key,
    base_url=os.environ.get("PM_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
    temperature=0.0,
    timeout_seconds=180,
)

CASES = [
    ("inputs/vendor_onboarding_sop.md",     "eval/gold/vendor_onboarding.json"),
    ("inputs/it_incident_management_sop.md", "eval/gold/it_incident_management.json"),
    ("inputs/employee_leave_approval_sop.md", "eval/gold/employee_leave_approval.json"),
    ("inputs/legacy_it_purchase_sop.txt",    "eval/gold/legacy_it_purchase.json"),
]


def load_gold(path):
    with open(path) as f:
        return json.load(f)


def score(model, gold):
    return evaluate_model(model, gold)


rows = {}
provider = build_provider(LLM_CONFIG)
print(f"LLM provider: {provider} ({LLM_CONFIG.model})")

for sop_path, gold_path in CASES:
    sop_name = Path(sop_path).stem.replace("_sop", "").replace("_", " ")
    gold = load_gold(PROJECT / gold_path)

    # Ingest SOP
    ingestion = IngestionAgent()
    doc = ingestion.run(str(PROJECT / sop_path))

    print(f"\n{'=' * 60}\n  {sop_name}\n{'=' * 60}")

    row = {}
    # E1: offline rule parser (no LLM)
    t0 = time.time()
    agent_e1 = ProcessModelerAgent(provider=None)
    out_e1 = agent_e1.run(doc)
    m_e1 = score(out_e1.model, gold)
    row["E1_rule"] = {"p": m_e1["task_precision"], "r": m_e1["task_recall"],
                      "f1": m_e1["task_f1"], "actor_f1": m_e1["actor_f1"],
                      "gw_err": m_e1["gateway_error"], "rw_err": m_e1["rework_error"],
                      "time": time.time() - t0, "method": out_e1.method}
    print(f"  E1 (rule):  P={m_e1['task_precision']:.2f} R={m_e1['task_recall']:.2f} F1={m_e1['task_f1']:.2f} | "
          f"ActorF1={m_e1['actor_f1']:.2f} | GW={m_e1['gateway_error']} RW={m_e1['rework_error']} | {row['E1_rule']['time']:.1f}s")

    # E2: LLM single-shot (max_retries=0)
    t0 = time.time()
    agent_e2 = ProcessModelerAgent(provider=provider, max_llm_retries=0)
    try:
        out_e2 = agent_e2.run(doc)
        m_e2 = score(out_e2.model, gold)
        row["E2_llm_single"] = {"p": m_e2["task_precision"], "r": m_e2["task_recall"],
                                "f1": m_e2["task_f1"], "actor_f1": m_e2["actor_f1"],
                                "gw_err": m_e2["gateway_error"], "rw_err": m_e2["rework_error"],
                                "time": time.time() - t0, "method": out_e2.method}
        print(f"  E2 (LLM 1-shot): P={m_e2['task_precision']:.2f} R={m_e2['task_recall']:.2f} F1={m_e2['task_f1']:.2f} | "
              f"ActorF1={m_e2['actor_f1']:.2f} | GW={m_e2['gateway_error']} RW={m_e2['rework_error']} | {row['E2_llm_single']['time']:.1f}s")
    except Exception as e:
        row["E2_llm_single"] = {"error": str(e), "time": time.time() - t0}
        print(f"  E2 (LLM 1-shot): ERROR — {e}")

    # E3: LLM with self-correction (max_retries=2)
    t0 = time.time()
    agent_e3 = ProcessModelerAgent(provider=provider, max_llm_retries=2)
    try:
        out_e3 = agent_e3.run(doc)
        m_e3 = score(out_e3.model, gold)
        row["E3_llm_retry"] = {"p": m_e3["task_precision"], "r": m_e3["task_recall"],
                               "f1": m_e3["task_f1"], "actor_f1": m_e3["actor_f1"],
                               "gw_err": m_e3["gateway_error"], "rw_err": m_e3["rework_error"],
                               "time": time.time() - t0, "method": out_e3.method}
        print(f"  E3 (LLM retry): P={m_e3['task_precision']:.2f} R={m_e3['task_recall']:.2f} F1={m_e3['task_f1']:.2f} | "
              f"ActorF1={m_e3['actor_f1']:.2f} | GW={m_e3['gateway_error']} RW={m_e3['rework_error']} | {row['E3_llm_retry']['time']:.1f}s")
    except Exception as e:
        row["E3_llm_retry"] = {"error": str(e), "time": time.time() - t0}
        print(f"  E3 (LLM retry): ERROR — {e}")

    rows[sop_name] = row

# Save results
out = PROJECT / "outputs" / "llm_comparison.json"
out.parent.mkdir(exist_ok=True, parents=True)
with open(out, "w") as f:
    json.dump(rows, f, indent=2)
print(f"\nSaved: {out}")
print("\nDone.")
