# ============================================================
# Production Dockerfile — multi-stage (tiêu chí 1, 11, 12)
# ============================================================

# ── Stage 1: builder — cài dependencies vào một venv riêng ──
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
# Copy requirements TRƯỚC source code: code đổi thì layer cài package vẫn dùng cache
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install -r requirements.txt

# ── Stage 2: runtime — chỉ copy venv + code, không có pip cache / file build ──
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# User non-root: lỡ app bị khai thác thì kẻ tấn công không có quyền root trong container
RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app/ ./app/
COPY --chown=app:app utils/ ./utils/

USER app
EXPOSE 8000

# Docker / platform gọi /health định kỳ; fail 3 lần liên tiếp → container "unhealthy"
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=3)"]

# `exec` thay sh bằng uvicorn → uvicorn là PID 1 và nhận SIGTERM khi `docker stop`.
# Nghe theo biến PORT do Railway/Render cấp, mặc định 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
