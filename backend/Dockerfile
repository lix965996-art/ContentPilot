FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY backend/docker-entrypoint.sh /usr/local/bin/contentpilot-entrypoint

RUN addgroup --system contentpilot \
    && adduser --system --ingroup contentpilot contentpilot \
    && mkdir -p /app/uploads /app/data \
    && chown -R contentpilot:contentpilot /app \
    && chmod +x /usr/local/bin/contentpilot-entrypoint

USER contentpilot

EXPOSE 8000

ENTRYPOINT ["contentpilot-entrypoint"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
