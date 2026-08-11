# syntax=docker/dockerfile:1
#
# Multi-stage build for the CasePilot API.
#   Stage 1 "builder": has uv + build tooling, resolves and installs deps.
#   Stage 2 "runtime": slim image with ONLY the app + its venv. No uv, no cache.
# Why two stages? The final image stays small and has no build tools in it
# (smaller attack surface, faster pulls). This is the standard prod pattern.

# ---------- Stage 1: builder ----------
# The uv images are built ON TOP of the official python images, so the Python
# lives at the same path (/usr/local/bin/python) as the runtime stage below.
# That path-match is what lets us copy the venv across stages safely.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies FIRST, from just the lockfiles. Because these two files
# change rarely, Docker caches this layer — so editing app code doesn't force a
# full dependency reinstall on every build. --no-dev skips ruff/ty (prod image).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Now copy the application source (changes often -> its own late layer).
COPY app ./app

# ---------- Stage 2: runtime ----------
FROM python:3.14-slim-bookworm AS runtime

# Run as an unprivileged user, never root, inside the container.
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

# Bring over the ready-to-run venv and the app code from the builder.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/app /app/app

# Putting the venv's bin on PATH means `fastapi`/`python` resolve to it.
ENV PATH="/app/.venv/bin:$PATH"

USER appuser
EXPOSE 8000

# Container-native liveness check (no curl in slim image, so use python).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# `fastapi run` is the production server (uvicorn under the hood).
# 0.0.0.0 so it's reachable from outside the container.
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
