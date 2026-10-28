"""Deploy the process, the decision table and the forms: python -m scenario.deploy"""

import sys
from pathlib import Path

from scenario.camunda import camunda_client

BPMN_DIR = Path(__file__).resolve().parents[2] / "bpmn"


def resources() -> list[Path]:
    return sorted(
        path for pattern in ("*.bpmn", "*.dmn", "*.form") for path in BPMN_DIR.glob(pattern)
    )


def main() -> int:
    files = resources()
    result = camunda_client().deploy_resources_from_files(files)
    print(f"Deployed {len(files)} resources: {', '.join(f.name for f in files)}")
    print(f"Deployment key: {result.deployment_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
