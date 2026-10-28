"""Kubernetes objects for one exposed service: Namespace, Deployment, Service, NetworkPolicy.

The NetworkPolicy plays the firewall: it only lets the requested zones in, on the requested port.
"""

from typing import Any

WORKLOAD_IMAGE = "traefik/whoami:v1.12.0"  # small HTTP server standing in for the real service
ZONE_LABEL = "netco.io/zone"
MANAGED_BY = "infra-request-orchestrator"


def _labels(service: str, environment: str) -> dict[str, str]:
    return {
        "app.kubernetes.io/name": service,
        "app.kubernetes.io/managed-by": MANAGED_BY,
        "netco.io/service": service,
        "netco.io/environment": environment,
    }


def namespace(name: str, service: str, environment: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": name, "labels": _labels(service, environment)},
    }


def deployment(namespace: str, service: str, environment: str, port: int) -> dict[str, Any]:
    labels = _labels(service, environment)
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": service, "namespace": namespace, "labels": labels},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app.kubernetes.io/name": service}},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [
                        {
                            "name": service,
                            "image": WORKLOAD_IMAGE,
                            "args": ["--port", str(port)],
                            "ports": [{"containerPort": port, "protocol": "TCP"}],
                            "readinessProbe": {"tcpSocket": {"port": port}, "periodSeconds": 2},
                        }
                    ]
                },
            },
        },
    }


def service(namespace: str, service: str, environment: str, port: int) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": service,
            "namespace": namespace,
            "labels": _labels(service, environment),
        },
        "spec": {
            "selector": {"app.kubernetes.io/name": service},
            "ports": [{"name": "app", "port": port, "targetPort": port, "protocol": "TCP"}],
        },
    }


def network_policy(
    namespace: str, service: str, environment: str, port: int, zones: list[str]
) -> dict[str, Any]:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": f"{service}-ingress",
            "namespace": namespace,
            "labels": _labels(service, environment),
        },
        "spec": {
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": service}},
            "policyTypes": ["Ingress"],
            "ingress": [
                {
                    "from": [
                        {
                            "namespaceSelector": {
                                "matchExpressions": [
                                    {"key": ZONE_LABEL, "operator": "In", "values": sorted(zones)}
                                ]
                            }
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": port}],
                }
            ],
        },
    }


def exposure_objects(
    namespace_name: str, service_name: str, environment: str, port: int, zones: list[str]
) -> list[dict[str, Any]]:
    """All objects for one exposure, in creation order."""
    return [
        namespace(namespace_name, service_name, environment),
        deployment(namespace_name, service_name, environment, port),
        service(namespace_name, service_name, environment, port),
        network_policy(namespace_name, service_name, environment, port, zones),
    ]
