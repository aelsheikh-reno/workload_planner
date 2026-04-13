"""Thin Asana REST API client using only stdlib (urllib).

Configure via env vars:
  ASANA_PAT          — Personal Access Token
  ASANA_PROJECT_GID  — Asana project GID to sync against

Usage:
  client = AsanaClient(pat=os.environ["ASANA_PAT"])
  tasks  = client.get_tasks(project_gid="12345")
  client.update_task("67890", {"due_on": "2026-05-01", "assignee": "me"})
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class AsanaAPIError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__("Asana API error %d: %s" % (status, body))
        self.status = status
        self.body = body


class AsanaClient:
    """Minimal Asana REST client (no third-party dependencies)."""

    BASE_URL = "https://app.asana.com/api/1.0"

    def __init__(self, pat: str) -> None:
        if not pat:
            raise ValueError("Asana PAT must not be empty.")
        self._pat = pat

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = self.BASE_URL + path
        if params:
            query = "&".join("%s=%s" % (k, v) for k, v in params.items())
            url = url + "?" + query

        data = json.dumps({"data": body}).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": "Bearer %s" % self._pat,
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AsanaAPIError(exc.code, body)

    def get_tasks(self, project_gid: str) -> List[Dict[str, Any]]:
        """Return all tasks in a project with relevant scheduling fields."""
        result = self._request(
            "GET",
            "/tasks",
            params={
                "project": project_gid,
                "opt_fields": "gid,name,due_on,start_on,assignee.gid,completed,notes,parent.gid,estimated_hours,custom_fields.name,custom_fields.number_value,custom_fields.display_value",
                "limit": "100",
            },
        )
        return result.get("data", [])

    def get_task(self, task_gid: str) -> Dict[str, Any]:
        result = self._request("GET", "/tasks/%s" % task_gid)
        return result.get("data", {})

    def update_task(self, task_gid: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Update fields on a task. Common fields: due_on, start_on, assignee."""
        result = self._request("PUT", "/tasks/%s" % task_gid, body=fields)
        return result.get("data", {})

    def get_project(self, project_gid: str) -> Dict[str, Any]:
        result = self._request("GET", "/projects/%s" % project_gid)
        return result.get("data", {})

    def get_workspaces(self) -> List[Dict[str, Any]]:
        """Return all workspaces the PAT has access to."""
        result = self._request("GET", "/workspaces", params={"opt_fields": "gid,name"})
        return result.get("data", [])

    def get_projects(self, workspace_gid: str) -> List[Dict[str, Any]]:
        """Return all projects in a workspace."""
        result = self._request("GET", "/projects", params={
            "workspace": workspace_gid,
            "opt_fields": "gid,name,color,archived",
            "limit": "100",
        })
        return result.get("data", [])

    def get_workspace_users(self, workspace_gid: str) -> List[Dict[str, Any]]:
        """Return all users in a workspace with gid, name, email."""
        result = self._request("GET", "/users", params={
            "workspace": workspace_gid,
            "opt_fields": "gid,name,email",
            "limit": "100",
        })
        return result.get("data", [])

    def create_task(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new task. Key fields: name, projects[], start_on, due_on, assignee, notes, parent."""
        result = self._request("POST", "/tasks", body=fields)
        return result.get("data", {})

    def add_dependencies(self, task_gid: str, dependency_gids: List[str]) -> None:
        """Declare predecessor tasks for task_gid (creates FS-style dependency links)."""
        self._request(
            "POST",
            "/tasks/%s/addDependencies" % task_gid,
            body={"dependencies": dependency_gids},
        )

    def get_task_dependencies(self, task_gid: str) -> List[Dict[str, Any]]:
        """Return predecessor tasks for a given task."""
        result = self._request(
            "GET",
            "/tasks/%s/dependencies" % task_gid,
            params={"opt_fields": "gid"},
        )
        return result.get("data", [])

    def delete_task(self, task_gid: str) -> None:
        """Delete a task by GID."""
        self._request("DELETE", "/tasks/%s" % task_gid)
