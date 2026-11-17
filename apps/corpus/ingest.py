import hashlib
import json
import logging
import re
from bisect import bisect_right
from pathlib import Path

import yaml
from django.db import transaction
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from apps.corpus.models import Chunk, Document, Source
from apps.retrieval import embedding

logging.getLogger("pypdf").setLevel(logging.ERROR)
MAX_WORD_PIECES = 256
NEAR_COPY_SIMILARITY = 0.2
MIN_COMMON_WORD_SHARE = 0.1
COMMON_WORDS = {
    "the",
    "and",
    "of",
    "to",
    "a",
    "in",
    "is",
    "with",
    "are",
    "for",
    "on",
    "that",
    "as",
    "by",
    "this",
    "it",
    "from",
    "at",
    "be",
    "an",
    "or",
    "which",
    "but",
    "not",
    "have",
    "has",
    "was",
    "were",
}


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def make_chunk_id(document_hash, config_hash, ordinal):
    return sha256(f"{document_hash}{config_hash}{ordinal}")[:32]


def read_pdf(path):
    return [page.extract_text() or "" for page in PdfReader(path).pages]


def is_readable(text):
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return False
    common = sum(word in COMMON_WORDS for word in words)
    return common / len(words) >= MIN_COMMON_WORD_SHARE


def shingles(text, size=5):
    words = re.findall(r"\w+", text.lower())
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def similarity(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def split_pages(pages, chunking):
    if chunking["splitter"] != "recursive":
        raise ValueError(f"Unknown splitter: {chunking['splitter']}")
    starts, position = [], 0
    for page in pages:
        starts.append(position)
        position += len(page) + 2
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunking["size"],
        chunk_overlap=chunking["overlap"],
        add_start_index=True,
    )
    pieces = []
    for piece in splitter.create_documents(["\n\n".join(pages)]):
        first = piece.metadata["start_index"]
        last = first + len(piece.page_content) - 1
        pieces.append(
            (
                piece.page_content,
                bisect_right(starts, first),
                bisect_right(starts, last),
            )
        )
    return pieces


def ingest(corpus_dir, config):
    corpus_dir = Path(corpus_dir)
    catalogue = yaml.safe_load((corpus_dir / "SOURCES.yaml").read_text("utf-8"))
    listed = {
        document["file"]: (source, document)
        for source in catalogue["sources"]
        for document in source["documents"]
    }
    settings = {"chunking": config["chunking"], "embedding": config["embedding"]}
    config_hash = sha256(json.dumps(config["chunking"], sort_keys=True))
    report = {"added": [], "skipped": [], "removed": [], "warnings": [], "chunks": 0}
    seen = {}
    kept = set()
    for path in sorted(corpus_dir.glob("*.pdf")):
        if path.name not in listed:
            report["warnings"].append(f"{path.name}: not in SOURCES.yaml, skipped")
            continue
        pages = read_pdf(path)
        text = "\n\n".join(pages)
        if not is_readable(text):
            report["warnings"].append(f"{path.name}: text is unreadable, skipped")
            continue
        words = shingles(text)
        for other, other_words in seen.items():
            score = similarity(words, other_words)
            if score >= NEAR_COPY_SIMILARITY:
                report["warnings"].append(
                    f"{path.name}: near-copy of {other} (similarity{score:.2f})"
                )
        seen[path.name] = words

        document_hash = sha256(text)
        kept.add(document_hash)
        existing = Document.objects.filter(content_hash=document_hash).first()
        if existing and existing.ingest_config == settings:
            report["skipped"].append(path.name)
            continue
        pieces = split_pages(pages, config["chunking"])
        texts = [piece_text for piece_text, _, _ in pieces]
        vectors = embedding.encode(texts, config["embedding"])
        tokens = [embedding.count_tokens(t, config["embedding"]) for t in texts]
        too_long = sum(count > MAX_WORD_PIECES for count in tokens)
        if too_long:
            report["warnings"].append(
                f"{path.name}:{too_long} chunks are longer than {MAX_WORD_PIECES} word pieces.it only reads the starting"
            )
        source_info, document_info = listed[path.name]
        with transaction.atomic():
            if existing:
                existing.delete()
            source, _ = Source.objects.update_or_create(
                slug=source_info["slug"],
                defaults={
                    "name": source_info["name"],
                    "publisher": source_info["publisher"],
                    "source_type": source_info["source_type"],
                    "url": source_info.get("url", ""),
                    "license_note": source_info.get("license_note", ""),
                },
            )
            document = Document.objects.create(
                source=source,
                title=document_info["title"],
                filename=path.name,
                version_label=str(document_info.get("version_label", "")),
                publication_date=document_info.get("publication_date"),
                page_count=len(pages),
                char_count=len(text),
                content_hash=document_hash,
                ingest_config=settings,
            )
            Chunk.objects.bulk_create(
                [
                    Chunk(
                        chunk_id=make_chunk_id(document_hash, config_hash, ordinal),
                        document=document,
                        ordinal=ordinal,
                        text=piece_text,
                        token_count=tokens[ordinal],
                        page_start=page_start,
                        page_end=page_end,
                        embedding=vectors[ordinal],
                        content_hash=sha256(piece_text),
                    )
                    for ordinal, (piece_text, page_start, page_end) in enumerate(pieces)
                ]
            )
        report["added"].append(path.name)
        report["chunks"] += len(pieces)

    for name in sorted(set(listed) - {path.name for path in corpus_dir.glob("*.pdf")}):
        report["warnings"].append(f"{name}: listed in SOURCES.yaml but not found")

    gone = Document.objects.exclude(content_hash__in=kept)
    report["removed"] = sorted(gone.values_list("filename", flat=True))
    gone.delete()
    return report
