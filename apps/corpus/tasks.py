from celery import shared_task

from apps.corpus.ingest import ingest


@shared_task
def ingest_corpus(corpus_dir, config):
    return ingest(corpus_dir, config)
