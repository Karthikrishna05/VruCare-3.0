from pathlib import Path

import yaml
from django.core.management.base import BaseCommand

from apps.corpus.ingest import ingest
from apps.corpus.tasks import ingest_corpus


class Command(BaseCommand):
    help = "Read the PDFs in the corpus folder and index them"

    def add_arguments(self, parser):
        parser.add_argument("--config", default="configs/baseline.yaml")
        parser.add_argument("--corpus-dir", default="data/corpus")
        parser.add_argument(
            "--sync", action="store_true", help="run here,not in worker"
        )

    def handle(self, *args, **options):
        config = yaml.safe_load(Path(options["config"]).read_text("utf-8"))
        if not options["sync"]:
            job = ingest_corpus.delay(options["corpus_dir"], config)
            self.stdout.write(f"Queued job {job.id}. Follow it with:")
            self.stdout.write("  docker compose logs -f worker")
            return
        report = ingest(options["corpus_dir"], config)
        for warning in report["warnings"]:
            self.stdout.write(self.style.WARNING(warning))
        self.stdout.write(
            f"added {len(report['added'])} ~skipped {len(report['skipped'])} ~removed {len(report['removed'])} ~new chunks {report['chunks']}"
        )
