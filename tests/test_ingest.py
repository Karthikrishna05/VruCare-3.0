import pytest
import yaml
from django.db.models import ProtectedError

from apps.corpus.ingest import ingest, make_chunk_id
from apps.corpus.models import Chunk, Document
from apps.corpus.tasks import ingest_corpus
from apps.evaluation.models import EvalJudgement, EvalQuestion

pytestmark = pytest.mark.django_db
CONFIG = {
    "chunking": {"size": 300, "overlap": 50, "splitter": "recursive"},
    "embedding": {"model": "fake", "device": "cpu"},
}
NEW_CONFIG = {**CONFIG, "chunking": {**CONFIG["chunking"], "overlap": 100}}


def make_pdf(path, pages):
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for text in pages:
        stream = f"BT /F1 10 Tf 20 800 Td ({text}) Tj ET".encode("latin-1")
        objects.append(
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        )
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % len(objects)
        )

    kids = " ".join(f"{number} 0 R" for number in range(5, len(objects) + 1, 2))
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)}>>".encode()
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    table = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        table,
    )
    path.write_bytes(bytes(pdf))


def sentences(template, count=12):
    return " ".join(template.format(i) for i in range(count))


KIDNEY = [
    sentences("The kidney note {} is about the stones and water."),
    sentences("Page two,line {},covers cystine in the urine."),
]
DIET = [sentences("Diet advice {}: drink fluids and eat less salt with meals.")]


def write_sources(folder, files):
    source = {
        "slug": "test",
        "name": "Test source",
        "publisher": "Tester",
        "source_type": "review",
        "documents": [{"file": name, "title": name} for name in files],
    }
    (folder / "SOURCES.yaml").write_text(yaml.safe_dump({"sources": [source]}))


@pytest.fixture
def corpus(tmp_path):
    make_pdf(tmp_path / "kidney.pdf", KIDNEY)
    make_pdf(tmp_path / "diet.pdf", DIET)
    write_sources(tmp_path, ["kidney.pdf", "diet.pdf"])
    return tmp_path


def chunk_ids():
    return set(Chunk.objects.values_list("chunk_id", flat=True))


def test_ingest_saves_documents_and_page_numbers(corpus, fake_model):
    report = ingest(corpus, CONFIG)
    assert report["added"] == ["diet.pdf", "kidney.pdf"]
    assert report["warnings"] == []
    kidney = Document.objects.get(filename="kidney.pdf")
    chunks = list(kidney.chunk_set.order_by("ordinal"))
    assert kidney.page_count == 2
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    assert all(len(chunk.text) <= 300 for chunk in chunks)


def test_a_chunk_can_cross_a_page_boundary(tmp_path, fake_model):
    make_pdf(tmp_path / "leaflet.pdf", ["The first page.", "The second page."])
    write_sources(tmp_path, ["leaflet.pdf"])
    ingest(tmp_path, CONFIG)
    chunk = Chunk.objects.get()
    assert (chunk.page_start, chunk.page_end) == (1, 2)


def test_running_twice_changes_nothing(corpus, fake_model):
    ingest(corpus, CONFIG)
    before = chunk_ids()
    report = ingest(corpus, CONFIG)
    assert report["added"] == []
    assert len(report["skipped"]) == 2
    assert chunk_ids() == before


def test_new_chunking_settings_give_new_ids(corpus, fake_model):
    ingest(corpus, CONFIG)
    before = chunk_ids()
    ingest(corpus, NEW_CONFIG)
    assert before.isdisjoint(chunk_ids())
    assert Document.objects.count() == 2


def test_chunk_id_depends_on_document_settings_and_position():
    chunk_id = make_chunk_id("d" * 64, "c" * 64, 0)
    assert len(chunk_id) == 32
    assert chunk_id == make_chunk_id("d" * 64, "c" * 64, 0)
    assert chunk_id != make_chunk_id("d" * 64, "c" * 64, 1)
    assert chunk_id != make_chunk_id("d" * 64, "e" * 64, 0)


def test_near_copy_is_reported(corpus, fake_model):
    make_pdf(corpus / "kidney-copy.pdf", [KIDNEY[0], KIDNEY[1] + "One more line."])
    write_sources(corpus, ["kidney.pdf", "diet.pdf", "kidney-copy.pdf"])
    report = ingest(corpus, CONFIG)
    assert any(
        "near-copy" in w and "kidney.pdf" in w and "kidney-copy.pdf" in w
        for w in report["warnings"]
    )


def test_unreadable_unlisted_and_missing_files_are_reported(corpus, fake_model):
    make_pdf(corpus / "scrambled.pdf", ["7KH 3XUSRVH RI WKLV JXLGHOLQH" * 20])
    make_pdf(corpus / "unlisted.pdf", DIET)
    write_sources(corpus, ["kidney.pdf", "diet.pdf", "scrambled.pdf", "missing.pdf"])
    report = ingest(corpus, CONFIG)
    assert "scrambled.pdf: text is unreadable, skipped" in report["warnings"]
    assert "unlisted.pdf: not in SOURCES.yaml, skipped" in report["warnings"]
    assert "missing.pdf: listed in SOURCES.yaml but not found" in report["warnings"]
    assert Document.objects.count() == 2


def test_a_removed_pdf_leaves_the_library(corpus, fake_model):
    ingest(corpus, CONFIG)
    (corpus / "diet.pdf").unlink()
    write_sources(corpus, ["kidney.pdf"])
    report = ingest(corpus, CONFIG)
    assert report["removed"] == ["diet.pdf"]
    assert list(Document.objects.values_list("filename", flat=True)) == ["kidney.pdf"]


def test_labelled_chunks_block_a_rebuild(corpus, fake_model):
    ingest(corpus, CONFIG)
    question = EvalQuestion.objects.create(
        key="q01",
        text="?",
        category="definitions",
        split="dev",
        expected_behaviour="answer",
    )
    labelled = Chunk.objects.filter(document__filename="kidney.pdf").first()
    EvalJudgement.objects.create(question=question, chunk=labelled, pool_source="dense")
    with pytest.raises(ProtectedError):
        ingest(corpus, NEW_CONFIG)
    assert Chunk.objects.filter(pk=labelled.pk).exists()


def test_long_chunks_are_reported(corpus, fake_model, monkeypatch):
    monkeypatch.setattr("apps.retrieval.embedding.count_tokens", lambda text, c: 300)
    report = ingest(corpus, CONFIG)
    assert any("longer than 256 word pieces" in w for w in report["warnings"])


def test_celery_job_runs_the_same_function(corpus, fake_model):
    report = ingest_corpus.apply(args=[str(corpus), CONFIG]).get()
    assert report["added"] == ["diet.pdf", "kidney.pdf"]
