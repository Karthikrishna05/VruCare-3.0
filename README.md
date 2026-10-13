# VruCare

An evidence-grounded question-answering system for kidney stone information. It answers only from a curated library of medical documents, cites its sources, refuses to diagnose or prescribe, and checks PubMed when its own library isn't enough.

**Status:** in preparation — no application code yet. Measured results will lead this page when they exist.

> VruCare provides general information from published medical literature. It is not a medical diagnosis and does not replace consultation with a qualified healthcare professional.

## Set up

```bash
py -3.13 scaffold.py
```

Then activate the environment with `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Linux/macOS), copy `.env.example` to `.env`, and run `pre-commit install`.

## Where things are

| Folder | Contents |
|---|---|
| `apps/`, `config/` | Application code (Phase 1 onwards) |
