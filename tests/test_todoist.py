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


@pytest.mark.asyncio
async def test_create_task_returns_created_task(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", todoist_api_token="token")
    output = TodoistOutput(settings)
    response = httpx.Response(200, json={"id": "task-9"}, request=httpx.Request("POST", "/tasks"))
    client = FakeClient([response])

    task = await output._create_task(client, "project-1", "Chicken thighs - $1.99")

    assert task == {"id": "task-9"}


@pytest.mark.asyncio
async def test_completed_task_ids_paginates_by_cursor(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", todoist_api_token="token")
    output = TodoistOutput(settings)
    client = FakeClient(
        [
            httpx.Response(
                200,
                json={"items": [{"id": "task-1"}], "next_cursor": "page-2"},
                request=httpx.Request("GET", "/tasks/completed/by_completion_date"),
            ),
            httpx.Response(
                200,
                json={"items": [{"id": "task-2"}], "next_cursor": None},
                request=httpx.Request("GET", "/tasks/completed/by_completion_date"),
            ),
        ]
    )

    ids = await output._completed_task_ids(client)

    assert ids == {"task-1", "task-2"}
    assert "cursor" not in client.requests[0][2]["params"]
    assert client.requests[1][2]["params"]["cursor"] == "page-2"


@pytest.mark.asyncio
async def test_harvest_outcomes_marks_completed_and_ignored(tmp_path, monkeypatch):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", todoist_api_token="token")
    output = TodoistOutput(settings)

    async def fake_completed_task_ids(_client):
        return {"task-1"}

    monkeypatch.setattr(output, "_completed_task_ids", fake_completed_task_ids)

    outcomes = await output.harvest_outcomes(["task-1", "task-2"])

    assert outcomes == {"task-1": "purchased", "task-2": "ignored"}


@pytest.mark.asyncio
async def test_harvest_outcomes_returns_empty_without_token(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", todoist_api_token="")
    output = TodoistOutput(settings)

    outcomes = await output.harvest_outcomes(["task-1"])

    assert outcomes == {}
