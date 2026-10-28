"""FastAPI application for Open Decide."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError

from open_decide.backends import (
    BackendError,
    BackendNotAvailable,
    get_backend,
    preload_backend,
)
from open_decide.engine import (
    DecisionEngine,
    EngineError,
    InvalidBackendAnswer,
    LowConfidenceNoFallback,
    MaxStepsExceeded,
)
from open_decide.extract import extract_fields
from open_decide.ingest import (
    IngestionDependencyMissing,
    IngestionError,
    UnsupportedFileType,
    extract_text,
)
from open_decide.models import DecisionTree, RunResult

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"
_TEMPLATES_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"


def _resolve_examples_dir() -> Path:
    for candidate in (
        Path.cwd() / "examples",
        Path(__file__).resolve().parents[3] / "examples",
    ):
        if candidate.is_dir():
            return candidate
    return Path.cwd() / "examples"


_EXAMPLES_DIR = _resolve_examples_dir()


def _startup_preload() -> None:
    """Optionally preload a backend at startup.

    Set ``OPEN_DECIDE_PRELOAD_BACKEND=tamev`` (or ``openjev``) to pay the
    model-loading cost once at boot instead of on the first request.
    """
    name = os.environ.get("OPEN_DECIDE_PRELOAD_BACKEND")
    if not name:
        return
    # A failed preload is not fatal: the error will surface on first use
    # with a clean BackendNotAvailable from the backend itself.
    with suppress(Exception):
        preload_backend(name)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    _startup_preload()
    yield
    # Explicitly unload heavy models before dropping references, so torch
    # can release memory (especially CUDA) deterministically on shutdown.
    from open_decide.backends import clear_backend_cache, list_cached_backends

    for backend in list_cached_backends():
        unload = getattr(backend, "unload", None)
        if callable(unload):
            unload()
    clear_backend_cache()


app = FastAPI(title="Open Decide", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class RunRequest(BaseModel):
    tree: dict[str, Any]
    input: str
    backend: str = "mock"
    backend_kwargs: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = 200


class BackendsResponse(BaseModel):
    backends: list[str]


class IngestResponse(BaseModel):
    filename: str
    chars: int
    text: str


class ExtractResponse(BaseModel):
    filename: str
    chars: int
    fields: dict[str, Any]


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/editor", response_class=HTMLResponse)
async def editor(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "editor.html", {})


# --------------------------------------------------------------------------- #
# Meta
# --------------------------------------------------------------------------- #


@app.get("/api/backends", response_model=BackendsResponse)
async def list_backends() -> BackendsResponse:
    return BackendsResponse(backends=["mock", "tamev", "openjev", "cascade"])


@app.get("/api/examples/{name}")
async def get_example(name: str) -> dict[str, Any]:
    if "/" in name or ".." in name:
        raise HTTPException(status_code=404, detail="invalid example name")
    path = _EXAMPLES_DIR / f"{name}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"example {name!r} not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail=f"example {name!r} is not a JSON object")
    return data


# --------------------------------------------------------------------------- #
# Execution core (shared by /api/run and /api/run-file)
# --------------------------------------------------------------------------- #


async def _execute_run(
    tree_data: dict[str, Any],
    context: str,
    backend_name: str,
    backend_kwargs: dict[str, Any],
    max_steps: int,
) -> RunResult:
    try:
        tree = DecisionTree.model_validate(tree_data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_tree", "errors": exc.errors()},
        ) from exc

    try:
        backend = get_backend(backend_name, **backend_kwargs)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "unknown_backend", "message": str(exc)},
        ) from exc

    engine = DecisionEngine(backend, max_steps=max_steps)

    try:
        return await engine.run(tree, context)
    except BackendNotAvailable as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "backend_unavailable", "message": str(exc)},
        ) from exc
    except BackendError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "backend_error", "message": str(exc)},
        ) from exc
    except MaxStepsExceeded as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "max_steps_exceeded", "message": str(exc)},
        ) from exc
    except InvalidBackendAnswer as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_backend_answer", "message": str(exc)},
        ) from exc
    except LowConfidenceNoFallback as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "low_confidence_no_fallback", "message": str(exc)},
        ) from exc
    except EngineError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "engine_error", "message": str(exc)},
        ) from exc


def _ingestion_http_error(exc: IngestionError) -> HTTPException:
    if isinstance(exc, UnsupportedFileType):
        code = "unsupported_file_type"
    elif isinstance(exc, IngestionDependencyMissing):
        code = "ingestion_dependency_missing"
    else:
        code = "ingestion_failed"
    return HTTPException(
        status_code=422,
        detail={"code": code, "message": str(exc)},
    )


# --------------------------------------------------------------------------- #
# Run endpoints
# --------------------------------------------------------------------------- #


@app.post("/api/run", response_model=RunResult)
async def run(payload: RunRequest) -> RunResult:
    return await _execute_run(
        payload.tree,
        payload.input,
        payload.backend,
        payload.backend_kwargs,
        payload.max_steps,
    )


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile = File(...)) -> IngestResponse:
    """Extract text from a PDF, an image or a text file (no execution)."""
    if file.filename is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "missing_filename", "message": "file has no name"},
        )
    data = await file.read()
    try:
        text = extract_text(data, file.filename)
    except IngestionError as exc:
        raise _ingestion_http_error(exc) from exc
    return IngestResponse(filename=file.filename, chars=len(text), text=text)


@app.post("/api/extract", response_model=ExtractResponse)
async def extract(file: UploadFile = File(...)) -> ExtractResponse:
    """Extract text and structured fields from an uploaded file."""
    if file.filename is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "missing_filename", "message": "file has no name"},
        )
    data = await file.read()
    try:
        text = extract_text(data, file.filename)
    except IngestionError as exc:
        raise _ingestion_http_error(exc) from exc
    fields = extract_fields(text)
    return ExtractResponse(filename=file.filename, chars=len(text), fields=fields)


@app.post("/api/run-file", response_model=RunResult)
async def run_file(
    tree: str = Form(...),
    backend: str = Form("mock"),
    max_steps: int = Form(200),
    file: UploadFile | None = File(None),
    input_text: str | None = Form(None),
) -> RunResult:
    """Ingest an uploaded file (or use ``input_text``) and run the tree."""
    try:
        tree_data = json.loads(tree)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_tree_json", "message": str(exc)},
        ) from exc
    if not isinstance(tree_data, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_tree_json",
                "message": "tree must be a JSON object",
            },
        )

    if file is not None and file.filename:
        data = await file.read()
        try:
            context = extract_text(data, file.filename)
        except IngestionError as exc:
            raise _ingestion_http_error(exc) from exc
    elif input_text:
        context = input_text
    else:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "missing_input",
                "message": "provide either a file or input_text",
            },
        )

    return await _execute_run(tree_data, context, backend, {}, max_steps)
