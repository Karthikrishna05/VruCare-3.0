from pathlib import Path

import yaml
from django.core.management.base import BaseCommand

from apps.retrieval.search import retrieve


class Command(BaseCommand):
    help = "Print the best chunks for a question"

    def add_arguments(self, parser):
        parser.add_argument("query")
        parser.add_argument("--config", default="configs/baseline.yaml")

    def handle(self, *args, **options):
        config = yaml.safe_load(Path(options["config"]).read_text("utf-8"))
        for number, item in enumerate(retrieve(options["query"], config), start=1):
            cosine = "-" if item.dense_cosine is None else f"{item.dense_cosine:.3f}"
            self.stdout.write(
                f"{number}. {item.chunk_id}  fused {item.fused_score:.4f}  "
                f"meaning #{item.dense_rank or '-'} (cosine {cosine})  "
                f"keyword #{item.sparse_rank or '-'}"
            )
            self.stdout.write(f"   {item.title}, page {item.page_start}")
            self.stdout.write(f"   {' '.join(item.text.split())[:160]}...")
