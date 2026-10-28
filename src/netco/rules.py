"""Validation of a service exposure request against referentiel/netco.yaml.

Rejection reasons are in French and start with the rule identifier documented in referentiel/*.md,
so that the requester sees which rule applies.
"""

import ipaddress
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

REFERENTIEL = Path(__file__).resolve().parents[2] / "referentiel" / "netco.yaml"


@cache
def load_rules(path: Path = REFERENTIEL) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass
class Validation:
    valid: bool
    reasons: list[str] = field(default_factory=list)
    namespace: str = ""
    port: int | None = None
    zones: list[str] = field(default_factory=list)
    sensitive_port: bool = False

    def as_variables(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "rejectionReasons": self.reasons,
            "namespace": self.namespace,
            "port": self.port,
            "zones": self.zones,
            "sensitivePort": self.sensitive_port,
        }


def validate(form: dict[str, Any], rules: dict[str, Any] | None = None) -> Validation:
    """Check the structured form of a request (camelCase keys, as in the process variables)."""
    rules = rules or load_rules()
    reasons: list[str] = []
    service = str(form.get("serviceName") or "").strip()
    environment = str(form.get("environment") or "").strip().lower()
    exposure = str(form.get("exposure") or "").strip().lower()

    if not re.fullmatch(rules["naming"]["service_pattern"], service):
        reasons.append(f"NOM-01 : nom de service « {service} » non conforme")
    if environment not in rules["environments"]:
        reasons.append(
            f"ENV-01 : environnement « {environment} » inconnu"
            if environment
            else "ENV-01 : environnement manquant"
        )
    if exposure not in rules["exposures"]:
        reasons.append(f"EXP-01 : exposition « {exposure} » inconnue (interne ou externe)")

    port = _check_port(str(form.get("ports") or ""), exposure, rules, reasons)
    zones = _check_zones(str(form.get("sourceNetworks") or ""), exposure, rules, reasons)

    if reasons:
        return Validation(valid=False, reasons=reasons)
    namespace = rules["naming"]["namespace_template"].format(
        service=service, environment=environment
    )
    return Validation(
        valid=True,
        namespace=namespace,
        port=port,
        zones=zones,
        sensitive_port=port in rules["ports"]["sensitive"],
    )


def _check_port(text: str, exposure: str, rules: dict[str, Any], reasons: list[str]) -> int | None:
    entries = [entry.strip() for entry in text.split(",") if entry.strip()]
    if not entries:
        reasons.append("PORT-02 : aucun port indiqué")
        return None
    if len(entries) > rules["ports"]["max_per_request"]:
        reasons.append("PORT-03 : un seul port par demande")
        return None
    number, _, protocol = entries[0].partition("/")
    if protocol and protocol.lower() not in rules["ports"]["protocols"]:
        reasons.append(f"PORT-04 : protocole « {protocol} » non pris en charge (TCP seulement)")
    if not number.isdigit():
        reasons.append(f"PORT-02 : port « {entries[0]} » illisible")
        return None
    port = int(number)
    forbidden = rules["ports"]["forbidden"]
    if port in forbidden:
        reasons.append(f"PORT-01 : le port {port} ({forbidden[port]}) est interdit")
    elif exposure in rules["ports"]["allowed"] and port not in rules["ports"]["allowed"][exposure]:
        reasons.append(
            f"PORT-02 : le port {port} n'est pas autorisé pour une exposition {exposure}"
        )
    return port


def _check_zones(text: str, exposure: str, rules: dict[str, Any], reasons: list[str]) -> list[str]:
    zone_networks = {name: ipaddress.ip_network(cidr) for name, cidr in rules["zones"].items()}
    zones: list[str] = []
    entries = [entry.strip() for entry in text.split(",") if entry.strip()]
    if not entries:
        reasons.append("ZONE-01 : aucun réseau source indiqué")
    for entry in entries:
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            reasons.append(f"ZONE-01 : réseau « {entry} » invalide")
            continue
        # The most specific zone that contains the requested network.
        matches = [
            (zone_network.prefixlen, name)
            for name, zone_network in zone_networks.items()
            if network.version == zone_network.version and network.subnet_of(zone_network)
        ]
        name = max(matches)[1] if matches else None
        if name is None or (name == "internet" and network.prefixlen != 0):
            reasons.append(f"ZONE-01 : le réseau {entry} n'appartient à aucune zone NetCo")
        elif name == "internet" and exposure != "externe":
            reasons.append("ZONE-02 : Internet (0.0.0.0/0) n'est accepté qu'en exposition externe")
        elif name not in zones:
            zones.append(name)
    if exposure == "externe" and "internet" not in zones:
        zones.append("internet")
    return zones
