"""Thin client for the Jira Cloud REST API v3."""

from typing import Any, Self

import httpx


class JiraError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Jira {status}: {message}")
        self.status = status


def to_adf(text: str) -> dict[str, Any]:
    """Convert plain text to an Atlassian Document Format document.

    Blank lines separate paragraphs; single newlines become hard breaks.
    """
    paragraphs = []
    for block in text.strip().split("\n\n"):
        inline: list[dict[str, Any]] = []
        for i, line in enumerate(block.strip("\n").split("\n")):
            if i:
                inline.append({"type": "hardBreak"})
            if line:
                inline.append({"type": "text", "text": line})
        paragraphs.append({"type": "paragraph", "content": inline})
    return {"type": "doc", "version": 1, "content": paragraphs}


def pick_transition(transitions: list[dict[str, Any]], category: str) -> dict[str, Any]:
    """Pick the first transition leading to a status of the given category.

    Categories (new, indeterminate, done) do not depend on the site language, unlike status names.
    """
    for transition in transitions:
        if transition["to"]["statusCategory"]["key"] == category:
            return transition
    raise JiraError(409, f"no transition to a status of category {category!r}")


class JiraClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url
        self._http = httpx.Client(
            base_url=f"{base_url}/rest/api/3",
            auth=(email, api_token),
            headers={"Accept": "application/json"},
            transport=transport,
            timeout=timeout,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def myself(self) -> dict[str, Any]:
        return self._request("GET", "/myself")

    def get_project(self, key: str) -> dict[str, Any]:
        return self._request("GET", f"/project/{key}")

    def issue_type_id(self, project_key: str, untranslated_name: str = "Task") -> str:
        """Find an issue type by its English name, whatever the language of the site."""
        meta = self._request("GET", f"/issue/createmeta/{project_key}/issuetypes")
        for issue_type in meta.get("issueTypes") or meta.get("values") or []:
            if issue_type.get("untranslatedName", issue_type["name"]) == untranslated_name:
                return issue_type["id"]
        raise JiraError(404, f"issue type {untranslated_name!r} not found in {project_key}")

    def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Task",
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "description": to_adf(description),
            "issuetype": {"id": self.issue_type_id(project_key, issue_type)},
        }
        if labels:
            fields["labels"] = labels
        return self._request("POST", "/issue", json={"fields": fields})

    def find_issues(self, jql: str, limit: int = 10) -> list[dict[str, Any]]:
        body = {"jql": jql, "fields": ["summary", "status"], "maxResults": limit}
        return self._request("POST", "/search/jql", json=body)["issues"]

    def get_issue(self, key: str, fields: list[str] | None = None) -> dict[str, Any]:
        params = {"fields": ",".join(fields)} if fields else None
        return self._request("GET", f"/issue/{key}", params=params)

    def add_comment(self, key: str, text: str) -> dict[str, Any]:
        return self._request("POST", f"/issue/{key}/comment", json={"body": to_adf(text)})

    def attach(
        self, key: str, filename: str, content: bytes, content_type: str = "text/markdown"
    ) -> list[dict[str, Any]]:
        return self._request(
            "POST",
            f"/issue/{key}/attachments",
            files={"file": (filename, content, content_type)},
            headers={"X-Atlassian-Token": "no-check"},
        )

    def attachments(self, key: str) -> list[str]:
        """File names already attached to an issue."""
        fields = self.get_issue(key, ["attachment"])["fields"]
        return [a["filename"] for a in fields.get("attachment") or []]

    def add_remote_link(self, key: str, url: str, title: str) -> dict[str, Any]:
        """Link the issue to a record in another tool (shown under "Web links").

        The URL doubles as globalId, so linking twice updates the link instead of adding one.
        """
        body = {"globalId": url, "object": {"url": url, "title": title}}
        return self._request("POST", f"/issue/{key}/remotelink", json=body)

    def browse_url(self, key: str) -> str:
        return f"{self.base_url}/browse/{key}"

    def transition(self, key: str, category: str = "done") -> str:
        """Move the issue to a status of the given category; return the new status name."""
        transitions = self._request("GET", f"/issue/{key}/transitions")["transitions"]
        target = pick_transition(transitions, category)
        self._request(
            "POST", f"/issue/{key}/transitions", json={"transition": {"id": target["id"]}}
        )
        return target["to"]["name"]

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._http.request(method, path, **kwargs)
        if response.is_error:
            raise JiraError(response.status_code, _error_message(response))
        if not response.content:
            return None
        return response.json()


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or response.reason_phrase
    messages = list(body.get("errorMessages") or []) + [
        f"{field}: {message}" for field, message in (body.get("errors") or {}).items()
    ]
    return "; ".join(messages) or response.reason_phrase
