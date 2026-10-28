import pytest

from integrations.seed import VARIABLES, as_variable, load_requests
from integrations.servicenow import ServiceNowError
from integrations.verify import run_check


def test_seed_requests_use_only_catalog_variables() -> None:
    requests = load_requests()
    assert len(requests) == 5
    known = {name for name, _, _ in VARIABLES}
    for request in requests:
        assert set(request["variables"]) <= known, request["title"]
        assert request["variables"]["request_text"].strip()


@pytest.mark.parametrize(
    ("value", "expected"), [(True, "true"), (False, "false"), (None, ""), ("M", "M")]
)
def test_as_variable(value: object, expected: str) -> None:
    assert as_variable(value) == expected


def test_run_check_reports_rejected_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    def rejected() -> str:
        raise ServiceNowError(401, "User is not authenticated")

    assert run_check("ServiceNow", rejected) is False
    assert "ServiceNow KO" in capsys.readouterr().out


def test_run_check_reports_success(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_check("Jira", lambda: "all good") is True
    assert capsys.readouterr().out.strip() == "Jira OK  all good"
