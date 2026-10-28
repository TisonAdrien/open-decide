---
name: Bug report
about: Something is broken or behaves unexpectedly
title: "[BUG] "
labels: bug
assignees: ""
---

**Describe the bug**

A clear and concise description of what the bug is.

**To reproduce**

Steps to reproduce the behavior:

1. Tree JSON used (paste or attach)
2. Input text (or file type)
3. Backend selected (mock / tamev / openjev / cascade)
4. Observed result

**Expected behavior**

What you expected to happen.

**Environment**

- OS / WSL distro:
- Python version: (output of `uv run python --version`)
- Open Decide version: (output of `git rev-parse --short HEAD`)
- Backend extras installed: (tamev / openjev / ingest / dev)
- GPU available: (output of `nvidia-smi` if relevant)

**Full trace (if possible)**

Paste the `RunResult.path` from the API response, or the full traceback.
