from django.db import models

from apps.base import UUIDModel
from apps.chat.models import Message


class AgentTrace(UUIDModel):
    NODES = [
        ("triage", "Triage"),
        ("retrieve", "Retrieve"),
        ("sufficiency", "Sufficiency"),
        ("pubmed", "PubMed"),
        ("generate", "Generate"),
        ("guardrail", "Guardrail"),
    ]
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    step_index = models.PositiveIntegerField()
    node = models.CharField(max_length=32, choices=NODES)
    decision = models.CharField(max_length=64)
    duration_ms = models.PositiveIntegerField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "step_index"], name="trace_step_unique"
            )
        ]

    def __str__(self):
        return f"{self.step_index}:{self.node} -> {self.decision}"
