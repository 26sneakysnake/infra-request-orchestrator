"""Camunda client shared by the workers and the scripts (local stack: no auth by default)."""

import os

from camunda_orchestration_sdk import CamundaAsyncClient, CamundaClient
from dotenv import load_dotenv


def _configuration() -> dict[str, str]:
    load_dotenv(override=False)
    return {
        "CAMUNDA_REST_ADDRESS": os.environ.get("CAMUNDA_REST_ADDRESS", "http://localhost:8080"),
        "CAMUNDA_AUTH_STRATEGY": os.environ.get("CAMUNDA_AUTH_STRATEGY", "NONE"),
        "CAMUNDA_SDK_LOG_LEVEL": os.environ.get("CAMUNDA_SDK_LOG_LEVEL", "warn"),
    }


def camunda_client() -> CamundaClient:
    return CamundaClient(configuration=_configuration())


def camunda_async_client() -> CamundaAsyncClient:
    return CamundaAsyncClient(configuration=_configuration())
