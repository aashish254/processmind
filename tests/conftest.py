"""Shared fixtures: project paths and ingested documents."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUTS = PROJECT_ROOT / "inputs"
GOLD = PROJECT_ROOT / "eval" / "gold"


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def inputs_dir() -> Path:
    return INPUTS


@pytest.fixture(scope="session")
def vendor_doc():
    from process_miner.agents.ingestion import IngestionAgent

    return IngestionAgent().run(str(INPUTS / "vendor_onboarding_sop.md"))


@pytest.fixture(scope="session")
def it_doc():
    from process_miner.agents.ingestion import IngestionAgent

    return IngestionAgent().run(str(INPUTS / "it_incident_management_sop.md"))


@pytest.fixture(scope="session")
def leave_doc():
    from process_miner.agents.ingestion import IngestionAgent

    return IngestionAgent().run(str(INPUTS / "employee_leave_approval_sop.md"))


@pytest.fixture(scope="session")
def vendor_model(vendor_doc):
    from process_miner.agents.modeler import ProcessModelerAgent

    return ProcessModelerAgent().run(vendor_doc).model


@pytest.fixture(scope="session")
def it_model(it_doc):
    from process_miner.agents.modeler import ProcessModelerAgent

    return ProcessModelerAgent().run(it_doc).model


@pytest.fixture()
def tmp_out(tmp_path):
    return tmp_path
