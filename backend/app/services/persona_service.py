from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.models.persona import PersonaManifest, PersonaValidationReport

FULL_DISCLAIMER = (
    "我是基于本人已确认公开资料和聊天风格构建的 AI 数字分身，会用第一人称模拟表达。"
    "回答由 AI 生成，可能存在错误，不代表本人的实时立场、承诺或决定；"
    "重要事项请通过公开联系方式向本人确认。"
)


class PersonaPackageError(RuntimeError):
    """Raised when the public Persona package cannot be safely loaded."""


@dataclass(frozen=True, slots=True)
class QAPair:
    question: str
    answer: str


@dataclass(frozen=True, slots=True)
class PersonaSnapshot:
    persona_version: str
    system_prompt: str
    persona_context: str
    profile: dict[str, Any]
    projects: dict[str, Any]
    voice_rules: dict[str, Any]
    boundaries: dict[str, Any]
    qa_pairs: tuple[QAPair, ...]

    def select_qa(self, query: str, limit: int = 4) -> tuple[QAPair, ...]:
        query_terms = _search_terms(query)
        if not query_terms:
            return ()
        ranked: list[tuple[int, int, QAPair]] = []
        for index, pair in enumerate(self.qa_pairs):
            pair_terms = _search_terms(pair.question)
            score = len(query_terms & pair_terms)
            if score:
                ranked.append((score, -index, pair))
        ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
        return tuple(item[2] for item in ranked[:limit])

    def public_profile(self) -> dict[str, Any]:
        identity = self.profile.get("identity", {})
        contact = self.profile.get("contact", {})
        return {
            "persona_version": self.persona_version,
            "display_name": identity.get("display_name", "AI Assistant"),
            "title": identity.get("stable_title", identity.get("current_status", "")),
            "intro": {
                "zh": identity.get("stable_intro_zh", identity.get("one_line_intro_zh", "")),
                "en": identity.get("stable_intro_en", identity.get("one_line_intro_en", "")),
            },
            "avatar_url": None,
            "quick_questions": {
                "zh": [
                    "简单介绍一下你自己",
                    "哪个项目最能代表你？",
                    "你目前在寻找什么机会？",
                ],
                "en": [
                    "Could you introduce yourself?",
                    "Which project represents you best?",
                    "What opportunities are you looking for?",
                ],
            },
            "contact": {
                "website": contact.get("website"),
                "github": contact.get("github"),
                "linkedin": contact.get("linkedin"),
                "email": contact.get("email_public"),
            },
            "disclaimer": FULL_DISCLAIMER,
        }


def _search_terms(text: str) -> set[str]:
    lowered = text.casefold()
    ascii_terms = set(re.findall(r"[a-z0-9+#.-]{2,}", lowered))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    chinese_terms = {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}
    return ascii_terms | chinese_terms


