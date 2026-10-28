"""Apply exposure objects to the kind lab cluster and check that the network rule really holds.

Checks run curl from the probe pod of each zone (infra/kind/zones.yaml): allowed zones must reach
the service, and one zone outside the request must be blocked.
"""

import time
from typing import Any

from kubernetes import client, config, dynamic
from kubernetes.stream import stream

PROBE_POD = "probe"
ALLOWED_GRACE_S = 30.0
FIELD_MANAGER = "infra-request-orchestrator"


class Cluster:
    def __init__(self, context: str | None = "kind-netco") -> None:
        self._context = context
        api_client = config.new_client_from_config(context=context)
        self._dynamic = dynamic.DynamicClient(api_client)
        # Typed clients, also used read-only by k8s.observe.
        self.core = client.CoreV1Api(api_client)
        self.apps = client.AppsV1Api(api_client)
        self.networking = client.NetworkingV1Api(api_client)
        self.discovery = client.DiscoveryV1Api(api_client)

    def apply(self, objects: list[dict[str, Any]]) -> list[str]:
        """Server-side apply, so running the same request twice converges instead of failing."""
        applied = []
        for obj in objects:
            resource = self._dynamic.resources.get(api_version=obj["apiVersion"], kind=obj["kind"])
            resource.server_side_apply(
                body=obj,
                name=obj["metadata"]["name"],
                namespace=obj["metadata"].get("namespace"),
                field_manager=FIELD_MANAGER,
                force_conflicts=True,
            )
            applied.append(f"{obj['kind']}/{obj['metadata']['name']}")
        return applied

    def raise_pod_quota(self, namespace: str, headroom: int = 2) -> list[str]:
        """Give every pod quota of the namespace room for the service's pods (allowed action)."""
        raised = []
        for quota in self.core.list_namespaced_resource_quota(namespace).items:
            hard = quota.spec.hard or {}
            if "pods" not in hard:
                continue
            used = int((quota.status.used or {}).get("pods", "0"))
            target = max(used + headroom, int(hard["pods"]))
            body = {"spec": {"hard": {"pods": str(target)}}}
            self.core.patch_namespaced_resource_quota(quota.metadata.name, namespace, body)
            raised.append(f"ResourceQuota/{quota.metadata.name} pods {hard['pods']} -> {target}")
        return raised

    def snapshot(
        self, namespace: str, service: str, request: dict[str, Any], verification: dict[str, Any]
    ) -> dict[str, Any]:
        from k8s.observe import collect  # observe imports Cluster for typing

        return collect(self, namespace, service, request, verification)

    def delete_namespace(self, name: str) -> None:
        self.core.delete_namespace(name)

    def wait_ready(self, namespace: str, name: str, timeout: float = 120.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.apps.read_namespaced_deployment_status(name, namespace).status
            if status.ready_replicas and status.ready_replicas >= 1:
                return True
            time.sleep(2)
        return False

    def reachable(self, zone: str, url: str) -> bool:
        """Run curl from the probe pod of a zone; True when the service answers with HTTP 200."""
        # stream() switches its ApiClient to websockets while it runs: a private client keeps the
        # jobs that share the main client (apply, read) safe when they run concurrently.
        core = client.CoreV1Api(config.new_client_from_config(context=self._context))
        output = stream(
            core.connect_get_namespaced_pod_exec,
            PROBE_POD,
            f"zone-{zone}",
            command=["curl", "-s", "-o", "/dev/null", "-m", "4", "-w", "%{http_code}", url],
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )
        return output.strip().endswith("200")

    def _reachable_within(self, zone: str, url: str, grace_s: float) -> bool:
        deadline = time.monotonic() + grace_s
        while True:
            if self.reachable(zone, url):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(3)

    def verify(
        self,
        namespace: str,
        service: str,
        port: int,
        allowed_zones: list[str],
        all_zones: list[str],
        ready_timeout: float = 120.0,
    ) -> dict[str, Any]:
        if not self.wait_ready(namespace, service, ready_timeout):
            summary = f"Déploiement {service} jamais prêt ({ready_timeout:.0f} s)"
            return {"ok": False, "checks": [], "summary": summary}
        url = f"http://{service}.{namespace}.svc.cluster.local:{port}/"
        denied = [zone for zone in all_zones if zone not in allowed_zones][:1]
        checks = []
        for zone, expected in [(z, True) for z in allowed_zones] + [(z, False) for z in denied]:
            # A ready pod is not yet a reachable one: service and network policy rules reach the
            # node a few seconds later. An allowed zone gets that grace; a denied one never does.
            reached = self._reachable_within(zone, url, ALLOWED_GRACE_S if expected else 0)
            checks.append(
                {
                    "zone": zone,
                    "expected": expected,
                    "reachable": reached,
                    "ok": reached == expected,
                }
            )
        failed = [c for c in checks if not c["ok"]]
        summary = (
            "Règle réseau conforme"
            if not failed
            else "; ".join(
                f"zone {c['zone']} : {'joignable' if c['reachable'] else 'bloquée'} "
                f"au lieu de {'joignable' if c['expected'] else 'bloquée'}"
                for c in failed
            )
        )
        return {"ok": not failed, "checks": checks, "summary": summary}
