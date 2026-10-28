# Security Policy

## Supported versions

Only the latest commit on `main` is supported. This project is pre-1.0.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report by email to the maintainers (see commit history) or via GitHub's
private vulnerability reporting:
https://github.com/TisonAdrien/open-decide/security/advisories/new

Include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix

You should receive an acknowledgement within 72 hours. We will coordinate a
fix and a disclosure date with you.

## Scope

In scope:

- The FastAPI application (API handlers, auth if added later)
- The ingestion pipeline (PDF, images) -- arbitrary file upload
- Backends if they accept external input (they do)

Out of scope (for now):

- Third-party models (TAMEV, OpenJev) -- report upstream
- Local-only development servers (uvicorn --reload, make run)

## Best practices for deployments

- Run behind a reverse proxy (Caddy, nginx) with TLS
- Set an upload size limit at the proxy level (`client_max_body_size`)
- Run the Docker image as the non-root `app` user (it already does)
- Do not expose `/api/run-file` without authentication on a public network
