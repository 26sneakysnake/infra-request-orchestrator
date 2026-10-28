import pytest

from evals import qualification as evaluation
from evals.stats import proportion, wilson


def test_wilson_interval_on_small_samples() -> None:
    low, high = wilson(27, 27)
    assert round(low, 4) == 0.8754 and high == 1.0
    assert wilson(0, 0) == (0.0, 1.0)
    assert proportion(3, 4)["rate"] == 0.75


def test_cases_are_frozen() -> None:
    assert evaluation.check_frozen() == evaluation.fingerprint()


@pytest.mark.parametrize(
    ("field", "expected", "got", "ok"),
    [
        ("ports", ["443/tcp"], ["443"], True),
        ("ports", ["443/tcp"], ["443/tcp", "80/tcp"], False),
        ("source_networks", ["10.20.0.0/16"], ["10.20.0.0/16"], True),
        ("environment", None, None, True),
        ("environment", None, "recette", False),
        ("service_name", "Catalogue-API", "catalogue-api", True),
        ("urgent", True, False, False),
    ],
)
def test_field_comparison(field: str, expected: object, got: object, ok: bool) -> None:
    assert evaluation.field_ok(field, expected, got) is ok


def _variables(**overrides: object) -> dict:
    variables = {
        "serviceName": "legacy-erp",
        "environment": "prod",
        "exposure": "externe",
        "ports": "3389/tcp",
        "sourceNetworks": "0.0.0.0/0",
        "qualification": {"outOfScope": False, "missing": []},
    }
    return {**variables, **overrides}


def test_final_decision_follows_the_deterministic_rules() -> None:
    assert evaluation.decision(_variables()) == ("rejected", ["PORT-01"])
    assert evaluation.decision(_variables(ports="443/tcp"))[0] == "valid"
    assert (
        evaluation.decision(_variables(qualification={"outOfScope": False, "missing": ["ports"]}))[
            0
        ]
        == "missing"
    )
