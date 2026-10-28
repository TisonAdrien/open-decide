# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Core execution engine (`DecisionEngine`) with confidence threshold, fallback
  routing, cycle guard, and full trace.
- Typed decision model: `noul`, `choice`, `score`.
- Pluggable backends with singleton cache: `mock`, `tamev`, `openjev`, `cascade`.
- Context truncation (head + tail) to keep inference latency predictable.
- Multimodal ingestion: text, PDF, scanned PDF (OCR via pdf2image + Tesseract),
  images (OCR), with actionable errors when optional deps are missing.
- Structured field extraction (regex): amounts (with currency), dates (ISO
  8601 normalized), emails, phones, IBAN, invoice numbers.
- FastAPI application with endpoints: `/`, `/editor`, `/api/run`,
  `/api/run-file`, `/api/ingest`, `/api/extract`, `/api/backends`,
  `/api/examples/{name}`.
- No-code web UI: JSON editor, run button, trace timeline, and a visual
  canvas editor (vis-network).
- `Dockerfile` (multi-stage, non-root, healthcheck) and `Makefile`
  (install, format, lint, type, test, run, run-bench, docker-*).
- GitHub Actions CI (lint, format, types, tests on 3.11 and 3.12).
- Documentation: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`,
  `docs/architecture.md`, `docs/backends.md`.
- Templates: bug report, feature request, pull request.

## [0.1.0] - TBD

Initial public release.
