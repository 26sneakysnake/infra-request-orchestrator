"""Reproducible faults injected into an exposure: diagnosis evaluation, e2e scenario and demos.

Each variant breaks one object the way a hurried manual change would. Its expected cause and action
are the ground truth of the diagnosis evaluation. Workers inject a fault only when asked to with
NETCO_INJECT_FAULT=<variant>:<service>, and only at provisioning time: a remediation always applies
the clean manifests computed from the validated request.
"""

import copy
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Objects = list[dict[str, Any]]
PROBE_IMAGE = "curlimages/curl:8.22.0"  # already on the node (zone probes)


@dataclass(frozen=True)
class Fault:
    cause: str
    action: str
    description: str
    apply: Callable[[Objects, dict[str, Any]], Objects]


def _find(objects: Objects, kind: str) -> dict[str, Any]:
    return next(o for o in objects if o["kind"] == kind)


def _edit(kind: str, change: Callable[[dict[str, Any], dict[str, Any]], None]):
    def apply(objects: Objects, request: dict[str, Any]) -> Objects:
        objects = copy.deepcopy(objects)
        change(_find(objects, kind), request)
        return objects

    return apply


def _other_zone(request: dict[str, Any]) -> str:
    return next(z for z in ("bureautique", "data", "finance", "dev") if z not in request["zones"])


def _policy_zone(policy: dict[str, Any], request: dict[str, Any]) -> None:
    selector = policy["spec"]["ingress"][0]["from"][0]["namespaceSelector"]
    selector["matchExpressions"][0]["values"] = [_other_zone(request)]


def _policy_port(policy: dict[str, Any], request: dict[str, Any]) -> None:
    policy["spec"]["ingress"][0]["ports"][0]["port"] = request["port"] + 1


def _target_port(service: dict[str, Any], request: dict[str, Any]) -> None:
    service["spec"]["ports"][0]["targetPort"] = request["port"] + 1


def _service_port(service: dict[str, Any], request: dict[str, Any]) -> None:
    service["spec"]["ports"][0]["port"] = request["port"] + 1


def _selector_typo(service: dict[str, Any], request: dict[str, Any]) -> None:
    service["spec"]["selector"] = {"app.kubernetes.io/name": f"{request['service']}-v2"}


def _selector_label(service: dict[str, Any], request: dict[str, Any]) -> None:
    service["spec"]["selector"] = {"app": request["service"]}


def _image(image: str):
    def change(deployment: dict[str, Any], request: dict[str, Any]) -> None:
        deployment["spec"]["template"]["spec"]["containers"][0]["image"] = image

    return change


def _quota(pods: int, occupied: bool):
    def apply(objects: Objects, request: dict[str, Any]) -> Objects:
        namespace = request["namespace"]
        extra: Objects = []
        if occupied:
            extra.append(
                {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {
                        "name": "batch-legacy",
                        "namespace": namespace,
                        "labels": {"app.kubernetes.io/name": "batch-legacy"},
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "batch",
                                "image": PROBE_IMAGE,
                                "command": ["sleep", "infinity"],
                            }
                        ]
                    },
                }
            )
        extra.append(
            {
                "apiVersion": "v1",
                "kind": "ResourceQuota",
                "metadata": {"name": "pods-quota", "namespace": namespace},
                "spec": {"hard": {"pods": str(pods)}},
            }
        )
        # Right after the namespace, so the quota is in place before the deployment's pods.
        return [objects[0], *extra, *copy.deepcopy(objects[1:])]

    return apply


FAULTS: dict[str, Fault] = {
    "network_policy_zone": Fault(
        "network_policy",
        "reapply_network_policy",
        "La NetworkPolicy autorise une autre zone que celle demandée",
        _edit("NetworkPolicy", _policy_zone),
    ),
    "network_policy_port": Fault(
        "network_policy",
        "reapply_network_policy",
        "La NetworkPolicy autorise un autre port que celui du service",
        _edit("NetworkPolicy", _policy_port),
    ),
    "service_target_port": Fault(
        "service_port",
        "reapply_service",
        "Le Service envoie le trafic vers un mauvais port du conteneur (targetPort)",
        _edit("Service", _target_port),
    ),
    "service_port": Fault(
        "service_port",
        "reapply_service",
        "Le Service écoute sur un autre port que celui demandé",
        _edit("Service", _service_port),
    ),
    "selector_typo": Fault(
        "service_selector",
        "reapply_service",
        "Le selector du Service contient une faute et ne vise aucun pod",
        _edit("Service", _selector_typo),
    ),
    "selector_label": Fault(
        "service_selector",
        "reapply_service",
        "Le selector du Service utilise un label que les pods n'ont pas",
        _edit("Service", _selector_label),
    ),
    "image_tag": Fault(
        "image",
        "reapply_deployment",
        "Le déploiement référence un tag d'image qui n'existe pas",
        _edit("Deployment", _image("traefik/whoami:v9.9.99")),
    ),
    "image_registry": Fault(
        "image",
        "reapply_deployment",
        "Le déploiement référence un registre d'images injoignable",
        _edit("Deployment", _image("registry.netco.invalid/whoami:v1.12.0")),
    ),
    "quota_zero": Fault(
        "quota",
        "raise_pod_quota",
        "Un quota du namespace n'autorise aucun pod",
        _quota(0, occupied=False),
    ),
    "quota_full": Fault(
        "quota",
        "raise_pod_quota",
        "Le quota de pods du namespace est déjà atteint par un autre pod",
        _quota(1, occupied=True),
    ),
}


def inject(objects: Objects, variant: str, request: dict[str, Any]) -> Objects:
    """request: service, namespace, port, zones of the validated exposure."""
    return FAULTS[variant].apply(objects, request)


def requested_fault(service: str) -> str | None:
    """The variant to inject for this service, from NETCO_INJECT_FAULT=<variant>:<service>."""
    spec = os.environ.get("NETCO_INJECT_FAULT", "")
    variant, _, target = spec.partition(":")
    if variant and target == service:
        if variant not in FAULTS:
            raise ValueError(f"unknown fault {variant!r}; known: {', '.join(FAULTS)}")
        return variant
    return None
