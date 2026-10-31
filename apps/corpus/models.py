from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from pgvector.django import VectorField

from apps.base import UUIDModel

EMBEDDING_DIMENSIONS = 384


class Source(UUIDModel):
    SOURCE_TYPES = [
        ("guideline", "Guideline"),
        ("review", "Review"),
        ("patient_info", "Patient information"),
        ("external", "External"),
    ]
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=255)
    publisher = models.CharField(max_length=255)
    source_type = models.CharField(max_length=32, choices=SOURCE_TYPES)
    url = models.URLField(blank=True)
    license_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Document(UUIDModel):
    source = models.ForeignKey(Source, on_delete=models.PROTECT)
    title = models.CharField(max_length=512)
    filename = models.CharField(max_length=512)
    version_label = models.CharField(max_length=64, blank=True)
    publication_date = models.DateField(blank=True, null=True)
    page_count = models.PositiveIntegerField()
    char_count = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64, unique=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    ingest_config = models.JSONField(default=dict)

    def __str__(self):
        return self.title


class Chunk(UUIDModel):
    chunk_id = models.CharField(max_length=64, unique=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    ordinal = models.PositiveIntegerField()
    text = models.TextField()
    token_count = models.PositiveIntegerField()
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    section_path = models.CharField(max_length=512, blank=True)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS)
    tsv = models.GeneratedField(
        expression=SearchVector("text", config="english"),
        output_field=SearchVectorField(),
        db_persist=True,
    )
    content_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        indexes = [GinIndex(fields=["tsv"], name="chunk_tsv_idx")]

    def __str__(self):
        return self.chunk_id
