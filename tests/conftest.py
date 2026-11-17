import zlib

import pytest

from apps.corpus.models import EMBEDDING_DIMENSIONS
from apps.retrieval import embedding


def fake_vector(text):
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in text.lower().split():
        vector[zlib.crc32(word.encode()) % EMBEDDING_DIMENSIONS] += 1.0
    return vector


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setattr(
        embedding, "encode", lambda texts, config: [fake_vector(t) for t in texts]
    )
    monkeypatch.setattr(
        embedding, "count_tokens", lambda text, config: len(text.split())
    )
