import httpx
import pytest

from integrations.jira import JiraClient, JiraError, pick_transition, to_adf


def test_to_adf_splits_paragraphs_and_lines() -> None:
    assert to_adf("Line 1\nLine 2\n\nParagraph 2") == {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Line 1"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "Line 2"},
                ],
            },
            {"type": "paragraph", "content": [{"type": "text", "text": "Paragraph 2"}]},
        ],
    }


def _transition(id_: str, name: str, category: str) -> dict:
    return {"id": id_, "to": {"name": name, "statusCategory": {"key": category}}}


def test_pick_transition_uses_the_category_not_the_translated_name() -> None:
    transitions = [_transition("11", "À faire", "new"), _transition("31", "Terminé", "done")]
    assert pick_transition(transitions, "done")["id"] == "31"
    with pytest.raises(JiraError, match="indeterminate"):
        pick_transition(transitions, "indeterminate")


def test_jira_error_messages_are_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"errorMessages": ["No project could be found with key 'NOPE'."], "errors": {}}
        return httpx.Response(404, json=body)

    client = JiraClient("https://example.atlassian.net", "u", "t", httpx.MockTransport(handler))
    with pytest.raises(JiraError, match="404: No project could be found") as excinfo:
        client.get_project("NOPE")
    assert excinfo.value.status == 404


@pytest.mark.recorded
def test_issue_lifecycle(jira: JiraClient) -> None:
    issue = jira.create_issue(
        "NETOPS",
        "[test] Exposition de test-api (enregistrement des tests)",
        "Ticket créé par les tests enregistrés du dépôt.\n\nAucune action réelle.",
    )
    assert issue["key"].startswith("NETOPS-")

    comment = jira.add_comment(issue["key"], "[test] Commentaire enregistré.")
    assert comment["id"]

    attachments = jira.attach(issue["key"], "fiche-test.md", b"# Fiche de test\n")
    assert attachments[0]["filename"] == "fiche-test.md"

    jira.transition(issue["key"], "done")
    status = jira.get_issue(issue["key"], fields=["status"])["fields"]["status"]
    assert status["statusCategory"]["key"] == "done"
