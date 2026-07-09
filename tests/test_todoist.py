import httpx
import pytest

from app.config import Settings
from app.db import init_db
from app.outputs.todoist import TodoistOutput


class FakeClient:
    def __init__(self, responses=None) -> None:
        self.requests = []
        self.responses = list(responses or [])

    async def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return httpx.Response(200, json={"id": "task-1"}, request=httpx.Request(method, path))


@pytest.mark.asyncio
async def test_todoist_create_task_payload(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", todoist_api_token="token")
    output = TodoistOutput(settings)
    client = FakeClient()

    await output._create_task(client, "project-1", "Chicken thighs - $1.99")

    assert client.requests == [
        (
            "POST",
            "/tasks",
            {"json": {"project_id": "project-1", "content": "Chicken thighs - $1.99"}},
        )
    ]


@pytest.mark.asyncio
async def test_todoist_project_id_accepts_paginated_projects(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", todoist_api_token="token")
    init_db(settings.database_url)
    output = TodoistOutput(settings)
    client = FakeClient(
        [
            httpx.Response(
                200,
                json={"results": [{"id": "project-1", "name": "Weekly Deals"}]},
                request=httpx.Request("GET", "/projects"),
            )
        ]
    )

    project_id = await output._project_id(client)

    assert project_id == "project-1"


@pytest.mark.asyncio
async def test_todoist_clear_project_accepts_paginated_tasks(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", todoist_api_token="token")
    output = TodoistOutput(settings)
    client = FakeClient(
        [
            httpx.Response(
                200,
                json={"results": [{"id": "task-1"}]},
                request=httpx.Request("GET", "/tasks"),
            ),
            httpx.Response(204, request=httpx.Request("DELETE", "/tasks/task-1")),
        ]
    )

    await output._clear_project(client, "project-1")

    assert client.requests == [
        ("GET", "/tasks", {"params": {"project_id": "project-1"}}),
        ("DELETE", "/tasks/task-1", {}),
    ]
