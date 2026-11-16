# syntax=docker/dockerfile:1
# Imagem do NotePi para o k3s (arm64 no Raspberry Pi, amd64 para testar no PC).
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
RUN python -m venv /venv
COPY requirements.lock ./
RUN /venv/bin/pip install --require-hashes -r requirements.lock
COPY pyproject.toml ./
COPY notepi ./notepi
RUN /venv/bin/pip install --no-deps .

FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PATH=/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NOTEPI_DB=/dados/notas.db \
    NOTEPI_BACKUP_DIR=/backup
RUN groupadd --gid 10001 notepi \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin notepi
COPY --from=build /venv /venv
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "notepi.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "20"]
