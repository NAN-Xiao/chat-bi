import asyncio

import httpx
import pytest
from fastapi import FastAPI

from apps.dashboard.models.dashboard_model import BaseDashboard, CoreDashboard


@pytest.mark.parametrize("create_by", ["codex", "7482253745313550336", None])
def test_dashboard_response_accepts_string_creator_identifiers(create_by: str | None) -> None:
    app = FastAPI()

    @app.get("/dashboard", response_model=BaseDashboard)
    def get_dashboard() -> CoreDashboard:
        return CoreDashboard(
            id="dashboard-id",
            tenant_id=1,
            name="dashboard",
            pid="root",
            org_id="",
            type="dashboard",
            node_type="leaf",
            level=1,
            create_by=create_by,
        )

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/dashboard")

    response = asyncio.run(send_request())

    assert response.status_code == 200
    assert response.json()["create_by"] == create_by
