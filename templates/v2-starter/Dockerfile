# my-app — Manaurum Platform v2 hosted app.
#
# `manaurum app deploy` tars this directory, the platform builds this
# image from it, pushes it to the internal registry, and runs it on Swarm
# behind Traefik at https://my-app.apps.manaurum.com/.
#
# PORT — read this before you change it. The gateway proxies to
# `manifest.runtime.port` (default 80 when the field is absent).
# `EXPOSE` is documentation only; the platform never parses it. So the
# port below and `runtime.port` in manifest.json MUST agree, or every
# request 502s with `upstream_unreachable`.
#
# This starter listens on 8000 and declares it explicitly, which is what
# every hosted v2 app in production does. 8000 is also unprivileged, so
# the non-root user below can bind it on any host configuration.
#
# Never bake a credential into this image. The platform injects
# MANAURUM_RUNTIME_TOKEN / MANAURUM_CORE_URL / MANAURUM_TENANT_ID /
# MANAURUM_APP_ID / CORE_USER_CONTEXT_PUBLIC_KEY_PEM at run time.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Run as a non-root user — the handler never needs root.
RUN useradd --create-home --uid 10001 appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
RUN chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
