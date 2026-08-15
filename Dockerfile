# Portability insurance. The app is a single Python process that reads
# DATABASE_URL and binds $PORT, so it runs unchanged on Render (native runtime),
# Cloud Run, Koyeb, a VPS, or anything else that speaks containers. Keeping this
# file means the hosting decision stays reversible at ~10 minutes' notice
# instead of becoming a migration.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY orqen/ ./orqen/
COPY data/ ./data/

# Cloud Run injects PORT (8080); Render injects its own. Default keeps local
# `docker run` working without arguments.
ENV PORT=8080
EXPOSE 8080

# Single worker on purpose: the probe fan-out is threaded inside one process and
# the free tiers everywhere give a fraction of a CPU. More workers would just
# multiply the memory floor.
CMD exec uvicorn orqen.api:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 65
