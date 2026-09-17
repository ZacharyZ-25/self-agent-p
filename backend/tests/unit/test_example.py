import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, discover_persona_dir
from app.demo import app
from app.services.persona_service import PersonaService


def test_example_is_complete_fictional_and_not_approved():
    service = PersonaService(discover_persona_dir())
    report = service.validate()
    assert report.structural_valid and report.complete
    assert report.qa_count == 30
    assert not report.approved
    assert not report.production_ready
    assert service.load().public_profile()["display_name"] == "Example Candidate"


def test_offline_demo_json_stream_and_profile():
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/v1/profile").json()["display_name"] == "Example Candidate"
        reply = client.post("/api/v1/chat", json={"message": "hello"})
        assert reply.status_code == 200
        assert "Offline demo" in reply.json()["reply"]
        stream = client.post("/api/v1/chat/stream", json={"message": "hello"})
        assert stream.status_code == 200
        assert all(f"event: {name}" in stream.text for name in ["meta", "delta", "done"])


def test_production_accepts_deployer_https_origin():
    assert Settings(app_env="production", cors_origins="https://my-site.example").is_production


@pytest.mark.parametrize("origin", ["*", "", "http://localhost:8080", "https://a.example/path",
                                    "https://a.example,https://a.example"])
def test_production_rejects_invalid_origins(origin):
    with pytest.raises(ValidationError):
        Settings(app_env="production", cors_origins=origin)
