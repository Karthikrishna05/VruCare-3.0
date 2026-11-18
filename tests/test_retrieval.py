import copy
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connections

from apps.corpus.ingest import sha256
from apps.corpus.models import Chunk, Document, Source
from apps.retrieval.search import dense_search, retrieve, rrf, sparse_search
from tests.conftest import fake_vector

pytestmark = pytest.mark.django_db
CONFIG = {
    "embedding": {"model": "fake", "device": "cpu"},
    "retrieval": {
        "dense": {"enabled": True, "top_k": 25},
        "sparse": {"enabled": True, "top_k": 25},
        "fusion": {"method": "rrf", "rrf_k": 60, "final_k": 5},
    },
}


def changed(section, key, value):
    config = copy.deepcopy(CONFIG)
    config["retrieval"][section][key] = value
    return config


def add_document(title, texts):
    source, _ = Source.objects.get_or_create(
        slug="test",
        defaults={"name": "Test", "publisher": "T", "source_type": "review"},
    )
    document = Document.objects.create(
        source=source,
        title=title,
        filename=f"{title}.pdf",
        page_count=1,
        char_count=1,
        content_hash=sha256(title),
    )
    for ordinal, text in enumerate(texts):
        Chunk.objects.create(
            chunk_id=f"{title}-{ordinal}",
            document=document,
            ordinal=ordinal,
            text=text,
            token_count=len(text.split()),
            embedding=fake_vector(text),
            content_hash=sha256(text),
        )


@pytest.fixture
def library(fake_model):
    add_document("stones", ["calcium oxalate stones form in the kidney", "kidney pain"])
    add_document("diet", ["spinach and nuts contain oxalate", "the weather was mild"])


def test_rrf_adds_one_over_k_plus_rank():
    scores = rrf([["a", "b"], ["b", "c"]], rrf_k=60)
    assert scores == pytest.approx({"a": 1 / 61, "b": 1 / 62 + 1 / 61, "c": 1 / 62})
    assert max(scores, key=scores.get) == "b"


def test_keyword_search_matches_any_of_the_words(library):
    found = {chunk_id for chunk_id, _ in sparse_search("kidney oxalate", top_k=10)}
    assert found == {"stones-0", "stones-1", "diet-0"}


def test_a_question_of_only_common_words_finds_nothing(library):
    assert sparse_search("What is the", top_k=10) == []


def test_meaning_search_reports_cosine_similarity(library):
    vector = fake_vector("calcium oxalate stones form in the kidney")
    chunk_id, cosine = dense_search(vector, top_k=3)[0]
    assert chunk_id == "stones-0"
    assert cosine == pytest.approx(1.0)


def test_identical_text_in_two_documents_stays_two_results(library):
    add_document("copy", ["calcium oxalate stones form in the kidney"])
    items = retrieve("calcium oxalate stones form in the kidney", CONFIG)
    top_two = {item.chunk_id for item in items[:2]}
    assert top_two == {"stones-0", "copy-0"}
    assert items[0].source_key != items[1].source_key


def test_each_search_can_be_switched_off(library):
    meaning_only = retrieve("kidney oxalate", changed("sparse", "enabled", False))
    keyword_only = retrieve("kidney oxalate", changed("dense", "enabled", False))
    assert all(item.sparse_rank is None for item in meaning_only)
    assert all(item.dense_cosine is None for item in keyword_only)
    assert len(retrieve("kidney oxalate", changed("fusion", "final_k", 2))) == 2


@pytest.mark.django_db(transaction=True)
def test_many_searches_at_once_give_the_same_answers(library):
    def search(final_k):
        try:
            config = changed("fusion", "final_k", final_k)
            return [item.chunk_id for item in retrieve("kidney oxalate", config)]
        finally:
            connections.close_all()

    expected = {k: search(k) for k in (1, 2, 3, 4)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(search, [1, 2, 3, 4] * 8))
        assert results == [expected[k] for k in [1, 2, 3, 4] * 8]
