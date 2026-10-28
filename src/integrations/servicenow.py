"""Thin client for the ServiceNow REST APIs: Table, Attachment and Service Catalog."""

from typing import Any, Self

import httpx


class ServiceNowError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"ServiceNow {status}: {message}")
        self.status = status


class ServiceNowClient:
    def __init__(
        self,
        instance_url: str,
        username: str,
        password: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._http = httpx.Client(
            base_url=instance_url,
            auth=(username, password),
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

    # Table API
    def create(self, table: str, fields: dict[str, str]) -> dict[str, Any]:
        return self._request("POST", f"/api/now/table/{table}", json=fields)

    def get(self, table: str, sys_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/now/table/{table}/{sys_id}")

    def query(
        self, table: str, query: str = "", fields: list[str] | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"sysparm_query": query, "sysparm_limit": limit}
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        return self._request("GET", f"/api/now/table/{table}", params=params)

    def update(self, table: str, sys_id: str, fields: dict[str, str]) -> dict[str, Any]:
        return self._request("PATCH", f"/api/now/table/{table}/{sys_id}", json=fields)

    def set_state(self, table: str, sys_id: str, state: int | str) -> dict[str, Any]:
        return self.update(table, sys_id, {"state": str(state)})

    def add_comment(
        self, table: str, sys_id: str, text: str, internal: bool = False
    ) -> dict[str, Any]:
        """Post a comment visible to the requester, or an internal work note."""
        return self.update(table, sys_id, {"work_notes" if internal else "comments": text})

    # Attachment API
    def attach(
        self,
        table: str,
        sys_id: str,
        filename: str,
        content: bytes,
        content_type: str = "text/markdown",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/now/attachment/file",
            params={"table_name": table, "table_sys_id": sys_id, "file_name": filename},
            content=content,
            headers={"Content-Type": content_type},
        )

    # Service Catalog API
    def list_catalogs(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._request(
            "GET", "/api/sn_sc/servicecatalog/catalogs", params={"sysparm_limit": limit}
        )

    def order_catalog_item(self, item_sys_id: str, variables: dict[str, str]) -> dict[str, Any]:
        """Order one unit of a catalog item; ServiceNow creates the REQ and its RITM."""
        return self._request(
            "POST",
            f"/api/sn_sc/servicecatalog/items/{item_sys_id}/order_now",
            json={"sysparm_quantity": "1", "variables": variables},
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._http.request(method, path, **kwargs)
        if "json" not in response.headers.get("content-type", ""):
            # A hibernating developer instance answers with an HTML page or a redirect.
            raise ServiceNowError(
                response.status_code,
                "non-JSON response; the instance may be hibernating (log in to it to wake it up)",
            )
        body = response.json()
        if response.is_error:
            error = body.get("error") or {}
            raise ServiceNowError(response.status_code, error.get("message") or response.text)
        return body["result"]
