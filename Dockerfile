FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BUS_MODEL_BUNDLE_DIR=/app/release

COPY requirements-serve.lock.txt ./
RUN python -m pip install --disable-pip-version-check --no-cache-dir \
    --no-deps --only-binary=:all: -r requirements-serve.lock.txt \
    && python -m pip check

COPY src/__init__.py src/config.py ./src/
COPY src/api/ ./src/api/
COPY src/features/ ./src/features/
COPY outputs/phase2_serving/ ./release/

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=2).close()"]
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
