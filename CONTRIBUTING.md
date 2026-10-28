# Contributing to Open Decide

Thanks for your interest! This project aims to stay small, clean and easy to
hack on. Please read this guide before opening a PR.

## Development setup

We use [`uv`](https://docs.astral.sh/uv/) for dependency management and the
`Makefile` for common tasks.

```bash
git clone https://github.com/<your-fork>/open-decide.git
cd open-decide
make install      # uv sync --extra dev
make test         # uv run pytest -q
