FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY .python-version pyproject.toml requirements.lock requirements-dev.lock README.md ./
COPY build_backend ./build_backend
COPY src ./src
COPY tests ./tests

ENTRYPOINT ["python", "-m", "coldstart"]
CMD ["--help"]
