"""Read-only, canonical snapshot of an exposure for the diagnosis agent.

The snapshot is taken once, when the verification fails: the agent then reasons on one consistent
state. It is canonical: random pod and ReplicaSet suffixes, timestamps, durations, IP addresses and
counters are removed, and only Warning events are kept. The same broken state therefore gives the
same snapshot, which keeps the agent's prompts stable (recorded answers replay in CI).
"""

import re
from typing import Any

import yaml

from k8s.cluster import Cluster

TIMESTAMP = re.compile(r"\b\d{4}[/-]\d{2}[/-]\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?Z?\s*")
DURATION = re.compile(r"\b\d+(\.\d+)?(ms|s|m|h)\b")
IP_PORT = re.compile(r"\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b")


def _canonical_names(deployments: list[str], pods: list[Any]) -> dict[str, str]:
    """Map generated names (ReplicaSet and pod suffixes) to stable ones."""
    names: dict[str, str] = {}
    counters: dict[str, int] = {}
    for pod in sorted(pods, key=lambda p: (p.metadata.creation_timestamp, p.metadata.name)):
        owner = next((d for d in deployments if pod.metadata.name.startswith(f"{d}-")), None)
        if owner:
            counters[owner] = counters.get(owner, 0) + 1
            names[pod.metadata.name] = f"{owner}-pod-{counters[owner]}"
    return names


def _clean(text: str, names: dict[str, str], deployments: list[str]) -> str:
    for real, canonical in sorted(names.items(), key=lambda item: -len(item[0])):
        text = text.replace(real, canonical)
    for deployment in deployments:
        # Pods the snapshot never saw (rejected by a quota) and ReplicaSets.
        text = re.sub(
            rf"\b{re.escape(deployment)}-[a-z0-9]{{6,10}}-[a-z0-9]{{5}}\b",
            f"{deployment}-pod",
            text,
        )
        text = re.sub(
            rf"\b{re.escape(deployment)}-[a-z0-9]{{6,10}}\b", f"{deployment}-replicaset", text
        )
    text = TIMESTAMP.sub("", text)
    text = IP_PORT.sub("<ip>", text)
    return DURATION.sub("<durée>", text).strip()


def _waiting_reason(pod: Any) -> str:
    for status in pod.status.container_statuses or []:
        if status.state and status.state.waiting:
            reason = status.state.waiting.reason or "Waiting"
            # ErrImagePull and ImagePullBackOff alternate over time for the same fault.
            return "ImagePullBackOff" if reason == "ErrImagePull" else reason
    return ""


