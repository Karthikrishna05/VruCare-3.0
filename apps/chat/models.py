from django.db import models
from django.db.models import Q

from apps.base import UUIDModel
from apps.corpus.models import Chunk


class Conversation(UUIDModel):
    session_key = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title or str(self.id)


class Message(UUIDModel):
    ROLES = [("user", "User"), ("assistant", "Assistant"), ("system", "System")]
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=ROLES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    route = models.CharField(max_length=32, blank=True)
    refused = models.BooleanField(default=False)
    refusal_reason = models.CharField(max_length=64, blank=True)
    model_used = models.CharField(max_length=128, blank=True)
    prompt_tokens = models.PositiveIntegerField(null=True, blank=True)
    completion_tokens = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    retrieval_ms = models.PositiveIntegerField(null=True, blank=True)
    generation_ms = models.PositiveIntegerField(null=True, blank=True)
    escalated = models.BooleanField(default=False)
    cache_hit = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class ExternalArticle(UUIDModel):
    pmid = models.CharField(max_length=32, unique=True)
    title = models.TextField()
    abstract = models.TextField(blank=True)
    authors = models.TextField(blank=True)
    journal = models.CharField(max_length=255, blank=True)
    publication_date = models.DateField(blank=True, null=True)
    pmc_id = models.CharField(max_length=32, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PMID {self.pmid}"


class Citation(UUIDModel):
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    chunk = models.ForeignKey(Chunk, null=True, blank=True, on_delete=models.PROTECT)
    external_article = models.ForeignKey(
        ExternalArticle, null=True, blank=True, on_delete=models.PROTECT
    )
    rank = models.PositiveIntegerField()
    relevance_score = models.FloatField()
    used_in_answer = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(chunk__isnull=False, external_article__isnull=True)
                    | Q(chunk__isnull=True, external_article__isnull=False)
                ),
                name="citation_one_target",
            )
        ]
