"""Settings for the external tools, read from the environment and the local .env file."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required settings are missing."""


def _require(names: tuple[str, ...], environ: Mapping[str, str] | None) -> dict[str, str]:
    if environ is None:
        # Real environment variables win over .env (CI secrets, shell overrides).
        load_dotenv(override=False)
        environ = os.environ
    values = {name: environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(f"missing settings (see .env.example): {', '.join(missing)}")
    return values


@dataclass(frozen=True)
class ServiceNowSettings:
    instance_url: str
    username: str
    password: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        v = _require(
            ("SERVICENOW_INSTANCE_URL", "SERVICENOW_USERNAME", "SERVICENOW_PASSWORD"), environ
        )
        return cls(
            v["SERVICENOW_INSTANCE_URL"].rstrip("/"),
            v["SERVICENOW_USERNAME"],
            v["SERVICENOW_PASSWORD"],
        )


@dataclass(frozen=True)
class JiraSettings:
    base_url: str
    email: str
    api_token: str
    project_key: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        v = _require(("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"), environ)
        return cls(
            v["JIRA_BASE_URL"].rstrip("/"),
            v["JIRA_EMAIL"],
            v["JIRA_API_TOKEN"],
            v["JIRA_PROJECT_KEY"],
        )
