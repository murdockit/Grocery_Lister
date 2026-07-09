from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import session_scope
from app.deals import SelectedDeal
from app.http import with_retries
from app.models import AppState
from app.outputs.base import OutputAdapter

PROJECT_ID_KEY = "todoist_project_id"


class TodoistOutput(OutputAdapter):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def publish(self, deals: list[SelectedDeal]) -> None:
        if not self.settings.todoist_api_token:
            return
        async with httpx.AsyncClient(
            base_url=self.settings.todoist_api_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.settings.todoist_api_token}"},
            timeout=self.settings.http_timeout_seconds,
        ) as client:
            project_id = await self._project_id(client)
            await self._clear_project(client, project_id)
            for deal in deals:
                await self._create_task(client, project_id, deal.task_content)

    async def _project_id(self, client: httpx.AsyncClient) -> str:
        with session_scope(self.settings.database_url) as session:
            cached = _get_state(session, PROJECT_ID_KEY)
        if cached and await self._project_exists(client, cached):
            return cached

        projects = await self._request_json(client, "GET", "/projects")
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
        tasks = await self._request_json(client, "GET", "/tasks", params={"project_id": project_id})
        for task in tasks:
            task_id = str(task["id"])
            response = await self._request(client, "DELETE", f"/tasks/{task_id}", tolerate_404=True)
            if response.status_code == 405:
                await self._request(client, "POST", f"/tasks/{task_id}/close", tolerate_404=True)

    async def _create_task(self, client: httpx.AsyncClient, project_id: str, content: str) -> None:
        await self._request_json(
            client,
            "POST",
            "/tasks",
            json={"project_id": project_id, "content": content},
        )

    async def _request_json(self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> Any:
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