def collect(
    cluster: Cluster, namespace: str, service: str, request: dict[str, Any], verification: dict
) -> dict[str, Any]:
    """request: what the validated request asked for (service, port, zones)."""
    deployments = cluster.apps.list_namespaced_deployment(namespace).items
    deployment_names = [d.metadata.name for d in deployments]
    pods = cluster.core.list_namespaced_pod(namespace).items
    names = _canonical_names(deployment_names, pods)
    services = cluster.core.list_namespaced_service(namespace).items
    policies = cluster.networking.list_namespaced_network_policy(namespace).items
    quotas = cluster.core.list_namespaced_resource_quota(namespace).items
    slices = cluster.discovery.list_namespaced_endpoint_slice(namespace).items

    resources, objects, logs = [], {}, {}
    for d in sorted(deployments, key=lambda d: d.metadata.name):
        container = d.spec.template.spec.containers[0]
        ready = d.status.ready_replicas or 0
        resources.append(
            f"Deployment {d.metadata.name}: image {container.image}, ready replicas {ready}/"
            f"{d.spec.replicas}"
        )
        objects[f"Deployment/{d.metadata.name}"] = {
            "replicas": d.spec.replicas,
            "selector": d.spec.selector.match_labels,
            "podLabels": d.spec.template.metadata.labels,
            "image": container.image,
            "args": container.args,
            "containerPorts": [p.container_port for p in container.ports or []],
        }
    for p in sorted(pods, key=lambda p: names.get(p.metadata.name, p.metadata.name)):
        name = names.get(p.metadata.name, p.metadata.name)
        ready = all(s.ready for s in p.status.container_statuses or []) and bool(
            p.status.container_statuses
        )
        restarts = sum(s.restart_count for s in p.status.container_statuses or [])
        waiting = _waiting_reason(p)
        resources.append(
            f"Pod {name}: {p.status.phase}, {'ready' if ready else 'not ready'}, restarts "
            f"{restarts}{', waiting: ' + waiting if waiting else ''}"
        )
        labels = {k: v for k, v in (p.metadata.labels or {}).items() if k != "pod-template-hash"}
        objects[f"Pod/{name}"] = {"labels": labels, "phase": p.status.phase}
        try:
            text = cluster.core.read_namespaced_pod_log(p.metadata.name, namespace, tail_lines=20)
            lines = [_clean(line, names, deployment_names) for line in text.splitlines()]
            logs[name] = "\n".join(line for line in lines if line) or "(journal vide)"
        except Exception:
            logs[name] = "(pas de journal : le conteneur n'a pas démarré)"
    for s in sorted(services, key=lambda s: s.metadata.name):
        ports = [f"{p.port} -> targetPort {p.target_port}" for p in s.spec.ports]
        endpoints = sum(
            1
            for slice_ in slices
            if (slice_.metadata.labels or {}).get("kubernetes.io/service-name") == s.metadata.name
            for e in slice_.endpoints or []
            if e.conditions and e.conditions.ready
        )
        selector = ", ".join(f"{k}={v}" for k, v in sorted((s.spec.selector or {}).items()))
        resources.append(
            f"Service {s.metadata.name}: ports {', '.join(ports)}, selector {selector}, "
            f"ready endpoints {endpoints}"
        )
        objects[f"Service/{s.metadata.name}"] = {
            "selector": s.spec.selector,
            "ports": [{"port": p.port, "targetPort": p.target_port} for p in s.spec.ports],
        }
    for n in sorted(policies, key=lambda n: n.metadata.name):
        rules = []
        for rule in n.spec.ingress or []:
            zones = sorted(
                v
                for peer in rule._from or []
                if peer.namespace_selector
                for expr in peer.namespace_selector.match_expressions or []
                for v in expr.values or []
            )
            ports = [f"{p.port}/{p.protocol}" for p in rule.ports or []]
            rules.append({"fromZones": zones, "ports": ports})
        resources.append(
            f"NetworkPolicy {n.metadata.name}: pods "
            + ", ".join(
                f"{k}={v}" for k, v in sorted((n.spec.pod_selector.match_labels or {}).items())
            )
            + ", ingress "
            + "; ".join(f"from zones {r['fromZones']} on {r['ports']}" for r in rules)
        )
        objects[f"NetworkPolicy/{n.metadata.name}"] = {
            "podSelector": n.spec.pod_selector.match_labels,
            "policyTypes": n.spec.policy_types,
            "ingress": rules,
        }
    for q in sorted(quotas, key=lambda q: q.metadata.name):
        used, hard = q.status.used or {}, q.spec.hard or {}
        usage = ", ".join(f"{k} {used.get(k, '0')}/{v}" for k, v in sorted(hard.items()))
        resources.append(f"ResourceQuota {q.metadata.name}: {usage}")
        objects[f"ResourceQuota/{q.metadata.name}"] = {"hard": hard, "used": used}

    warnings = set()
    for event in cluster.core.list_namespaced_event(namespace).items:
        if event.type != "Warning":
            continue
        kind = event.involved_object.kind
        name = names.get(event.involved_object.name, event.involved_object.name)
        message = _clean(event.message or "", names, deployment_names)
        warnings.add(f"{event.reason} {kind}/{_clean(name, names, deployment_names)}: {message}")

    zones = ", ".join(request["zones"])
    request_text = (
        f"Demande validée : service {request['service']}, port {request['port']}/tcp, zones "
        f"autorisées attendues : {zones}."
    )
    checks = [
        f"zone {c['zone']} : attendue {'joignable' if c['expected'] else 'bloquée'}, observée "
        f"{'joignable' if c['reachable'] else 'bloquée'}{'' if c['ok'] else ' (ÉCHEC)'}"
        for c in verification.get("checks", [])
    ]
    return {
        "namespace": namespace,
        "resources": "\n".join(resources),
        "objects": {
            key: yaml.safe_dump(value, sort_keys=True).strip() for key, value in objects.items()
        },
        "events": "\n".join(sorted(warnings)) or "(aucun événement Warning)",
        "logs": logs,
        "verification": "\n".join([request_text, verification.get("summary", ""), *checks]),
    }
