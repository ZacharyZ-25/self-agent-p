"""Split a legacy Persona into stable identity and dated, private knowledge documents."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.services.persona_service import PersonaService


@dataclass(frozen=True)
class MigrationDocument:
    document_id: str
    title: str
    project: str | None
    source_date: str
    author: str
    body: str


@dataclass(frozen=True)
class PersonaMigration:
    core_files: dict[str, str]
    documents: tuple[MigrationDocument, ...]


def prepare_migration(persona_dir: Path, config: dict) -> PersonaMigration:
    """QA routes are reviewed by the owner; zero keeps a stable answer in Persona.

    Project routes use project IDs; profile routes use status, career or learning.
    All original answers must have a route so no information is silently discarded.
    """
    snapshot = PersonaService(persona_dir).load()
    manifest = yaml.safe_load((persona_dir / "manifest.yaml").read_text(encoding="utf-8"))
    if manifest["schema_version"] != 1:
        raise ValueError("Migration expects a schema 1 Persona; use its original backup to retry")
    profile = copy.deepcopy(snapshot.profile)
    verified = str(manifest["last_verified_at"])
    author = profile["identity"]["display_name"]
    sections: dict[str, dict] = {
        "status": {"title": "身份状态、毕业设计与毕业计划", "data": {}},
        "career": {"title": "职业方向与岗位意向", "data": profile.pop("career", {})},
        "learning": {"title": "技术能力与学习方向", "data": {
            "learning": profile.get("skills", {}).pop("learning", [])
        }},
    }
    identity = profile["identity"]
    for key in ("current_status", "one_line_intro_zh", "one_line_intro_en"):
        sections["status"]["data"][key] = identity.pop(key, None)
    education_updates = []
    for entry in profile.get("education", []):
        updates = {key: entry.pop(key) for key in ("current_thesis", "expected_graduation")
                   if key in entry}
        if updates:
            education_updates.append({"institution": entry["institution"], **updates})
    sections["status"]["data"]["education_updates"] = education_updates
    identity.update(config["stable_identity"])
    for project in snapshot.projects.get("projects", []):
        sections[project["id"]] = {"title": project["name"], "data": project,
                                    "project": project["name"]}
    sections.update({key: {"title": title, "data": {}}
                     for key, title in config.get("extra_documents", {}).items()})
    routes = {int(key): value for key, value in config["qa_routes"].items()}
    expected = set(range(1, len(snapshot.qa_pairs) + 1))
    if set(routes) != expected:
        raise ValueError("Every original Q&A needs an explicit route")
    stable_qa = []
    overrides = {int(key): value for key, value in config.get("qa_overrides", {}).items()}
    for number, pair in enumerate(snapshot.qa_pairs, 1):
        target = routes[number]
        text = f"## Q: {pair.question}\nA: {pair.answer}\n"
        if target == "core":
            stable_qa.append(f"## Q: {pair.question}\nA: {overrides.get(number, pair.answer)}\n")
        else:
            if target not in sections:
                raise ValueError(f"Unknown Q&A route: {target}")
            sections[target].setdefault("qa", []).append(text)
    core_files = {}
    manifest.update(schema_version=2, persona_version=config["persona_version"],
                    facts_policy="knowledge_base")
    # Content approval and verification dates stay attached to the original facts.
    manifest["migration"] = {"from_version": snapshot.persona_version,
                             "performed_at": config["performed_at"],
                             "dynamic_visibility": "private_preview"}
    documents = []
    for key, section in sections.items():
        body = (
            f"# {section['title']}\n\n"
            f"作者：{author}\n资料确认日期：{verified}\n"
            f"来源：Persona {snapshot.persona_version}，结构迁移日期 {config['performed_at']}。\n"
            "以下是资料确认日的记录；迁移不表示已经重新确认当前进度。\n\n"
            + yaml.safe_dump(section["data"], allow_unicode=True, sort_keys=False)
            + "\n" + "\n".join(section.get("qa", []))
        )
        documents.append(MigrationDocument(
            f"persona-{key}", section["title"], section.get("project"), verified, author, body
        ))
    for filename, value in (
        ("manifest.yaml", manifest), ("profile.yaml", profile),
        ("projects.yaml", {"schema_version": 2, "last_verified_at": verified, "projects": []}),
        ("voice_rules.yaml", copy.deepcopy(snapshot.voice_rules)),
        ("boundaries.yaml", copy.deepcopy(snapshot.boundaries)),
    ):
        value["schema_version"] = 2
        core_files[filename] = yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
    core_files["qa_pairs.md"] = "# Stable Persona Q&A\n\n" + "\n".join(stable_qa)
    core_files["system_prompt.md"] = config.get("system_prompt", snapshot.system_prompt) + (
        "\n\n# 动态资料\n\n项目、研究进度、毕业计划与职业动态仅使用本次授权知识库证据。"
        "没有证据时说明无法确认，不用旧记忆补全。管理员预览可使用本次授权的私有资料，"
        "访客回答仅使用已发布资料。\n"
    )
    return PersonaMigration(core_files, tuple(documents))
