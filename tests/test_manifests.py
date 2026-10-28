from k8s.manifests import ZONE_LABEL, exposure_objects


def test_exposure_objects_in_creation_order() -> None:
    objects = exposure_objects("svc-catalogue-api-dev", "catalogue-api", "dev", 8080, ["dev"])
    assert [o["kind"] for o in objects] == ["Namespace", "Deployment", "Service", "NetworkPolicy"]
    assert {o["metadata"].get("namespace", o["metadata"]["name"]) for o in objects} == {
        "svc-catalogue-api-dev"
    }


def test_workload_listens_on_the_requested_port() -> None:
    deployment = exposure_objects("ns", "api", "dev", 5432, ["data"])[1]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["args"] == ["--port", "5432"]
    assert container["ports"] == [{"containerPort": 5432, "protocol": "TCP"}]


def test_network_policy_only_admits_the_requested_zones_on_the_port() -> None:
    policy = exposure_objects("ns", "api", "prod", 443, ["internet", "dev"])[3]
    assert policy["spec"]["podSelector"] == {"matchLabels": {"app.kubernetes.io/name": "api"}}
    assert policy["spec"]["policyTypes"] == ["Ingress"]
    (rule,) = policy["spec"]["ingress"]
    selector = rule["from"][0]["namespaceSelector"]["matchExpressions"][0]
    assert selector == {"key": ZONE_LABEL, "operator": "In", "values": ["dev", "internet"]}
    assert rule["ports"] == [{"protocol": "TCP", "port": 443}]
