"""
Production AI Agent — Part 6 Final Project.

Luồng xử lý POST /ask:
  verify_api_key (401) → check_rate_limit (429) → check_budget (402)
  → gọi LLM → record_cost → trả kết quả

Kiểm tra:  python check_production_ready.py
"""
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

import redis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


# ─────────────────────────────────────────────────────────
# Structured logging (tiêu chí 10): mỗi dòng log = 1 JSON object
# ─────────────────────────────────────────────────────────
_STD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        # Các field truyền qua extra={...} được đưa vào JSON
        for key, value in record.__dict__.items():
            if key not in _STD_ATTRS and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            # Ghi tên lỗi vào log nội bộ; stack trace KHÔNG bao giờ trả về cho client
            entry["error"] = repr(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=False, default=str)


def _setup_logger() -> logging.Logger:
    log = logging.getLogger("agent")
    log.setLevel(settings.log_level)
    log.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log.addHandler(handler)
    log.propagate = False  # không để root logger in thêm 1 dòng dạng text
    return log


logger = _setup_logger()


# ─────────────────────────────────────────────────────────
# Graceful shutdown (tiêu chí 11)
# Khi nhận SIGTERM, uvicorn: ngừng nhận kết nối mới → chờ request đang chạy xong
# → chạy phần sau `yield` của lifespan → thoát với exit code 0.
# Không tự đăng ký signal handler để không ghi đè handler của uvicorn.
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", extra={"environment": settings.environment, "port": settings.port,
                                  "rate_limit_per_minute": settings.rate_limit_per_minute,
                                  "daily_budget_usd": settings.daily_budget_usd,
                                  "redis_ok": redis_healthy()})
    yield
    logger.info("shutdown", extra={"reason": "SIGTERM or stop — in-flight requests finished"})
    try:
        r.close()
    except Exception:
        pass


app = FastAPI(title="Production AI Agent", version="1.0.0", lifespan=lifespan,
              docs_url=None if settings.environment == "production" else "/docs",
              redoc_url=None)


# ─────────────────────────────────────────────────────────
# Middleware: log mỗi request (không log body / API key)
# ─────────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_error", extra={"request_id": request_id, "path": request.url.path})
        response = JSONResponse(status_code=500, content={"detail": "Internal server error",
                                                          "request_id": request_id})
    response.headers["X-Request-ID"] = request_id
    logger.info("request", extra={"request_id": request_id, "method": request.method,
                                  "path": request.url.path, "status": response.status_code,
                                  "ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


@app.exception_handler(redis.RedisError)
async def redis_error_handler(request: Request, exc: redis.RedisError):
    """Redis chết giữa chừng → 503 rõ ràng thay vì 500 kèm stack trace."""
    logger.error("redis_unavailable", extra={"path": request.url.path, "error": repr(exc)})
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable"},
                        headers={"Retry-After": "5"})


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class AskRequest(BaseModel):
    question: Question
    user_id: str | None = Field(default=None, max_length=64)


def _count_tokens(text: str) -> int:
    """Ước lượng token (~4 ký tự / token) vì mock LLM không trả usage."""
    return max(1, len(text) // 4)


@app.get("/")
def root():
    return {"service": "production-ai-agent", "environment": settings.environment,
            "endpoints": ["GET /health", "GET /ready", "POST /ask"]}


@app.get("/health")
def health():
    """Liveness (tiêu chí 4): process còn sống → 200. Không phụ thuộc Redis,
    nếu không platform sẽ restart container chỉ vì Redis chết — restart không sửa được Redis."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness (tiêu chí 5): chỉ nhận traffic khi Redis kết nối được, ngược lại 503
    để load balancer tạm ngừng gửi request tới instance này."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis not reachable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)          # 429
    check_budget()                     # 402

    answer = llm_ask(body.question)

    input_tokens = _count_tokens(body.question)
    output_tokens = _count_tokens(answer)
    cost = record_cost(input_tokens, output_tokens)
    logger.info("llm_call", extra={"input_tokens": input_tokens, "output_tokens": output_tokens,
                                   "cost_usd": round(cost, 8)})
    return {
        "question": body.question,
        "answer": answer,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                  "cost_usd": round(cost, 8)},
    }
