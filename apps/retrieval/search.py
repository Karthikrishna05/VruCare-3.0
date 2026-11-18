from dataclasses import dataclass
from datetime import date

from django.db import connection
from pgvector.django import CosineDistance

from apps.corpus.models import Chunk
from apps.retrieval import embedding


@dataclass(frozen=True)
class EvidenceItem:
    chunk_id: str
    source_key: str
    text: str
    title: str
    source_name: str
    publication_date: date | None
    page_start: int | None
    page_end: int | None
    dense_rank: int | None
    dense_cosine: float | None
    sparse_rank: int | None
    fused_score: float | None
    origin: str = "local"


def dense_search(vector, top_k):
    rows = (
        Chunk.objects.annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance", "chunk_id")
        .values_list("chunk_id", "distance")[:top_k]
    )
    return [(chunk_id, 1 - distance) for chunk_id, distance in rows]


SPARSE_SQL = """
            WITH q AS (
            SELECT replace(plainto_tsquery('english',%s)::text, ' & ',
            ' | ')::tsquery
            AS query)
            SELECT chunk_id,ts_rank_cd(tsv,q.query) AS rank
            FROM corpus_chunk,q
            WHERE tsv @@ q.query
            ORDER BY rank DESC,chunk_id
            LIMIT %s
        """


def sparse_search(query, top_k):
    with connection.cursor() as cursor:
        cursor.execute(SPARSE_SQL, [query, top_k])
        return cursor.fetchall()


def rrf(rankings, rrf_k):
    scores = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (rrf_k + rank)
    return scores


def retrieve(query, config):
    settings = config["retrieval"]
    if settings["fusion"]["method"] != "rrf":
        raise ValueError(f"unknown fusion method: {settings['fusion']['method']}")
    dense, sparse = [], []
    if settings["dense"]["enabled"]:
        vector = embedding.encode([query], config["embedding"])[0]
        dense = dense_search(vector, settings["dense"]["top_k"])
    if settings["sparse"]["enabled"]:
        sparse = sparse_search(query, settings["sparse"]["top_k"])
    scores = rrf(
        [[chunk_id for chunk_id, _ in dense], [chunk_id for chunk_id, _ in sparse]],
        settings["fusion"]["rrf_k"],
    )
    best = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    best = best[: settings["fusion"]["final_k"]]

    dense_found = {
        chunk_id: (rank, cosine) for rank, (chunk_id, cosine) in enumerate(dense, 1)
    }
    sparse_found = {chunk_id: rank for rank, (chunk_id, _) in enumerate(sparse, 1)}
    chunks = Chunk.objects.select_related("document__source").in_bulk(
        best, field_name="chunk_id"
    )
    items = []
    for chunk_id in best:
        chunk = chunks[chunk_id]
        dense_rank, dense_cosine = dense_found.get(chunk_id, (None, None))
        items.append(
            EvidenceItem(
                chunk_id=chunk_id,
                source_key=str(chunk.document_id),
                text=chunk.text,
                title=chunk.document.title,
                source_name=chunk.document.source.name,
                publication_date=chunk.document.publication_date,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                dense_rank=dense_rank,
                dense_cosine=dense_cosine,
                sparse_rank=sparse_found.get(chunk_id),
                fused_score=scores[chunk_id],
            )
        )
    return items
