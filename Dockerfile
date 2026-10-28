# syntax=docker/dockerfile:1.7
# ---------- build stage ----------
FROM python:3.11-slim AS builder

# Install uv from the official image
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

# uv tweaks: precompile .pyc, copy packages (no hardlinks across stages),
# and never download another Python (we use the base image one).
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Layer-cache: install deps first, without the project and without dev extras
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Then copy sources and install the project
COPY src ./src
COPY examples ./examples
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------- runtime stage ----------
FROM python:3.11-slim

RUN useradd --create-home --uid 1000 app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://127.0.0.1:8000/api/backends', timeout=2.0).raise_for_status()"

CMD ["uvicorn", "open_decide.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
