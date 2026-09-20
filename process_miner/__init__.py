"""ProcessMind - Enterprise AI Process Mining & BPMN Automation.

A multi-agent pipeline that ingests unstructured operational documents
(SOPs, runbooks, process narratives) or raw event logs and produces:

* structured JSON process models,
* BPMN 2.0 XML with full diagram interchange (DI) layout,
* bottleneck findings and As-Is -> To-Be optimization recommendations,
* draw.io / Mermaid / SVG exports and an HTML analyst report.

Package layout:
    process_miner.models     - core data contracts (pydantic)
    process_miner.llm        - provider abstraction (OpenAI/Anthropic/offline)
    process_miner.agents     - ingestion, modeling, optimization agents
    process_miner.bpmn       - BPMN 2.0 XML builder, layout engine, validator
    process_miner.mining     - event-log mining (DFG discovery, analytics)
    process_miner.export     - draw.io, Mermaid, SVG, HTML report exporters
    process_miner.graph      - pipeline orchestration (builtin + LangGraph)
    process_miner.cli        - command line interface
    process_miner.api        - FastAPI service (optional)
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
