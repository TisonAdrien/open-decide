# Open Decide

[![CI](https://github.com/TisonAdrien/open-decide/actions/workflows/ci.yml/badge.svg)](https://github.com/TisonAdrien/open-decide/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

> Build complex decision trees, one fast decision model at every branch.

Open Decide is an open source, no-code tool to design and run decision trees
where each branch is decided by a fast, Jev-class decision model -- not a
generative LLM. It is designed for auditable, low-latency, deterministic
workflows over unstructured inputs (text, PDFs, images).

## Why

Generative LLMs are powerful but slow, expensive and non-deterministic. For
routing, triage and classification tasks, small decision models (Jev, TAMEV,
OpenJev) offer:

- Speed      : sub-100 ms per decision on CPU
- Cost       : negligible per call, no API
- Calibration: probabilities you can actually threshold on
- Determinism: same input, same output at a fixed threshold

Open Decide turns those properties into a visual, auditable decision tree,
with a full execution trace for every run.

## Features

- No-code tree editor -- JSON editor plus a visual canvas (vis-network)
- Typed decisions -- noul (yes/no), choice (N-way), score (ordinal)
- Pluggable backends -- mock, tamev, openjev, cascade
- Confidence-aware routing with fallback paths and cycle guard
- Multimodal ingestion -- text, PDF, scanned PDF (OCR), images
- Structured field extraction -- amounts, dates, emails, phones, IBAN, invoices
- Full traceability -- path, probabilities, latency, fallback/escalation flags
- Context truncation and singleton backend cache for predictable latency

## Quickstart

Prerequisites: Python 3.11+, uv (https://docs.astral.sh/uv/).

    git clone https://github.com/TisonAdrien/open-decide.git
    cd open-decide
    uv sync --extra dev --extra ingest

### 1. Mock backend (no model, 5 seconds)

    uv run uvicorn open_decide.api.main:app --reload

Open http://127.0.0.1:8000/, click "Load example", paste some text, Run.

### 2. TAMEV backend (~90 MB, CPU-friendly)

    uv sync --extra dev --extra ingest --extra tamev
    OPEN_DECIDE_PRELOAD_BACKEND=tamev uv run uvicorn open_decide.api.main:app --reload

Select "tamev" as the backend in the UI.

### 3. Cascade backend (recommended for real workloads)

    uv sync --extra dev --extra ingest --extra tamev --extra openjev
    OPEN_DECIDE_PRELOAD_BACKEND=cascade uv run uvicorn open_decide.api.main:app --reload

Select "cascade": TAMEV answers easy cases in ~10 ms, OpenJev escalates only
when TAMEV's confidence is below the threshold.

## Backend comparison

| Backend   | Size     | p50 (CPU) | Use case                                          |
| :-------- | :------- | :-------- | :------------------------------------------------ |
| mock      | 0        | <1 ms     | Tests, UI demos, wiring                          |
| tamev     | 90 MB    | ~7 ms     | Fast routing when signal is clear                |
| openjev   | ~7 GB    | 200 ms-9 s| Ambiguous cases, higher accuracy                 |
| cascade   | both     | ~10 ms (easy) / ~1-3 s (hard) | Best of both worlds          |

OpenJev is a 1.7B model designed for GPU. On CPU, its inference time scales
with the input length (attention is O(n^2) on the prefill). Open Decide
truncates context (head + tail, 4000 chars) by default to keep latency
predictable.

## Docker

    docker build -t open-decide:latest .
    docker run --rm -p 8000:8000 open-decide:latest

The image ships with mock, tamev and cascade. To add OpenJev, rebuild with
`--extra openjev` -- but be aware the image grows by ~7 GB.

## How it works

    +--------------------+      +---------------------------+
    | Web UI (vanilla)   | ---> | FastAPI (api/main.py)     |
    +--------------------+      +-------------+-------------+
                                            |
                                +-----------v-----------+
                                | DecisionEngine        |
                                | (threshold, fallback) |
                                +-----+-----------+-----+
                                      |           |
                              +-------v---+   +---v-------------+
                              | Models    |   | DecisionBackend |
                              | (Pydantic)|   | (mock/tamev/..) |
                              +-----------+   +-----------------+

Every run returns a RunResult with a full trace: for each node, the question,
the options, the chosen label, its probabilities, the latency, and whether a
fallback or escalation was taken.

See docs/architecture.md for the full design.

## Development

    make install      # uv sync --extra dev --extra ingest
    make test         # pytest
    make lint         # ruff check
    make type         # mypy
    make format       # ruff format + check --fix
    make run          # dev server with reload (WSL-friendly)
    make run-bench    # dev server without reload (for benchmarks)

Integration tests for TAMEV and OpenJev are opt-in:

    OPEN_DECIDE_TEST_TAMEV=1 uv run --extra dev --extra ingest --extra tamev pytest tests/test_backends_tamev.py -v

## Project layout

    src/open_decide/
      models.py            Pydantic schema (nodes, decisions, traces)
      engine.py            Execution engine (pure, backend-agnostic)
      context.py           Context truncation (head + tail)
      ingest.py            PDF, scanned PDF (OCR), images, text
      extract.py           Structured field extraction (regex)
      backends/            Decision backends (mock, tamev, openjev, cascade)
      api/main.py          FastAPI app
      web/                 Templates, static assets, JS
    tests/                 Unit and API tests
    examples/              Example decision trees
    docs/                  Architecture and backend docs

## Contributing

See CONTRIBUTING.md. This project follows the Contributor Covenant
(CODE_OF_CONDUCT.md). Security disclosures: see SECURITY.md.

## License

MIT -- see LICENSE.
