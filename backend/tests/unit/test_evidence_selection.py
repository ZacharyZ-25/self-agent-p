from dataclasses import replace
from datetime import date

import pytest

from app.knowledge.evidence_selection import select_answer_evidence
from app.knowledge.retriever import Evidence


class TopicEmbeddings:
    dimensions = 2

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0] if "budget" in text.lower() else [0.0, 1.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "budget" in text.lower() else [0.0, 1.0] for text in texts]


def evidence(document_id: str, title: str, body: str, *, fact_type: str = "project") -> Evidence:
    return Evidence(
        source_id=document_id,
        document_id=document_id,
        version_id=f"{document_id}-v1",
        title=title,
        body=body,
        locations=[{"section": "Facts"}],
        token_count=20,
        score=0.03,
        channels=("vector",),
        fact_type=fact_type,
        author="Example Author",
        subject_relation="fictional_owner",
        effective_at=date(2026, 9, 1),
    )


def test_withdrawn_subject_does_not_borrow_an_unrelated_paper() -> None:
    catalog = (("beacon", "Beacon report"), ("paper", "External paper"))
    paper = evidence("paper", "External paper", "EchoGrip combines two methods.",
                     fact_type="external_reference")

    selected = select_answer_evidence(
        "After Beacon was withdrawn, what sensor did it use?", (paper,),
        TopicEmbeddings(), catalog,
    )

    assert selected == ()


def test_unknown_named_code_does_not_borrow_another_public_project() -> None:
    selected = select_answer_evidence(
        "What is SECRET-91 throughput?",
        (evidence("atlas", "ATLAS-42 report", "ATLAS-42 throughput is 42."),),
        TopicEmbeddings(),
        (("atlas", "ATLAS-42 report"),),
    )

    assert selected == ()


def test_owner_budget_evidence_survives_even_when_its_title_is_generic() -> None:
    catalog = (("atlas", "Atlas report"), ("private", "Private planning note"))
    budget = evidence("private", "Private planning note", "The Atlas budget is 7300 EUR.")
    status = evidence("atlas", "Atlas report", "Atlas completed validation.")

    selected = select_answer_evidence(
        "What is the internal Atlas budget?", (status, budget), TopicEmbeddings(), catalog
    )

    assert selected == (budget,)


def test_numeric_conflict_keeps_both_current_reports() -> None:
    catalog = (("beacon", "Beacon report"), ("beacon-conflict", "Beacon second report"))
    first = evidence("beacon", "Beacon report", "Beacon range is 8 m.")
    second = evidence("beacon-conflict", "Beacon second report", "Beacon range is 12 m.")

    selected = select_answer_evidence(
        "Is Beacon range 8 m or 12 m?", (first, second), TopicEmbeddings(), catalog
    )

    assert selected == (first, second)


class ResultEmbeddings:
    dimensions = 2

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Topic-heavy passages have a higher raw cosine than the measured result.
        return [[0.95, 0.312] if "measured" in text.lower() else [1.0, 0.0] for text in texts]


@pytest.mark.parametrize(
    "query",
    [
        "你的本科 Atlas 手势控制系统使用了哪些算法，识别结果如何？",
        "Which algorithms did your Atlas undergraduate robot use, and what were the results?",
        "Welche Algorithmen nutzte dein Atlas Roboter und welche Ergebnisse wurden gemessen?",
    ],
)
@pytest.mark.parametrize(
    ("other_body", "other_section"),
    [
        ("Atlas recognition algorithms control the robot using visual gesture inputs.",
         "Background and motivation"),
        ("Atlas recognition accuracy is planned to reach 99%.", "Results"),
        ("Atlas recognition accuracy reached 99% in the related literature.", "Related work"),
        ("Atlas results report dated 2026-09-01, section 3, paragraph 12.", "Results"),
        ("Atlas results report dated 2026/09/01, section 3, paragraph 12.", "Results"),
        ("Atlas结果记录于2026/09/01，第3段。", "Results"),
        ("Atlas结果记录于2026-09-01，第3段。", "Results"),
    ],
)
def test_result_question_prefers_measured_findings_over_generic_or_planned_passages(
    query: str, other_body: str, other_section: str,
) -> None:
    other = replace(
        evidence("atlas", "Atlas undergraduate robot", other_body),
        source_id="atlas-other", locations=[{"section": other_section}],
    )
    measured = replace(
        evidence("atlas", "Atlas undergraduate robot",
                 "Atlas measured recognition accuracy reached 92.4%, with 47 of 50 trials."),
        source_id="atlas-measured", locations=[{"section": "Evaluation summary"}],
    )

    selected = select_answer_evidence(
        query, (other, measured), ResultEmbeddings(), (("atlas", "Atlas robot"),),
    )

    assert selected[0] == measured


def test_result_reordering_does_not_override_a_non_result_question() -> None:
    background = evidence("atlas", "Atlas robot", "Atlas uses visual gesture inputs.")
    measured = evidence("atlas", "Atlas robot", "Atlas measured accuracy reached 92.4%.")

    selected = select_answer_evidence(
        "What input does Atlas use?", (background, measured),
        ResultEmbeddings(), (("atlas", "Atlas robot"),),
    )

    assert selected[0] == background
