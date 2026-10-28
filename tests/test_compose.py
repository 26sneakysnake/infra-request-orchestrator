import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

# image: repository:${VARIABLE:-default}, where the default is an explicit version.
PINNED_IMAGE = re.compile(r"[\w./-]+:\$\{[A-Z_]+:-v?\d[\w.-]*\}")


def test_stack_services_are_declared() -> None:
    assert {"orchestration", "connectors", "vcsim"} <= COMPOSE["services"].keys()


def test_every_image_is_pinned_to_a_version() -> None:
    for name, service in COMPOSE["services"].items():
        assert PINNED_IMAGE.fullmatch(service["image"]), f"{name}: {service['image']}"


def test_orchestration_config_file_exists() -> None:
    assert (ROOT / COMPOSE["configs"]["orchestration-config"]["file"]).is_file()
