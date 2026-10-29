from metrics.collect import aggregate, as_is, instance_measures


def _element(element_id: str, kind: str, start: float, end: float, name: str = "") -> dict:
    return {"id": element_id, "name": name or element_id, "type": kind, "start": start, "end": end}


STANDARD = {
    "start": 0.0,
    "end": 60.0,
    "elements": [
        _element("StartEvent_RequestReceived", "START_EVENT", 0, 0),
        _element("Task_QualifyRequest", "SERVICE_TASK", 0, 8),
        _element("Task_ClassifyChange", "BUSINESS_RULE_TASK", 8, 8),
        _element("Task_Provision", "SERVICE_TASK", 9, 10),
        _element("Task_Document", "SERVICE_TASK", 40, 55),
        _element("End_Exposed", "END_EVENT", 60, 60),
    ],
    "variables": {"llmCostUsd": 0.03, "documentation": {"source": "agent"}},
}
FREE_TEXT = {
    "start": 0.0,
    "end": 100.0,
    "elements": [
        _element("Task_QualifyRequest", "SERVICE_TASK", 0, 6),
        _element("Gateway_WaitReply", "EVENT_BASED_GATEWAY", 7, 37),  # the requester's 30 s
        _element("Event_RequesterReply", "INTERMEDIATE_CATCH_EVENT", 37, 37),
        _element("Task_QualifyRequest", "SERVICE_TASK", 37, 45),
        _element("Task_ApproveChange", "USER_TASK", 50, 60),
        _element("Task_Document", "SERVICE_TASK", 80, 90),
        # A step still running has no end date: it is left out of every duration.
        _element("Task_Unfinished", "SERVICE_TASK", 95, None),  # type: ignore[arg-type]
    ],
    "variables": {"llmCostUsd": 0.05, "documentation": {"source": "gabarit"}},
}


def test_human_waits_are_subtracted_from_the_processing_time() -> None:
    m = instance_measures(FREE_TEXT)
    assert m["total_s"] == 100 and m["human_wait_s"] == 40 and m["processing_s"] == 60
    assert m["interventions"] == ["Event_RequesterReply", "Task_ApproveChange"]
    assert (m["automated"], m["human"]) == (3, 2)


def test_aggregate_counts_proportions_and_groups_by_kind() -> None:
    rows = [
        {**instance_measures(STANDARD), "kind": "standard"},
        {**instance_measures(FREE_TEXT), "kind": "texte_libre"},
    ]
    result = aggregate(rows, total_requests=3)
    assert result["completed"]["k"] == 2 and result["completed"]["n"] == 3
    assert result["end_to_end_s"]["all"] == {"n": 2, "median": 80.0, "min": 60.0, "max": 100.0}
    assert result["end_to_end_s"]["standard"]["median"] == 60.0
    assert result["end_to_end_s"]["panne"] == {"n": 0}
    # Both rounds of the qualification are counted as steps.
    assert result["agent_steps_s"]["Task_QualifyRequest"]["n"] == 3
    assert result["automated_activities"] == {"k": 7, "n": 9, "rate": 0.7778}
    assert result["requests_without_human"]["k"] == 1
    assert result["human_interventions_by_kind"]["texte_libre"] == {
        "Event_RequesterReply": 1,
        "Task_ApproveChange": 1,
    }
    assert result["llm_cost_usd"]["total"] == 0.08
    assert result["documentation_by_agent"]["k"] == 1 and result["documentation_by_agent"]["n"] == 2


def test_as_is_hypotheses_are_labelled_and_summed() -> None:
    hypotheses = as_is()
    assert hypotheses["nature"] == "hypothèse déclarée, non mesurée"
    standard, with_vm = hypotheses["totals"]["standard"], hypotheses["totals"]["normale_vm"]
    # The CAB and the VM only apply to a normal change with a VM.
    assert with_vm["steps"] == standard["steps"] + 2
    assert with_vm["effort_min"] > standard["effort_min"]
    assert with_vm["delay_days"][1] >= with_vm["delay_days"][0]
