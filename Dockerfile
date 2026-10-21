# Backend image (spec P3-03): one image, two commands —
#   ngdesign serve  (CMD)   -> the API server
#   ngdesign worker (override in compose/chart) -> the solve-job worker
# Multi-stage: build the dependency venv with uv, then copy it into a slim
# runtime. The package runs from source (PYTHONPATH=/app/src) so that
# ngdesign.data's DATA_DIR (Path(__file__).parents[2] / "data") resolves to
# /app/data, which the image ships alongside src/.
FROM ghcr.io/astral-sh/uv:0.5.22 AS uv

FROM python:3.12.8-slim-bookworm AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Deps only, cached independently of the source.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --extra postgres

FROM python:3.12.8-slim-bookworm AS runtime
RUN groupadd --system stomato && useradd --system --gid stomato --no-create-home stomato
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src ./src
COPY data ./data
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1
USER stomato
EXPOSE 8000
# The worker container runs `ngdesign worker` (no HTTP endpoint); compose and
# the chart disable/ignore the healthcheck there. Kubernetes ignores Docker
# HEALTHCHECK entirely, so the chart probes the api Deployment itself.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
ENTRYPOINT ["python", "-m", "ngdesign.cli"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
