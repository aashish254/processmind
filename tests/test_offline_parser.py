"""Tests for the offline rule-based process parser."""

from __future__ import annotations

import pytest

from process_miner.agents.modeler import ProcessModelerAgent
from process_miner.bpmn.validate import validate_model


@pytest.fixture(scope="module")
def agent():
    return ProcessModelerAgent()


def test_vendor_model_structure(agent, vendor_doc):
    out = agent.run(vendor_doc)
    m = out.model
    assert out.method == "offline-rules"
    assert len(m.tasks()) == 13
    assert len(m.start_events()) == 1
    assert len(m.end_events()) >= 1
    xor = sum(1 for g in m.gateways() if g.type.value == "xor_gateway")
    ands = sum(1 for g in m.gateways() if g.type.value == "and_gateway")
    assert xor == 3
    assert ands == 2
    assert validate_model(m).ok


def test_vendor_key_tasks(vendor_model):
    names = [t.name for t in vendor_model.tasks()]
    assert "Approve the vendor request" in names
    assert "Create the vendor record" in names
    assert "Perform background screening" in names


def test_rework_loop(vendor_model):
    rework = [f for f in vendor_model.flows if f.label == "Rework"]
    assert len(rework) == 1
    # the rework edge must enter an explicit XOR merge gateway, never the task directly
    merge = vendor_model.node(rework[0].target)
    assert merge is not None and merge.is_gateway()
    join_targets = vendor_model.out_nodes(merge.id)
    assert len(join_targets) == 1 and vendor_model.node(join_targets[0]).is_task()


def test_parallel_block(vendor_model):
    ands = [g for g in vendor_model.gateways() if g.type.value == "and_gateway"]
    assert len(ands) == 2  # split + join
    split, join = ands
    assert len(vendor_model.out_nodes(split.id)) == 2
    assert len(vendor_model.in_nodes(join.id)) == 2


def test_lane_assignment(vendor_model):
    actors = [a for a in vendor_model.actors() if a != "Unassigned"]
    assert set(actors) == {"Procurement Officer", "Compliance Team", "Finance Manager", "Vendor Portal", "ERP System"}
    # ERP tasks are automated service tasks
    erp_tasks = [t for t in vendor_model.tasks() if t.actor == "ERP System"]
    assert erp_tasks and all(t.automated for t in erp_tasks)


def test_provenance_recorded(vendor_model):
    tasks_with_source = [t for t in vendor_model.tasks() if t.source_text]
    assert len(tasks_with_source) == len(vendor_model.tasks())


def test_it_model_structure(agent, it_doc):
    out = agent.run(it_doc)
    m = out.model
    names = [t.name for t in m.tasks()]
    assert len(names) == 15
    for expected in ["Open a war room", "Apply the standard fix", "Restore the affected service", "Escalate the ticket to the Incident Manager"]:
        assert expected in names, f"missing: {expected}"
    rework = [f for f in m.flows if f.label == "Rework"]
    assert len(rework) == 1
    assert validate_model(m).ok


def test_leave_model_structure(agent, leave_doc):
    out = agent.run(leave_doc)
    m = out.model
    names = [t.name for t in m.tasks()]
    assert len(names) == 8
    assert "Approve the leave request" in names
    # no rework in this process
    assert not [f for f in m.flows if f.label == "Rework"]
    assert validate_model(m).ok


def test_xor_splits_have_labels(vendor_model):
    for g in vendor_model.gateways():
        if g.type.value == "xor_gateway" and len(vendor_model.out_nodes(g.id)) > 1 and g.name:
            labels = [f.label for f in vendor_model.successors(g.id)]
            assert all(labels), f"unlabeled split at {g.name}"


def test_deterministic_output(vendor_doc, agent):
    out1 = agent.run(vendor_doc)
    out2 = agent.run(vendor_doc)
    assert [n.id for n in out1.model.nodes] == [n.id for n in out2.model.nodes]
    assert [(f.source, f.target, f.label) for f in out1.model.flows] == [
        (f.source, f.target, f.label) for f in out2.model.flows
    ]


def test_negation_continuation(agent):
    doc_text = (
        "Process: Tiny\n"
        "Roles: Clerk, System\n"
        "The process begins when a form is received.\n"
        "The System checks the form.\n"
        "If the form is invalid, the System rejects the form and the process ends.\n"
        "Otherwise, the Clerk processes the form.\n"
        "The Clerk archives the form and the process ends.\n"
    )
    from process_miner.agents.ingestion import IngestionAgent

    doc = IngestionAgent().run(doc_text)
    out = agent.run(doc)
    m = out.model
    assert validate_model(m).ok
    # no path from the rejected branch into the main flow
    reject = next(t for t in m.tasks() if "Reject" in t.name)
    outs = [m.node(x).type.value for x in m.out_nodes(reject.id)]
    assert outs == ["end_event"]
