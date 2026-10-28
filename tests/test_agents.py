import json
from pathlib import Path

import httpx2
import pytest
import yaml

from agents.llm import BudgetExceeded, CassetteMiss, CassetteTransport, SpendLedger, cost_usd
from agents.qualification import Qualification, merge, qualify
from agents.referentiel import passage_exists, search

CASES = Path(__file__).resolve().parents[1] / "eval" / "cases" / "qualification" / "cases.yaml"
ANSWER = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-5-5",
    "content": [{"type": "text", "text": "{}"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 1000, "output_tokens": 100},
}


def test_search_finds_the_zone_of_a_team() -> None:
    assert search("équipe finance")[0].title.startswith("ZONE-01")
    assert search("port RDP bureau à distance")[0].title.startswith("PORT-01")


def test_only_genuine_passages_count_as_citations() -> None:
    assert passage_exists("| finance | 10.40.12.0/24 | Applications de la direction financière |")
    assert passage_exists("Trois environnements existent : dev, recette et prod.")
    assert not passage_exists("Le port 3389 est autorisé en externe.")
    assert not passage_exists("   ")


def _transport(tmp_path: Path, mode: str, budget: float = 3.0) -> CassetteTransport:
    inner = httpx2.MockTransport(lambda request: httpx2.Response(200, json=ANSWER))
    ledger = SpendLedger(tmp_path / "spend.json", budget_usd=budget)
    return CassetteTransport(mode, directory=tmp_path / "llm", ledger=ledger, inner=inner)


def _post(transport: CassetteTransport, body: dict) -> httpx2.Response:
    with httpx2.Client(transport=transport) as client:
        return client.post(
            "https://api.anthropic.com/v1/messages",
            json=body,
            headers={"x-api-key": "sk-ant-secret"},
        )


BODY = {
    "model": "claude-sonnet-5-5",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "a"}],
}


def test_record_stores_the_answer_without_headers_then_replay_serves_it(tmp_path: Path) -> None:
    assert _post(_transport(tmp_path, "record"), BODY).json() == ANSWER
    stored = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "llm").glob("*.json"))
    assert "sk-ant-secret" not in stored and "x-api-key" not in stored
    assert _post(_transport(tmp_path, "replay"), BODY).json() == ANSWER


def test_replay_of_an_unknown_prompt_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(CassetteMiss, match="make eval-live"):
        _post(_transport(tmp_path, "replay"), BODY)


def test_spend_is_recorded_and_the_budget_enforced(tmp_path: Path) -> None:
    _post(_transport(tmp_path, "live"), BODY)
    assert SpendLedger(tmp_path / "spend.json").spent() == pytest.approx(
        cost_usd("claude-sonnet-5-5", ANSWER["usage"])
    )
    with pytest.raises(BudgetExceeded):
        _post(_transport(tmp_path, "live", budget=0.0001), BODY)


def test_qualify_replays_a_recorded_case() -> None:
    case = yaml.safe_load(CASES.read_text(encoding="utf-8"))[10]  # Q11: zone named in words
    from agents.llm import anthropic_client

    result = qualify(case["text"], client=anthropic_client("replay"))
    assert result.answer["source_networks"] == ["10.20.0.0/16"]
    assert result.answer["missing"] == []
    assert result.turns >= 1 and result.cost_usd > 0


def _qualification(**answer: object) -> Qualification:
    base = {
        "out_of_scope": False,
        "service_name": "facturation-api",
        "environment": None,
        "exposure": "interne",
        "ports": ["8443/tcp"],
        "source_networks": ["10.40.12.0/24"],
        "vm_required": False,
        "vm_size": None,
        "urgent": False,
        "missing": ["environment"],
        "questions": ["Pour quel environnement ?"],
        "citations": [],
        "summary": "Exposition de facturation-api",
    }
    return Qualification({**base, **answer}, "claude-sonnet-5-5", 1, {"output_tokens": 10})


def test_merge_keeps_what_the_requester_filled_in() -> None:
    merged = merge({"environment": "recette", "ports": "443/tcp"}, _qualification())
    assert merged["environment"] == "recette"  # form wins, so nothing is missing any more
    assert merged["ports"] == "443/tcp"
    assert merged["sourceNetworks"] == "10.40.12.0/24"
    assert merged["qualification"]["missing"] == []


def test_merge_recomputes_gaps_the_agent_did_not_flag() -> None:
    merged = merge({}, _qualification(missing=[], questions=[], source_networks=[]))
    assert merged["qualification"]["missing"] == ["environment", "source_networks"]
    assert len(merged["qualification"]["questions"]) == 2


def test_out_of_scope_gives_a_rejection_reason() -> None:
    merged = merge({}, _qualification(out_of_scope=True, summary="Réinitialiser un mot de passe"))
    assert merged["qualification"]["outOfScope"] is True
    assert merged["qualification"]["missing"] == []
    assert "mot de passe" in merged["rejectionReasons"][0]


def test_cassettes_never_contain_an_api_key() -> None:
    cassettes = Path(__file__).resolve().parents[1] / "cassettes" / "llm"
    for path in cassettes.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "sk-ant-" not in text and "x-api-key" not in text.lower(), path.name
        assert json.loads(text)["status"] == 200
