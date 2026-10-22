"""Scaffold checks: the package imports and both services expose a health probe."""

from fastapi.testclient import TestClient

import analyst


def test_package_exposes_version() -> None:
    assert isinstance(analyst.__version__, str)


def test_api_healthz() -> None:
    from app.api.main import app

    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_admin_healthz() -> None:
    from app.admin.main import app

    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
