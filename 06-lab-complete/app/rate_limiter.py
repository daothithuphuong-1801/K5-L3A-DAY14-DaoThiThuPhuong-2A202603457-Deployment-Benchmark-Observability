"""
Rate limiting (tiêu chí 7) — sliding window 60 giây bằng Redis sorted set.

Mỗi API key có 1 sorted set: member = 1 request, score = thời điểm (giây).
  1. ZREMRANGEBYSCORE: xoá request cũ hơn 60 giây
  2. ZADD: ghi request hiện tại
  3. ZCARD: đếm số request trong cửa sổ
  4. EXPIRE: key tự xoá khi không dùng nữa
Cả 4 lệnh chạy trong 1 transaction (MULTI/EXEC) nên nhiều worker / instance gọi cùng lúc
vẫn đếm đúng. State nằm trong Redis → restart agent vẫn còn.
"""
import hashlib
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Vượt RATE_LIMIT_PER_MINUTE trong 60 giây → HTTP 429 kèm Retry-After."""
    limit = settings.rate_limit_per_minute
    # Băm API key: không lưu key thật trong Redis
    redis_key = "ratelimit:" + hashlib.sha256(key.encode()).hexdigest()[:32]
    now = time.time()
    member = f"{now}:{uuid.uuid4().hex}"

    pipe = r.pipeline(transaction=True)
    pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
    pipe.zadd(redis_key, {member: now})
    pipe.zcard(redis_key)
    pipe.expire(redis_key, WINDOW_SECONDS)
    _, _, count, _ = pipe.execute()

    if count > limit:
        # Request bị chặn không được tính vào cửa sổ
        r.zrem(redis_key, member)
        oldest = r.zrange(redis_key, 0, 0, withscores=True)
        retry_after = WINDOW_SECONDS
        if oldest:
            retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit} requests / {WINDOW_SECONDS}s",
            headers={"Retry-After": str(retry_after)},
        )
