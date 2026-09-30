from datetime import date

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
