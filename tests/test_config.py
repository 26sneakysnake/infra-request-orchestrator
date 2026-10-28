import pytest

from integrations.config import ConfigError, JiraSettings, ServiceNowSettings


def test_missing_settings_are_listed() -> None:
    environ = {"SERVICENOW_INSTANCE_URL": "https://example.service-now.com"}
    with pytest.raises(ConfigError, match="SERVICENOW_USERNAME, SERVICENOW_PASSWORD"):
        ServiceNowSettings.from_env(environ)


def test_blank_values_count_as_missing() -> None:
    environ = {
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_EMAIL": "user@example.com",
        "JIRA_API_TOKEN": "  ",
        "JIRA_PROJECT_KEY": "NETOPS",
    }
    with pytest.raises(ConfigError, match="JIRA_API_TOKEN"):
        JiraSettings.from_env(environ)


def test_trailing_slash_is_removed_from_urls() -> None:
    environ = {
        "JIRA_BASE_URL": "https://example.atlassian.net/",
        "JIRA_EMAIL": "user@example.com",
        "JIRA_API_TOKEN": "token",
        "JIRA_PROJECT_KEY": "NETOPS",
    }
    assert JiraSettings.from_env(environ).base_url == "https://example.atlassian.net"