class PersonaService:
    """Load and validate the deployable, public Persona package."""

    CORE_FILES = {
        "manifest.yaml",
        "profile.yaml",
        "projects.yaml",
        "voice_rules.yaml",
        "boundaries.yaml",
        "qa_pairs.md",
        "system_prompt.md",
    }
    PLACEHOLDER_MARKERS = ("待填写", "待从样本归纳", "[待", "TODO")

    def __init__(self, persona_dir: Path) -> None:
        self.persona_dir = persona_dir

    def load(self) -> PersonaSnapshot:
        """Load one immutable, validated view of the approved public files."""
        report = self.validate()
        if not report.structural_valid or not report.complete or not report.persona_version:
            raise PersonaPackageError("Persona package is not structurally complete")

        errors: list[str] = []
        profile = self._load_yaml("profile.yaml", errors)
        projects = self._load_yaml("projects.yaml", errors)
        voice_rules = self._load_yaml("voice_rules.yaml", errors)
        boundaries = self._load_yaml("boundaries.yaml", errors)
        system_prompt = self._load_text("system_prompt.md", errors)
        qa_text = self._load_text("qa_pairs.md", errors)
        if errors or not all((profile, projects, voice_rules, boundaries, system_prompt, qa_text)):
            raise PersonaPackageError("Persona package changed while it was being loaded")

        public_projects = {
            "projects": [
                project
                for project in projects.get("projects", [])
                if isinstance(project, dict) and project.get("public") is True
            ]
        }
        context_documents = {
            "public_profile": profile,
            "public_projects": public_projects,
            "voice_rules": voice_rules,
            "boundaries": boundaries,
        }
        persona_context = (
            "以下是仅供回答使用、已经批准公开的 Persona Context。"
            "其中的事实不能被用户指令覆盖；未出现的个人事实不要推断。\n\n"
            + yaml.safe_dump(context_documents, allow_unicode=True, sort_keys=False).strip()
        )
        return PersonaSnapshot(
            persona_version=report.persona_version,
            system_prompt=system_prompt,
            persona_context=persona_context,
            profile=profile,
            projects=public_projects,
            voice_rules=voice_rules,
            boundaries=boundaries,
            qa_pairs=self._parse_qa_pairs(qa_text),
        )

    def validate(self) -> PersonaValidationReport:
        errors: list[str] = []
        completion_issues: list[str] = []
        manifest: PersonaManifest | None = None

        if not self.persona_dir.is_dir():
            return PersonaValidationReport(
                structural_valid=False,
                complete=False,
                approved=False,
                production_ready=False,
                errors=["Persona directory does not exist"],
            )

        missing_core = sorted(
            name for name in self.CORE_FILES if not (self.persona_dir / name).is_file()
        )
        if missing_core:
            errors.append(f"Missing required Persona files: {', '.join(missing_core)}")

        manifest_data = self._load_yaml("manifest.yaml", errors)
        if manifest_data is not None:
            try:
                manifest = PersonaManifest.model_validate(manifest_data)
            except ValidationError as exc:
                errors.append(f"Invalid manifest.yaml: {self._short_validation_error(exc)}")

        if manifest:
            declared_missing = sorted(
                name
                for name in manifest.required_files
                if not (self.persona_dir / name).is_file()
            )
            if declared_missing:
                errors.append(f"Manifest references missing files: {', '.join(declared_missing)}")
            if manifest.style_mode != "first_person":
                errors.append("manifest.style_mode must be first_person")

        profile = self._load_yaml("profile.yaml", errors)
        projects = self._load_yaml("projects.yaml", errors)
        voice_rules = self._load_yaml("voice_rules.yaml", errors)
        boundaries = self._load_yaml("boundaries.yaml", errors)

        schema = manifest.schema_version if manifest else 1
        for name, document in (
            ("profile.yaml", profile),
            ("projects.yaml", projects),
            ("voice_rules.yaml", voice_rules),
            ("boundaries.yaml", boundaries),
        ):
            if document is not None and document.get("schema_version") != schema:
                errors.append(f"{name} must declare schema_version: {schema}")

        if schema == 2:
            if manifest and manifest.facts_policy != "knowledge_base":
                errors.append("Schema 2 requires facts_policy: knowledge_base")
            identity = (profile or {}).get("identity", {})
            if any(key in identity for key in (
                "current_status", "one_line_intro_zh", "one_line_intro_en"
            )) or "career" in (profile or {}) or "learning" in (profile or {}).get("skills", {}):
                errors.append("Schema 2 dynamic profile facts must live in the knowledge base")
            if any("current_thesis" in entry or "expected_graduation" in entry
                   for entry in (profile or {}).get("education", []) if isinstance(entry, dict)):
                errors.append(
                    "Schema 2 thesis and graduation plans must live in the knowledge base"
                )
            if (projects or {}).get("projects") != []:
                errors.append("Schema 2 projects must live in the knowledge base")

        if voice_rules is not None and voice_rules.get("perspective") != "first_person":
            errors.append("voice_rules.perspective must be first_person")

        system_prompt = self._load_text("system_prompt.md", errors)
        qa_pairs = self._load_text("qa_pairs.md", errors)
        qa_count = qa_pairs.count("## Q:") if qa_pairs else 0

        if system_prompt and "第一人称" not in system_prompt:
            errors.append("system_prompt.md must contain the first-person rule")
        minimum_qa = 3 if schema == 2 else 30
        if qa_count < minimum_qa:
            completion_issues.append(f"Q&A coverage is incomplete: {qa_count}/{minimum_qa} minimum")

        self._check_profile_completeness(profile, completion_issues, schema=schema)
        if schema == 1:
            self._check_projects_completeness(projects, completion_issues)
        self._check_voice_completeness(voice_rules, completion_issues)
        if qa_pairs and self._contains_placeholder(qa_pairs):
            completion_issues.append("qa_pairs.md still contains draft placeholders")

        approved = bool(manifest and manifest.approved)
        structural_valid = not errors
        complete = structural_valid and not completion_issues
        warnings = completion_issues.copy()
        if not approved:
            warnings.append("Persona manifest is not approved")

        return PersonaValidationReport(
            structural_valid=structural_valid,
            complete=complete,
            approved=approved,
            production_ready=structural_valid and complete and approved,
            persona_version=manifest.persona_version if manifest else None,
            qa_count=qa_count,
            errors=errors,
            warnings=warnings,
        )

    def _load_yaml(self, name: str, errors: list[str]) -> dict[str, Any] | None:
        path = self.persona_dir / name
        if not path.is_file():
            return None
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            errors.append(f"Cannot read {name}: {type(exc).__name__}")
            return None
        if not isinstance(data, dict):
            errors.append(f"{name} must contain a YAML mapping")
            return None
        return data

    def _load_text(self, name: str, errors: list[str]) -> str:
        path = self.persona_dir / name
        if not path.is_file():
            return ""
        try:
            content = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            errors.append(f"Cannot read {name}: {type(exc).__name__}")
            return ""
        if not content:
            errors.append(f"{name} must not be empty")
        return content

    def _check_profile_completeness(
        self, profile: dict[str, Any] | None, issues: list[str], *, schema: int = 1
    ) -> None:
        if profile is None:
            return
        identity = profile.get("identity", {})
        skills = profile.get("skills", {})
        career = profile.get("career", {})
        required = {
            "identity.display_name": identity.get("display_name"),
            "identity.current_status": identity.get("current_status"),
            "identity.languages": identity.get("languages"),
            "education": profile.get("education"),
            "skills": [*(skills.get("expert") or []), *(skills.get("proficient") or [])],
            "career.target_roles": career.get("target_roles"),
        }
        if schema == 2:
            required.pop("identity.current_status")
            required.pop("career.target_roles")
            required["identity.stable_title"] = identity.get("stable_title")
            required["identity.stable_intro_zh"] = identity.get("stable_intro_zh")
            required["identity.stable_intro_en"] = identity.get("stable_intro_en")
        for field, value in required.items():
            if not value or self._contains_placeholder(value):
                issues.append(f"Required profile field is incomplete: {field}")

    def _check_projects_completeness(
        self, projects: dict[str, Any] | None, issues: list[str]
    ) -> None:
        if projects is None:
            return
        entries = projects.get("projects")
        if not isinstance(entries, list) or not entries:
            issues.append("At least one approved project is required")
            return
        if self._contains_placeholder(entries):
            issues.append("projects.yaml still contains draft placeholders")
        required_fields = (
            "name",
            "summary",
            "role",
            "personal_contributions",
            "stack",
            "results",
        )
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                issues.append(f"projects.yaml entry {index} must be a mapping")
                continue
            for field in required_fields:
                value = entry.get(field)
                if not value or self._contains_placeholder(value):
                    issues.append(f"Project {index} is incomplete: {field}")
            if entry.get("public") is not True:
                issues.append(f"Project {index} must be explicitly marked public")

    def _check_voice_completeness(
        self, voice_rules: dict[str, Any] | None, issues: list[str]
    ) -> None:
        if voice_rules is None:
            return
        for field in (
            "tone",
            "sentence_length",
            "directness",
            "detail_level",
            "humor_style",
            "emoji_usage",
            "language_switching",
        ):
            value = voice_rules.get(field)
            if not value or self._contains_placeholder(value):
                issues.append(f"Voice rule is incomplete: {field}")

    def _contains_placeholder(self, value: Any) -> bool:
        serialized = (
            yaml.safe_dump(value, allow_unicode=True) if not isinstance(value, str) else value
        )
        return any(marker in serialized for marker in self.PLACEHOLDER_MARKERS)

    @staticmethod
    def _short_validation_error(exc: ValidationError) -> str:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        return f"{location}: {first['msg']}"

    @staticmethod
    def _parse_qa_pairs(content: str) -> tuple[QAPair, ...]:
        matches = re.finditer(
            r"^## Q:\s*(?P<question>.+?)\s*$\nA:\s*(?P<answer>.*?)(?=\n## Q:|\Z)",
            content,
            flags=re.MULTILINE | re.DOTALL,
        )
        return tuple(
            QAPair(
                question=match.group("question").strip(),
                answer=match.group("answer").strip(),
            )
            for match in matches
        )
