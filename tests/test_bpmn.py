"""Static checks on the deployed models; the engine validates them for real in the e2e job."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from workers.handlers import HANDLERS

BPMN_DIR = Path(__file__).resolve().parents[1] / "bpmn"
NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "zeebe": "http://camunda.org/schema/zeebe/1.0",
    "dmn": "https://www.omg.org/spec/DMN/20191111/MODEL/",
}
PROCESS = ET.parse(BPMN_DIR / "expose_service.bpmn").getroot()


def test_every_service_task_type_has_a_worker() -> None:
    types = {t.get("type") for t in PROCESS.iterfind(".//zeebe:taskDefinition", NS)}
    assert types == set(HANDLERS)


def test_every_element_is_drawn() -> None:
    process = PROCESS.find("bpmn:process", NS)
    elements = {child.get("id") for child in process if child.get("id")}
    drawn = {d.get("bpmnElement") for d in PROCESS.iterfind(".//bpmndi:BPMNShape", NS)} | {
        d.get("bpmnElement") for d in PROCESS.iterfind(".//bpmndi:BPMNEdge", NS)
    }
    assert elements <= drawn, elements - drawn


def test_called_decision_and_forms_exist() -> None:
    decision = PROCESS.find(".//zeebe:calledDecision", NS).get("decisionId")
    dmn = ET.parse(BPMN_DIR / "change_class.dmn").getroot()
    assert decision in {d.get("id") for d in dmn.iterfind("dmn:decision", NS)}

    form_ids = {f.get("formId") for f in PROCESS.iterfind(".//zeebe:formDefinition", NS)}
    deployed = {json.loads(p.read_text(encoding="utf-8"))["id"] for p in BPMN_DIR.glob("*.form")}
    assert form_ids == deployed


def test_every_user_task_is_a_camunda_user_task() -> None:
    for task in PROCESS.iterfind(".//bpmn:userTask", NS):
        assert task.find("bpmn:extensionElements/zeebe:userTask", NS) is not None, task.get("id")
