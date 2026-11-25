"""
Cost guard (tiêu chí 8).

  • Cộng dồn chi phí LLM theo ngày (UTC) trong Redis: key cost:YYYY-MM-DD
  • Tổng chi phí trong ngày đạt DAILY_BUDGET_USD → HTTP 402 cho tới hết ngày
Rate limit bảo vệ khỏi gọi quá NHANH; cost guard bảo vệ khỏi tiêu quá NHIỀU tiền.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

KEY_TTL_SECONDS = 2 * 24 * 3600  # giữ 2 ngày rồi Redis tự xoá


def _today_key() -> str:
    return "cost:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")


def current_spend() -> float:
    return float(r.get(_today_key()) or 0.0)


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → HTTP 402."""
    spent = current_spend()
    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=(f"Daily budget exceeded: spent ${spent:.6f} "
                    f"of ${settings.daily_budget_usd:.6f}. Try again tomorrow (UTC)."),
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào tổng của ngày, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    key = _today_key()
    pipe = r.pipeline(transaction=True)
    pipe.incrbyfloat(key, cost)   # INCRBYFLOAT là atomic → nhiều worker cộng cùng lúc không mất số
    pipe.expire(key, KEY_TTL_SECONDS)
    pipe.execute()
    return cost
