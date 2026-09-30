
import pytest
import yaml

from app.config import Settings
from app.knowledge.persona_migration import prepare_migration
from app.models.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.persona_service import PersonaService


@pytest.fixture
def legacy(tmp_path):
    files = {
        "manifest.yaml": {"schema_version": 1, "persona_version": "fictional-1",
                          "approved": True, "last_verified_at": "2026-09-01",
                          "required_files": list(PersonaService.CORE_FILES - {"manifest.yaml"})},
        "profile.yaml": {"schema_version": 1, "identity": {
            "display_name": "Fictional Owner", "current_status": "Old thesis phase",
            "one_line_intro_zh": "旧介绍", "one_line_intro_en": "Old introduction",
            "languages": ["Chinese"]}, "education": [{"institution": "Example Institute",
            "degree": "MSc Robotics", "current_thesis": "Old experiment",
            "expected_graduation": "2027-06"}], "skills": {
                "proficient": ["Python"], "learning": ["Old learning direction"]},
            "career": {"target_roles": ["Old role"]}},
        "projects.yaml": {"schema_version": 1, "projects": [{"id": "atlas",
            "name": "Atlas", "public": True, "summary": "Old project summary",
            "role": "Developer", "personal_contributions": ["Old contribution"],
            "stack": ["Python"], "results": ["Old result"]}]},
        "voice_rules.yaml": {"schema_version": 1, "perspective": "first_person",
                             **{key: "concise" for key in (
                                 "tone", "sentence_length", "directness", "detail_level",
                                 "humor_style", "emoji_usage", "language_switching")}},
        "boundaries.yaml": {"schema_version": 1, "disallowed": ["Private addresses"]},
    }
    for name, value in files.items():
        (tmp_path / name).write_text(yaml.safe_dump(value), encoding="utf-8")
    (tmp_path / "qa_pairs.md").write_text(
        "## Q: Project progress?\nA: Old result\n" + "\n".join(
            f"## Q: Stable style {i}?\nA: Concise answer." for i in range(2, 31)
        ), encoding="utf-8"
    )
    (tmp_path / "system_prompt.md").write_text("使用第一人称。", encoding="utf-8")
    return tmp_path


def configuration():
    return {"persona_version": "fictional-2", "performed_at": "2026-09-30",
            "stable_identity": {"stable_title": "Robotics", "stable_intro_zh": "机器人背景",
                                "stable_intro_en": "Robotics background"},
            "qa_routes": {i: "atlas" if i == 1 else "core" for i in range(1, 31)}}


def test_migration_preserves_dated_facts_and_removes_them_from_fallback(legacy, tmp_path):
    assert PersonaService(legacy).validate().production_ready
    migration = prepare_migration(legacy, configuration())
    document = next(d for d in migration.documents if d.document_id == "persona-atlas")
    assert document.source_date == "2026-09-01"
    assert "Old result" in document.body and "Old contribution" in document.body
    assert "Project progress?" in document.body
    candidate = tmp_path / "core"
    candidate.mkdir()
    for name, text in migration.core_files.items():
        (candidate / name).write_text(text, encoding="utf-8")
    service = PersonaService(candidate)
    assert service.validate().production_ready
    snapshot = service.load()
    assert snapshot.profile["education"][0]["institution"] == "Example Institute"
    assert snapshot.public_profile()["title"] == "Robotics"
    chat = ChatService(Settings(_env_file=None), snapshot, object())
    messages = chat.build_messages(ChatRequest(message="Project progress?"))
    context = "\n".join(m["content"] for m in messages)
    for old in ("Old result", "Old role", "Old thesis phase", "Old experiment"):
        assert old not in context
    assert "知识库" in context


def test_migration_requires_all_original_answers_to_be_accounted_for(legacy):
    config = configuration()
    config["qa_routes"].pop(1)
    with pytest.raises(ValueError, match="Every original Q&A"):
        prepare_migration(legacy, config)


def test_schema_two_rejects_restored_dynamic_facts(legacy, tmp_path):
    migration = prepare_migration(legacy, configuration())
    candidate = tmp_path / "core"
    candidate.mkdir()
    for name, text in migration.core_files.items():
        (candidate / name).write_text(text, encoding="utf-8")
    profile = yaml.safe_load((candidate / "profile.yaml").read_text(encoding="utf-8"))
    profile["career"] = {"target_roles": ["Old role"]}
    (candidate / "profile.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    assert not PersonaService(candidate).validate().structural_valid
