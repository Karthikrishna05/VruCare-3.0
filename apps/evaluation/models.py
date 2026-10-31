from django.db import models

from apps.base import UUIDModel
from apps.corpus.models import Chunk


class EvalQuestion(UUIDModel):
    SPLITS = [("dev", "Dev"), ("holdout", "Holdout")]
    BEHAVIOURS = [("answer", "Answer"), ("refuse", "Refuse"), ("escalate", "Escalate")]
    key = models.CharField(max_length=16, unique=True)
    text = models.TextField()
    category = models.CharField(max_length=48)
    split = models.CharField(max_length=16, choices=SPLITS)
    conversation_context = models.JSONField(null=True, blank=True)
    expected_behaviour = models.CharField(max_length=48, choices=BEHAVIOURS)

    def __str__(self):
        return f"{self.key}:{self.text[:60]}"


class EvalJudgement(UUIDModel):
    question = models.ForeignKey(EvalQuestion, on_delete=models.CASCADE)
    chunk = models.ForeignKey(Chunk, on_delete=models.PROTECT)
    relevant = models.BooleanField(null=True, blank=True)
    annotated_at = models.DateTimeField(null=True, blank=True)
    pool_source = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["question", "chunk"], name="judgement_unique"
            )
        ]


class EvalRun(UUIDModel):
    commit_sha = models.CharField(max_length=40, db_index=True)
    split = models.CharField(max_length=16, choices=EvalQuestion.SPLITS)
    tier = models.CharField(max_length=8)
    config = models.JSONField()
    metrics = models.JSONField()
    n_runs = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.commit_sha[:7]} {self.split} {self.tier}"
