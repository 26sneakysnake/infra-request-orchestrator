import pytest

from integrations.seed import load_requests
from netco.rules import validate
from workers.poller import FORM_FIELDS


def _form(**overrides: str) -> dict[str, str]:
    form = {
        "serviceName": "catalogue-api",
        "environment": "dev",
        "ports": "8080/tcp",
        "sourceNetworks": "10.20.0.0/16",
        "exposure": "interne",
    }
    return {**form, **overrides}


def test_seed_requests_get_the_expected_verdicts() -> None:
    verdicts = {}
    for request in load_requests():
        form = {FORM_FIELDS[k]: v for k, v in request["variables"].items()}
        result = validate(form)
        verdicts[request["title"]] = (result.valid, [r.split(" ")[0] for r in result.reasons])
    assert verdicts == {
        "Standard, interne, dev": (True, []),
        "Externe, prod": (True, []),
        "Avec VM, recette": (True, []),
        "Environnement manquant": (False, ["ENV-01"]),
        "Port interdit": (False, ["PORT-01"]),
    }


def test_valid_request_gives_namespace_port_and_zones() -> None:
    result = validate(_form())
    assert result.as_variables() == {
        "valid": True,
        "rejectionReasons": [],
        "namespace": "svc-catalogue-api-dev",
        "port": 8080,
        "zones": ["dev"],
        "sensitivePort": False,
    }


def test_subnet_of_a_zone_maps_to_that_zone() -> None:
    assert validate(_form(sourceNetworks="10.20.5.0/24, 10.30.0.0/16")).zones == ["dev", "data"]


def test_external_exposure_adds_the_internet_zone() -> None:
    result = validate(_form(exposure="externe", ports="443/tcp"))
    assert result.valid and result.zones == ["dev", "internet"]


def test_sensitive_port_is_flagged() -> None:
    assert validate(_form(ports="5432/tcp")).sensitive_port is True


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"serviceName": "Catalogue_API"}, "NOM-01"),
        ({"environment": "preprod"}, "ENV-01"),
        ({"exposure": "publique"}, "EXP-01"),
        ({"ports": "22/tcp"}, "PORT-01"),
        ({"ports": "9999/tcp"}, "PORT-02"),
        ({"exposure": "externe", "ports": "8080/tcp"}, "PORT-02"),
        ({"ports": "443/tcp, 8443/tcp"}, "PORT-03"),
        ({"ports": "8080/udp"}, "PORT-04"),
        ({"sourceNetworks": "192.168.1.0/24"}, "ZONE-01"),
        ({"sourceNetworks": "pas-un-reseau"}, "ZONE-01"),
        ({"sourceNetworks": "0.0.0.0/0"}, "ZONE-02"),
        ({"vmRequired": True, "vmSize": ""}, "VM-01"),
        ({"vmRequired": True, "vmSize": "XL"}, "VM-01"),
    ],
)
def test_each_rule_rejects_with_its_identifier(overrides: dict[str, str], rule: str) -> None:
    result = validate(_form(**overrides))
    assert not result.valid
    assert any(reason.startswith(rule) for reason in result.reasons), result.reasons


def test_vm_size_is_only_checked_when_a_vm_is_requested() -> None:
    assert validate(_form(vmRequired=False, vmSize="")).valid
    assert validate(_form(vmRequired=True, vmSize="m")).valid
