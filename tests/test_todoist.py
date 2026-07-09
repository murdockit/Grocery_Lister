import httpx
import pytest

from app.config import Settings
from app.outputs.todoist import TodoistOutput


class FakeClient:
    def __init__(self) -> None:
        self.requests = []

    async def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
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
