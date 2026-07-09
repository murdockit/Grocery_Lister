from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import session_scope
from app.deals import SelectedDeal
from app.http import with_retries
from app.models import AppState, utc_now
from app.outputs.base import OutputAdapter

PROJECT_ID_KEY = "todoist_project_id"
COMPLETED_LOOKBACK_DAYS = 14


def _todoist_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        items = payload["results"]
    else:
        raise RuntimeError(f"Unexpected Todoist response shape: {type(payload).__name__}")

    if not all(isinstance(item, dict) for item in items):
        raise RuntimeError("Unexpected Todoist response item shape")
    return items


class TodoistOutput(OutputAdapter):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def publish(self, deals: list[SelectedDeal]) -> dict[str, str]:
        if not self.settings.todoist_api_token:
            return {}
        async with httpx.AsyncClient(
            base_url=self.settings.todoist_api_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.settings.todoist_api_token}"},
            timeout=self.settings.http_timeout_seconds,
        ) as client:
            project_id = await self._project_id(client)
            await self._clear_project(client, project_id)
            task_ids: dict[str, str] = {}
            for deal in deals:
                task = await self._create_task(client, project_id, deal.task_content)
                if task is not None:
                    task_ids[deal.candidate.upc] = str(task["id"])
            return task_ids

    async def harvest_outcomes(self, task_ids: list[str]) -> dict[str, str]:
        """Map each requested Todoist task id to 'purchased' or 'ignored'.

        Call this before publish() clears the project for the new week's list.
        """
        if not task_ids or not self.settings.todoist_api_token:
            return {}
        async with httpx.AsyncClient(
            base_url=self.settings.todoist_api_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.settings.todoist_api_token}"},
            timeout=self.settings.http_timeout_seconds,
        ) as client:
            completed_ids = await self._completed_task_ids(client)
        return {
            task_id: "purchased" if task_id in completed_ids else "ignored"
            for task_id in task_ids
        }

    async def _project_id(self, client: httpx.AsyncClient) -> str:
        with session_scope(self.settings.database_url) as session:
            cached = _get_state(session, PROJECT_ID_KEY)
        if cached and await self._project_exists(client, cached):
            return cached

        projects = _todoist_items(await self._request_json(client, "GET", "/projects"))
        for project in projects:
            if project.get("name") == self.settings.todoist_project_name:
                project_id = str(project["id"])
                self._store_project_id(project_id)
                return project_id

        project = await self._request_json(
            client,
            "POST",
            "/projects",
            json={"name": self.settings.todoist_project_name},
        )
        project_id = str(project["id"])
        self._store_project_id(project_id)
        return project_id

    async def _project_exists(self, client: httpx.AsyncClient, project_id: str) -> bool:
        response = await self._request(client, "GET", f"/projects/{project_id}", tolerate_404=True)
        return response.status_code == 200

    async def _clear_project(self, client: httpx.AsyncClient, project_id: str) -> None:
        tasks = _todoist_items(
            await self._request_json(client, "GET", "/tasks", params={"project_id": project_id})
        )
        for task in tasks:
            task_id = str(task["id"])
            response = await self._request(client, "DELETE", f"/tasks/{task_id}", tolerate_404=True)
            if response.status_code == 405:
                await self._request(client, "POST", f"/tasks/{task_id}/close", tolerate_404=True)

    async def _create_task(
        self, client: httpx.AsyncClient, project_id: str, content: str
    ) -> dict[str, Any] | None:
        return await self._request_json(
            client,
            "POST",
            "/tasks",
            json={"project_id": project_id, "content": content},
        )

    async def _completed_task_ids(self, client: httpx.AsyncClient) -> set[str]:
        since = utc_now() - timedelta(days=COMPLETED_LOOKBACK_DAYS)
        until = utc_now()
        ids: set[str] = set()
        cursor: str | None = None
        while True:
            params: dict[str, str] = {
                "since": since.isoformat(timespec="seconds"),
                "until": until.isoformat(timespec="seconds"),
            }
            if cursor:
                params["cursor"] = cursor
            payload = await self._request_json(
                client, "GET", "/tasks/completed/by_completion_date", params=params
            )
            if not isinstance(payload, dict):
                break
            ids.update(str(item["id"]) for item in payload.get("items", []))
            cursor = payload.get("next_cursor")
            if not cursor:
                break
        return ids

    async def _request_json(
        self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any
    ) -> Any:
        response = await self._request(client, method, path, **kwargs)
        if response.status_code == 204:
            return None
        return response.json()

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        tolerate_404: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        async def operation() -> httpx.Response:
            response = await client.request(method, path, **kwargs)
            if response.status_code == 410:
                raise RuntimeError(
                    "Todoist API returned 410 Gone. Check developer.todoist.com and update "
                    "TODOIST_API_BASE_URL if Todoist has migrated endpoint versions."
                )
            if tolerate_404 and response.status_code == 404:
                return response
            response.raise_for_status()
            return response

        return await with_retries(operation)

    def _store_project_id(self, project_id: str) -> None:
        with session_scope(self.settings.database_url) as session:
            state = session.scalar(select(AppState).where(AppState.key == PROJECT_ID_KEY))
            if state is None:
                session.add(AppState(key=PROJECT_ID_KEY, value=project_id))
            else:
                state.value = project_id


def _get_state(session: Session, key: str) -> str | None:
    state = session.scalar(select(AppState).where(AppState.key == key))
    return state.value if state else None
