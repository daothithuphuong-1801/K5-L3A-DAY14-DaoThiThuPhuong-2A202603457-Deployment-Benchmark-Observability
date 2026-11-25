# Deployment Information

## Public URL
https://agent-production-92b8234c.up.railway.app

## Platform
Railway — project `day14-agent`, gồm 2 service:

| Service | Nguồn | Vai trò |
|---|---|---|
| `agent` | `06-lab-complete/Dockerfile` (builder `DOCKERFILE` trong `railway.toml`) | AI agent Part 6, healthcheck `/health` |
| `Redis` | Railway Redis database | State của rate limiter và cost guard |

Agent nối tới Redis qua mạng nội bộ của Railway (`redis.railway.internal:6379`), Redis không mở ra internet.

## Test Commands

Đặt `BASE` và `AGENT_API_KEY` (key lấy từ tab Variables của service `agent` trên Railway, không ghi trong repo):

```bash
BASE=https://agent-production-92b8234c.up.railway.app

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả chạy ngày 2026-11-25: `200`, `200`, `401`, `200`.

### API Test (with authentication)
```bash
curl -X POST "$BASE/ask" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What is deployment?"}'
```
Response:
```json
{"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được.","usage":{"input_tokens":4,"output_tokens":19,"cost_usd":1.2e-05}}
```

### Rate limit (RATE_LIMIT_PER_MINUTE=10)
Gửi 15 request liên tiếp với cùng key:
```
200 200 200 200 200 200 200 200 429 429 429 429 429 429 429
```
(2 request trước đó trong cùng phút đã được tính, nên request thứ 9 của vòng lặp là request thứ 11 trong cửa sổ 60 giây → 429.)

## Environment Variables Set
Đặt trên Railway (service `agent` → Variables), không ghi trong code hay repo:

| Biến | Giá trị |
|---|---|
| `AGENT_API_KEY` | chuỗi ngẫu nhiên 43 ký tự (`secrets.token_urlsafe(32)`) — secret |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (tham chiếu tới service Redis) — secret |
| `ENVIRONMENT` | `production` |
| `LOG_LEVEL` | `INFO` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `PORT` | Railway tự cấp; `CMD` trong Dockerfile nghe theo `${PORT:-8000}` |

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
