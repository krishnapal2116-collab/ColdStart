FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY .python-version pyproject.toml requirements.lock requirements-dev.lock README.md LICENSE ./
COPY build_backend ./build_backend
COPY src ./src

# Install the package itself instead of relying on a source-tree PYTHONPATH.
# The project has no third-party runtime dependencies, and the vendored build
# backend keeps this step independent of the network after the base image is
# available.
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation .

# The CLI only needs to read the mounted repository.  A numeric user keeps the
# image independent of distribution-specific user-management utilities.
USER 65532:65532

ENTRYPOINT ["coldstart"]
CMD ["--help"]
