FROM python:3.12-slim

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

COPY backend/requirements-runtime.lock.txt ./requirements-runtime.lock.txt
RUN pip install --no-cache-dir -r requirements-runtime.lock.txt

COPY backend/ ./
COPY frontend/public/ /app/frontend/public/
COPY backend/docker-entrypoint.sh /usr/local/bin/contentpilot-entrypoint

RUN addgroup --system contentpilot \
    && adduser --system --ingroup contentpilot contentpilot \
    && mkdir -p /app/var/uploads /app/var/db /app/var/run /app/var/logs \
        /app/var/sessions /app/var/tools /app/var/cache /app/var/reports /app/var/tmp \
    && chown -R contentpilot:contentpilot /app \
    && chmod +x /usr/local/bin/contentpilot-entrypoint

USER contentpilot

EXPOSE 8000

ENTRYPOINT ["contentpilot-entrypoint"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
