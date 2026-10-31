import pytest
from django.contrib import admin
from django.db import DataError, IntegrityError
from django.db.models import ProtectedError
from pgvector.django import CosineDistance

from apps.agents.models import AgentTrace
from apps.chat.models import Citation, Conversation, ExternalArticle, Message
from apps.corpus.models import EMBEDDING_DIMENSIONS, Chunk, Document, Source
from apps.evaluation.models import EvalJudgement, EvalQuestion

pytestmark = pytest.mark.django_db


def unit_vector(position):
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[position] = 1.0
    return vector


@pytest.fixture
def document():
    source = Source.objects.create(
        slug="test-source",
        name="Test source",
        publisher="Test publisher",
        source_type="guideline",
    )
    return Document.objects.create(
        source=source,
        title="Test document",
        filename="test,pdf",
        page_count=1,
        char_count=100,
        content_hash="d" * 64,
    )


def make_chunk(document, ordinal, text="Kidney Stones are hard deposits."):
    return Chunk.objects.create(
        chunk_id=f"chunk-{ordinal}",
        document=document,
        ordinal=ordinal,
        text=text,
        token_count=6,
        embedding=unit_vector(ordinal),
        content_hash=f"{ordinal:064d}",
    )


@pytest.fixture
def message():
    conversation = Conversation.objects.create(session_key="s" * 32)
    return Message.objects.create(
        conversation=conversation, role="assistant", content="An Answer."
    )


def test_chunk_stores_a_384_number_embedding(document):
    chunk = make_chunk(document, 0)
    chunk.refresh_from_db()
    assert len(chunk.embedding) == EMBEDDING_DIMENSIONS
    assert chunk.embedding[0] == 1.0


def test_embedding_of_the_wrong_size_is_rejected(document):
    with pytest.raises(DataError):
        Chunk.objects.create(
            chunk_id="too-short",
            document=document,
            ordinal=0,
            text="x",
            token_count=1,
            embedding=[1.0, 0.0, 0.0],
            content_hash="0" * 64,
        )


def test_keyword_index_fills_itsellf_in(document):
    chunk = make_chunk(document, 0, text="Kidney stones are hard deposits.")
    chunk.refresh_from_db()
    assert "stone" in chunk.tsv
    assert "kidney" in chunk.tsv
    assert "are" not in chunk.tsv


def test_nearest_chunk_is_found_by_cosine_distance(document):
    make_chunk(document, 0)
    near = make_chunk(document, 1)
    make_chunk(document, 2)
    nearest = Chunk.objects.order_by(
        CosineDistance("embedding", unit_vector(1))
    ).first()
    assert nearest == near


def test_chunk_id_must_be_unique(document):
    make_chunk(document, 0)
    with pytest.raises(IntegrityError):
        Chunk.objects.create(
            chunk_id="chunk-0",
            document=document,
            ordinal=1,
            text="x",
            token_count=1,
            embedding=unit_vector(1),
            content_hash="1" * 64,
        )


def test_citation_to_a_chunk_is_allowed(document, message):
    Citation.objects.create(
        message=message, chunk=make_chunk(document, 0), rank=1, relevance_score=0.03
    )
    assert Citation.objects.count() == 1


def test_citation_with_no_target_is_rejected(message):
    with pytest.raises(IntegrityError):
        Citation.objects.create(message=message, rank=1, relevance_score=0.03)


def test_citation_with_two_targets_is_rejected(document, message):
    article = ExternalArticle.objects.create(pmid="123", title="A review")
    with pytest.raises(IntegrityError):
        Citation.objects.create(
            message=message,
            chunk=make_chunk(document, 0),
            external_article=article,
            rank=1,
            relevance_score=0.03,
        )


def test_trace_step_numbers_cannot_repeat_within_a_message(message):
    AgentTrace.objects.create(
        message=message, step_index=0, node="triage", decision="in_scope", duration_ms=9
    )
    with pytest.raises(IntegrityError):
        AgentTrace.objects.create(
            message=message,
            step_index=0,
            node="retrieve",
            decision="5 chunks",
            duration_ms=4,
        )


@pytest.fixture
def question():
    return EvalQuestion.objects.create(
        key="q01",
        text="What causes kidney stones?",
        category="definitions",
        split="dev",
        expected_behaviour="answer",
    )


def test_judgement_starts_unjudged_and_cannot_be_duplicated(document, question):
    chunk = make_chunk(document, 0)
    judgement = EvalJudgement.objects.create(
        question=question, chunk=chunk, pool_source="dense"
    )
    assert judgement.relevant is None
    with pytest.raises(IntegrityError):
        EvalJudgement.objects.create(question=question, chunk=chunk, pool_source="rrf")


def test_a_judged_chunk_cannot_be_deleted(document, question):
    chunk = make_chunk(document, 0)
    EvalJudgement.objects.create(question=question, chunk=chunk, pool_source="dense")
    with pytest.raises(ProtectedError):
        chunk.delete()


def test_admin_lists_all_eleven_tables(admin_client):
    ours = [
        model
        for model in admin.site._registry
        if model._meta.app_label in ("corpus", "chat", "agents", "evaluation")
    ]
    assert len(ours) == 11
    for model in ours:
        url = f"/admin/{model._meta.app_label}/{model._meta.model_name}/"
        assert admin_client.get(url).status_code == 200
