# Day 14 Lab — Mission Answers

> Bài cá nhân · Lớp K5-L3A. Môi trường: Windows 11 + WSL2 Ubuntu, Python 3.11.18, Docker Desktop 29.9.3.

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
Trong `01-localhost-vs-production/develop/app.py`:

1. **Secret hard-code trong code** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-..."` và `DATABASE_URL = "postgresql://admin:password123@..."`. Push lên GitHub là lộ key và mật khẩu DB; muốn đổi key phải sửa code và deploy lại.
2. **Log ra secret** (dòng 34): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` — key nằm trong log, ai đọc được log là lấy được key (đã thấy thật trong log khi chạy, xem 1.2).
3. **Dùng `print()` thay cho logging có cấu trúc** (dòng 33, 34, 38): không có level, timestamp, không parse được bằng log aggregator; còn in toàn bộ câu hỏi/câu trả lời của user ra log.
4. **Config cố định trong code** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` — không đổi được giữa dev/staging/prod mà không sửa code.
5. **Không có health check** (dòng 42–43): gọi `GET /health` trả 404 → platform không biết app còn sống để restart.
6. **Bind `host="localhost"`** (dòng 51): trong container/cloud, request từ ngoài không vào được vì chỉ nghe trên loopback.
7. **Port cố định 8000** (dòng 52): Railway/Render cấp port qua biến `PORT`, app không đọc biến này.
8. **`reload=True`** (dòng 53): chế độ dev (theo dõi file, chạy 2 process) bật cả khi chạy production.
9. **Không xử lý shutdown**: không có lifespan/SIGTERM handler, không đóng kết nối, không đợi request đang chạy.
10. **Input không validate**: `question` lấy từ query string, không giới hạn độ dài.

### Exercise 1.2: Kết quả chạy bản develop
Bản develop nhận `question` qua query string:

```text
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 422 Unprocessable Entity
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}

$ curl -i http://localhost:8000/health
HTTP/1.1 404 Not Found
```

Log server — secret bị in ra:
```text
INFO:     Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [9512] using WatchFiles
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
```

**Quan sát:** chạy được, nhưng không production-ready: lộ key trong log, không có `/health`, chỉ nghe `localhost`, bật reloader.

Bản production (`ENVIRONMENT=development python app.py`) nhận JSON, có `/health` và `/ready`:
```text
$ curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). ...","model":"gpt-4o-mini"}
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":1.2,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:36:40.024048+00:00"}
$ curl http://localhost:8000/ready
{"ready":true}
```
Server nghe `0.0.0.0:8000`, chỉ log `WARNING:root:OPENAI_API_KEY not set — using mock LLM`, không in secret.

> Nhận xét thêm: các dòng log JSON (`logger.info(...)`) của bản production **không hiện** khi chạy. Lý do: `config.py` gọi `logging.warning()` lúc import, việc này tự cấu hình root logger ở mức WARNING, nên `logging.basicConfig(level=INFO, format=...)` trong `app.py` chạy sau không còn tác dụng. Ở Part 6 tôi tránh lỗi này bằng cách tự gắn handler + `JsonFormatter` cho logger riêng.

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Tại sao quan trọng? |
|---------|---------|------------|---------------------|
| Config | Hard-code trong code (`OPENAI_API_KEY`, `DEBUG`, `MAX_TOKENS`, port) | Đọc env qua `config.py` (`Settings` dataclass + `os.getenv`), có `.env.example`, `validate()` fail-fast khi production thiếu `AGENT_API_KEY` | Cùng một code chạy dev/staging/prod chỉ khác env; secret không nằm trong git; đổi cấu hình không cần build lại |
| Secrets | Ghi thẳng trong code và còn in ra log | Lấy từ env, không log secret (chỉ log độ dài câu hỏi) | Lộ key = mất tiền/bị lạm dụng; secret trong lịch sử git không xoá được |
| Health check | ❌ Không có (`/health` → 404) | ✅ `/health` (liveness: uptime, version) + `/ready` (readiness, 503 khi chưa sẵn sàng) | Platform/LB biết khi nào restart container và khi nào được gửi traffic |
| Logging | `print()`, in cả secret | Log dạng JSON (`{"time":..., "level":..., "msg":...}`), event có cấu trúc | Dễ parse/search/alert trong Loki, Datadog...; không lộ dữ liệu nhạy cảm |
| Host / Port | `localhost:8000` cố định | `0.0.0.0` + `PORT` từ env | Container/cloud cần nghe mọi interface và port do platform cấp |
| Reload / Debug | `reload=True`, `DEBUG=True` luôn bật | `reload` chỉ khi `DEBUG=true` | Reloader tốn tài nguyên, debug có thể lộ thông tin lỗi |
| Shutdown | Đột ngột, không cleanup | Graceful: `lifespan` dọn dẹp, có handler SIGTERM | Request đang chạy không bị cắt, đóng kết nối DB/Redis sạch sẽ khi deploy/scale down |
| Input | Query string, không validate | Body JSON, thiếu `question` → 422 rõ ràng | Báo lỗi rõ cho client, chặn input xấu |
| CORS | Không cấu hình | `ALLOWED_ORIGINS` từ env | Chỉ frontend được phép mới gọi từ trình duyệt |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)
1. **Base image:** `python:3.11` — bản Python đầy đủ (Debian + build tools, compiler, header...), rất nặng (image cuối 1,67 GB).
2. **Working directory:** `/app` (`WORKDIR /app`) — mọi lệnh `COPY`, `RUN`, `CMD` sau đó chạy trong thư mục này.
3. **Vì sao `COPY requirements.txt` trước:** Docker cache theo từng layer. Copy riêng `requirements.txt` rồi `pip install` trước, sau đó mới `COPY app.py`; khi chỉ sửa code thì layer cài package vẫn dùng cache, build lại mất vài giây thay vì cài lại toàn bộ thư viện. Nếu `COPY . .` trước thì mỗi lần sửa 1 dòng code là cài lại hết.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh/tham số **mặc định**, bị ghi đè khi chạy `docker run image <lệnh khác>`. `ENTRYPOINT` là chương trình **cố định** của container, tham số của `docker run` được nối thêm vào sau (muốn đổi phải dùng `--entrypoint`). Thường dùng `ENTRYPOINT` cho file thực thi chính và `CMD` cho tham số mặc định. Nên dùng exec form (`["python", "app.py"]`) để process là PID 1 và nhận được SIGTERM.

### Exercise 2.2: Build và run
```text
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -d -p 8000:8000 my-agent:develop
$ curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":0.6,"container":true}
```

### Exercise 2.3: Multi-stage build và image size comparison
`02-docker/production/Dockerfile`:
- **Stage 1 (`builder`, `python:3.11-slim`):** cài build tools (`gcc`, `libpq-dev`) và `pip install --user -r requirements.txt` vào `/root/.local`. Stage này chỉ để build, không được deploy.
- **Stage 2 (`runtime`, `python:3.11-slim`):** tạo user non-root `appuser`, chỉ copy `/root/.local` (package đã cài) từ builder + `main.py` + `utils/`, đặt `USER appuser`, `HEALTHCHECK`, chạy `uvicorn --workers 2`.
- **Vì sao nhỏ hơn:** base `slim` bỏ phần lớn thư viện hệ thống; gcc, header, apt cache, pip cache nằm lại ở stage builder và không vào image cuối; image cuối chỉ có Python runtime + package + code.

Đo bằng `docker images` (ngày 2026-11-25):
```text
$ docker images my-agent
REPOSITORY   TAG        IMAGE ID       SIZE
my-agent     advanced   50b7818aed2a   240MB
my-agent     develop    2f2e4b5e3342   1.67GB
```
- Develop: **1667,8 MB** (1 667 776 006 bytes)
- Production (advanced): **239,8 MB** (239 815 418 bytes)
- Difference: nhỏ hơn **85,6 %** (`1 − 239,8 / 1667,8`), tức develop nặng gấp ~7 lần.

### Exercise 2.4: Docker Compose stack
Chạy `touch .env.local && docker compose -p k5-day14-docker up -d --build` trong `02-docker/production/`. Services được start: `agent`, `redis`, `qdrant`, `nginx`.

```text
                      ┌──────────────────────── network "internal" (bridge) ─────────────────────────┐
 Client ──HTTP:80──▶  │  nginx (nginx:alpine)  ──proxy_pass──▶  agent:8000 (FastAPI, 2 workers)        │
 (localhost:80/443)   │   - rate limit 10 r/s                         │            │                  │
                      │   - security headers                          ▼            ▼                  │
                      │                                      redis:6379      qdrant:6333              │
                      │                                    (cache/session)   (vector DB cho RAG)      │
                      └──────────────────────────────────────────────────────────────────────────────┘
```
- Chỉ **nginx** mở port ra ngoài (80, 443); agent, redis, qdrant chỉ nằm trong network `internal`, gọi nhau bằng **tên service** (Docker DNS): `REDIS_URL=redis://redis:6379/0`, `QDRANT_URL=http://qdrant:6333`.
- `depends_on: condition: service_healthy`: agent chỉ start khi redis và qdrant đã healthy; nginx start sau agent.

```text
$ docker compose -p k5-day14-docker ps
SERVICE   IMAGE                   STATUS                            PORTS
agent     k5-day14-docker-agent   Up 5 seconds (health: starting)   8000/tcp
nginx     nginx:alpine            Up 4 seconds                      0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
qdrant    qdrant/qdrant:v1.9.0    Up 16 seconds (healthy)           6333-6334/tcp
redis     redis:7-alpine          Up 15 seconds (healthy)           6379/tcp

$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
{"status":"ok","uptime_seconds":3.1,"version":"2.0.0","timestamp":"2026-11-25T08:43:36.205534"}

$ curl -i http://localhost/ask -X POST -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```
Header `Server: nginx` và các security header cho thấy request đi qua Nginx rồi mới tới agent.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Deploy agent Part 6 lên Railway
- URL: https://agent-production-92b8234c.up.railway.app
- Nền tảng chính: Railway. Deploy thư mục `06-lab-complete/` (agent Part 6) bằng `railway up`, build từ `Dockerfile` theo `railway.toml`; thêm Railway Redis và đặt `REDIS_URL=${{Redis.REDIS_URL}}`.
- 4 lệnh tự kiểm ở CP6: `/health` → 200, `/ready` → 200, `/ask` không key → 401, `/ask` có key → 200. Rate limit trên cloud: request thứ 11 trong 60 giây → 429.
- Chi tiết, biến môi trường và ảnh chụp: xem `DEPLOYMENT.md`.

### Exercise 3.2: So sánh `railway.toml` và `render.yaml`

| Điểm khác | `railway.toml` | `render.yaml` | Vì sao |
|---|---|---|---|
| Phạm vi | Cấu hình **1 service** (cách build + deploy) | **Blueprint** mô tả cả hạ tầng: nhiều service (web + Redis/Key Value), region, plan | Railway tạo service/database bằng dashboard hoặc CLI (`railway add`), file chỉ nói service này build/chạy thế nào; Render dựng toàn bộ stack từ một file (Infrastructure as Code) |
| Cách build | `[build] builder = "DOCKERFILE"` (hoặc `NIXPACKS` tự nhận diện Python) | `runtime: docker` + `dockerfilePath`, hoặc `runtime: python` + `buildCommand` | Cả hai đều cho chọn Docker hay tự build; bài này dùng Dockerfile để môi trường cloud giống hệt local |
| Lệnh chạy | `startCommand` (bỏ trống thì dùng `CMD` của Dockerfile) | `startCommand` | Port do platform cấp qua `$PORT`, nên lệnh chạy phải đọc biến này |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout` | `healthCheckPath: /health` | Platform chỉ chuyển traffic sang bản mới khi `/health` trả 200 (zero-downtime deploy) |
| Restart | `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries` | Render tự restart, không cấu hình trong file | |
| Biến môi trường / secret | **Không khai báo trong file**: đặt bằng `railway variables` hoặc dashboard; tham chiếu service khác bằng `${{Redis.REDIS_URL}}` | Khai báo trong `envVars`: giá trị thường dùng `value`, secret dùng `sync: false` (nhập tay trên dashboard) hoặc `generateValue: true` (Render tự sinh), nối Redis bằng `fromService` | Cả hai đều không ghi giá trị secret vào file commit lên git |
| Redis | Thêm bằng `railway add --database redis` | Khai báo luôn trong file (`type: keyvalue` / `type: redis`) | |

Tóm lại: `railway.toml` gọn, chỉ lo build/deploy một service, phần hạ tầng và secret nằm trên dashboard/CLI; `render.yaml` dài hơn nhưng mô tả được cả stack và danh sách biến môi trường, nên tạo lại môi trường mới từ git dễ hơn.

### Exercise 3.3: Pipeline CI/CD Cloud Run (`cloudbuild.yaml` + `service.yaml`)
1. **test** — Cloud Build chạy container `python:3.11-slim`, cài `requirements.txt` + pytest rồi chạy `pytest tests/`; test fail thì pipeline dừng, không build.
2. **build** — build Docker image, gắn 2 tag `ai-agent:$COMMIT_SHA` và `ai-agent:latest`, dùng `--cache-from ...:latest` để tận dụng layer cache.
3. **push** — đẩy cả 2 tag lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **deploy** — `gcloud run deploy` image theo đúng `$COMMIT_SHA` lên region `asia-southeast1`: min 1 / max 10 instance, 512Mi RAM, 1 CPU, timeout 60s, `ENVIRONMENT=production`, secret lấy từ Secret Manager (`--set-secrets`), không ghi trong file.
5. `service.yaml` mô tả cùng service đó theo kiểu khai báo (Knative): autoscaling 1–10 instance, mỗi instance tối đa 80 request đồng thời; `livenessProbe` gọi `/health`, `startupProbe` gọi `/ready`; `AGENT_API_KEY` và `OPENAI_API_KEY` lấy từ Secret Manager qua `secretKeyRef`.

---

## Part 4: API Security

### Exercise 4.1: API Key authentication (`04-api-gateway/develop`)
- **Key được check ở đâu:** hàm dependency `verify_api_key()` (dòng 39–54) đọc header `X-API-Key` qua `APIKeyHeader(name="X-API-Key", auto_error=False)`, được gắn vào `/ask` bằng `Depends(verify_api_key)`. Key đúng lấy từ env `AGENT_API_KEY`.
- **Sai key thì sao:** thiếu header → **401** "Missing API key"; có header nhưng sai → **403** "Invalid API key" (Part 6 yêu cầu cả hai trường hợp đều 401, nên bản Part 6 của tôi trả 401 cho cả hai).
- **Rotate key:** đổi giá trị `AGENT_API_KEY` trên platform rồi restart/redeploy — không phải sửa code. Để không làm gián đoạn client, nên cho phép 2 key cùng lúc trong thời gian chuyển (vd `AGENT_API_KEYS=old,new`), báo client đổi sang key mới, rồi bỏ key cũ.

Chạy `AGENT_API_KEY=secret-key-123 python app.py`:
```text
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2: JWT authentication (`04-api-gateway/production`)
**JWT flow** (`auth.py`):
1. Client `POST /auth/token` với username/password → `authenticate_user()` kiểm tra trong `DEMO_USERS`.
2. `create_token()` ký JWT bằng HS256 với `JWT_SECRET`, payload gồm `sub` (username), `role`, `iat`, `exp` (60 phút).
3. Client gửi `Authorization: Bearer <token>` ở mọi request.
4. `verify_token()` kiểm tra chữ ký + hạn → lấy `username`, `role` từ token, **không cần tra database**. Thiếu token → 401, hết hạn → 401, token sai/giả → 403.

```text
$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
HTTP/1.1 200 OK
x-content-type-options: nosniff
x-frame-options: DENY
{"access_token":"<TOKEN_HIDDEN>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer <TOKEN_HIDDEN>"}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 401 Unauthorized
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```
(Token đã được che.)

### Exercise 4.3: Rate limiting
- **Algorithm:** **sliding window log** — mỗi user có một `deque` lưu timestamp các request trong 60 giây gần nhất; mỗi lần gọi xoá timestamp cũ hơn 60 giây rồi đếm (không phải token bucket).
- **Limit:** user thường (`student`) **10 request/phút**; admin (`teacher`) **100 request/phút**.
- **Bypass cho admin:** `/ask` chọn limiter theo `role` trong JWT: `rate_limiter_admin if role == "admin" else rate_limiter_user` — admin dùng limiter có ngưỡng cao hơn (muốn bỏ hẳn thì bỏ qua `limiter.check()` khi `role == "admin"`).
- Hạn chế: state nằm trong RAM của process → nhiều instance thì mỗi instance đếm riêng; restart là mất. Part 6 chuyển sang Redis sorted set để khắc phục.

Vòng lặp 20 request với token của `student` (1 request ở 4.2 đã được tính trước đó):
```text
$ for i in {1..20}; do curl -s -o /dev/null -w "%{http_code} " -X POST http://localhost:8000/ask -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"question\": \"Test $i\"}"; done
200 200 200 200 200 200 200 200 200 429 429 429 429 429 429 429 429 429 429 429

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"question":"Test 21"}'
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost guard implementation
**Bản mẫu (`04-api-gateway/production/cost_guard.py`):** trước khi gọi LLM, `check_budget(user)` kiểm tra: tổng chi phí toàn hệ thống trong ngày ≥ $10 → **503**; chi phí của user trong ngày ≥ $1 → **402**; ≥ 80% thì log cảnh báo. Sau khi gọi LLM, `record_usage()` cộng token → chi phí theo giá gpt-4o-mini ($0,15/1M input, $0,60/1M output). State lưu trong dict (RAM), reset theo ngày.
```text
$ curl http://localhost:8000/me/usage -H "Authorization: Bearer $TOKEN"
{"user_id":"student","date":"2026-11-25","requests":10,"input_tokens":40,"output_tokens":312,"cost_usd":0.000193,"budget_usd":1.0,"budget_remaining_usd":0.999807,"budget_used_pct":0.0}
```
(Ghi chú: trong response của `/ask`, field `budget_remaining_usd` thực ra đang trả **số đã dùng** (`usage.total_cost_usd`), đặt tên sai.)

**Cách tôi làm (Redis, dùng được khi nhiều instance) — theo đề Exercise 4.4, $10/tháng/user:**
```python
from datetime import datetime, timezone
import redis
r = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10"))

def check_budget(user_id: str, estimated_cost: float) -> bool:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    key = f"budget:{user_id}:{month}"           # key mới mỗi tháng → tự "reset đầu tháng"
    current = float(r.get(key) or 0)
    if current + estimated_cost > MONTHLY_BUDGET_USD:
        return False                              # caller trả HTTP 402
    pipe = r.pipeline()
    pipe.incrbyfloat(key, estimated_cost)         # atomic: nhiều instance cộng cùng lúc không mất số
    pipe.expire(key, 32 * 24 * 3600)              # giữ 32 ngày rồi Redis tự xoá
    pipe.execute()
    return True
```
- Key theo `user_id` + tháng (`YYYY-MM`) nên sang tháng mới là key mới — không cần cron reset.
- `INCRBYFLOAT` là lệnh atomic của Redis nên nhiều worker/instance cùng cộng vẫn đúng; state nằm ngoài process nên restart không mất.
- Part 6 (`06-lab-complete/app/cost_guard.py`) dùng cùng ý tưởng theo **ngày**: `check_budget()` đọc `cost:YYYY-MM-DD`, ≥ `DAILY_BUDGET_USD` → 402; `record_cost()` tính chi phí thật sau khi gọi LLM rồi `INCRBYFLOAT`.
- **Rate limit vs cost guard:** rate limit chặn gọi quá **nhanh** (bảo vệ hạ tầng khỏi spike/abuse); cost guard chặn tiêu quá **nhiều tiền** — gọi chậm nhưng đều cả ngày, hoặc vài request với prompt rất dài, vẫn có thể đốt hết budget mà không chạm rate limit. Cần cả hai.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks (`05-scaling-reliability/develop`)
- **`/health` (liveness):** "process còn sống không?" — trả 200 kèm uptime, version, kiểm tra RAM bằng `psutil` (`degraded` nếu > 90%). Fail → platform **restart** container.
- **`/ready` (readiness):** "đã sẵn sàng nhận traffic chưa?" — 503 khi đang khởi động/đang shutdown (`_is_ready=False`) hoặc dependency (Redis, DB) chưa kết nối. Fail → LB **ngừng gửi traffic** vào instance đó nhưng không restart.
- Vì sao tách: Redis chết thì restart agent cũng không sửa được, chỉ cần tạm ngừng nhận traffic. Nếu gộp, Redis chết sẽ làm tất cả agent bị restart liên tục.

```text
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":1.9,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:45:09.083334+00:00","checks":{"memory":{"status":"ok","used_percent":22.8}}}
$ curl http://localhost:8000/ready
{"ready":true,"in_flight_requests":1}
```

### Exercise 5.2: Graceful shutdown
App đếm request đang xử lý bằng middleware (`_in_flight_requests`); khi shutdown, phần sau `yield` của `lifespan` đặt `_is_ready=False` (để `/ready` trả 503) rồi chờ tối đa 30s cho `_in_flight_requests` về 0. `uvicorn.run(..., timeout_graceful_shutdown=30)`.

Test: gửi request rồi `kill -TERM` ngay sau 50ms:
```text
in-flight request result:
{"answer":"Đây là câu trả lời từ AI agent (mock). ..."}  -> HTTP 200
process exit code: 0

--- server log:
INFO:     Shutting down
INFO:     127.0.0.1:41290 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-25 15:45:12,206 INFO 🔄 Graceful shutdown initiated...
2026-11-25 15:45:12,216 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [10178]
2026-11-25 15:45:12,216 INFO Received signal 15 — uvicorn will handle graceful shutdown
```
**Kết quả:** request đang chạy vẫn hoàn thành (200) rồi process mới thoát, exit code 0. Uvicorn nhận SIGTERM → ngừng nhận kết nối mới → đợi request xong → chạy lifespan shutdown. Handler `handle_sigterm` của app chỉ log thêm; dòng log của nó in ra **sau cùng** vì trong lúc chạy uvicorn tạm thay handler SIGTERM bằng handler của chính nó, xử lý shutdown xong mới gọi lại handler cũ của app.

### Exercise 5.3: Stateless design
`05-scaling-reliability/production/app.py` lưu session/conversation history trong **Redis** (`session:<id>`, `SETEX` TTL 1 giờ), không lưu dict trong RAM. Mỗi request đọc history từ Redis → thêm message → ghi lại. Vì vậy bất kỳ instance nào cũng phục vụ tiếp được cuộc hội thoại của user.
Vì sao cần: khi scale ra nhiều instance, mỗi instance có RAM riêng; nếu history nằm trong RAM, request 2 của user đến instance khác sẽ mất history, và restart/deploy là mất toàn bộ. (Ghi chú: code mẫu tự fallback về dict trong RAM nếu không kết nối được Redis lúc khởi động — tiện cho demo nhưng trong production nên fail ở `/ready` thay vì âm thầm chạy stateful.)

### Exercise 5.4: Load balancing
`docker compose -p k5-day14-scaling up -d --build --scale agent=3` trong `05-scaling-reliability/production/`:
```text
NAME                       STATUS                    PORTS
k5-day14-scaling-agent-1   Up 32 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   Up 32 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   Up 32 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   Up 32 seconds             0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   Up 43 seconds (healthy)   6379/tcp
```
10 request `POST http://localhost:8080/chat`, đếm theo `served_by`:
```text
      3 instance-1acb73 redis
      4 instance-6933c8 redis
      3 instance-79f446 redis
```
`docker compose -p k5-day14-scaling logs agent | grep "POST /chat"` đếm theo container: `agent-1: 4`, `agent-2: 4`, `agent-3: 3` (gồm 1 request thử trước đó) → Nginx chia round-robin khá đều cho 3 instance. Nginx tìm các instance qua Docker DNS (`server agent:8000`, `resolver 127.0.0.11`), header `X-Served-By` cho biết IP instance đã xử lý.

Lưu ý: lần chạy đầu, gửi request ngay sau `up --build` thì Nginx trả **502** vì vừa tạo lại các container agent (IP mới) trong lúc Nginx còn giữ địa chỉ cũ; chờ vài giây khi mọi instance `healthy` là hết.

### Exercise 5.5: Test stateless
```text
$ python test_stateless.py
Session ID: 9181b783-9fd5-44a2-a408-c1aa16b0b29c
Request 1: [instance-1acb73]   Q: What is Docker?
Request 2: [instance-79f446]   Q: Why do we need containers?
Request 3: [instance-6933c8]   Q: What is Kubernetes?
Request 4: [instance-1acb73]   Q: How does load balancing work?
Request 5: [instance-79f446]   Q: What is Redis used for?
------------------------------------------------------------
Total requests: 5
Instances used: {'instance-79f446', 'instance-6933c8', 'instance-1acb73'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```
**Giải thích:** 5 câu của cùng một `session_id` được 3 instance khác nhau xử lý, nhưng history đọc lại vẫn đủ 10 message (5 user + 5 assistant) theo đúng thứ tự → state nằm trong Redis, không nằm trong instance nào.

Script không tự tắt instance, nên tôi thử thêm: tạo session, `docker stop k5-day14-scaling-agent-1`, gửi tiếp 4 câu cùng session:
```text
stopped k5-day14-scaling-agent-1
HTTP 200 served_by instance-79f446
HTTP 200 served_by instance-1acb73
HTTP 200 served_by instance-1acb73
HTTP 200 served_by instance-79f446
history count: 10 ['turn A', 'turn B', 'turn C', 'turn D', 'turn E']
```
Một instance chết, các request tiếp theo vẫn 200 (Nginx `proxy_next_upstream` chuyển sang instance còn sống) và history không mất. (Ghi chú: field `turn` trong response của app mẫu bị lệch +1 — câu đầu tiên đã báo `turn: 2` — vì đếm sau khi đã append câu hỏi vào history.)

---

## Part 6: Final Project

Code nằm trong `06-lab-complete/`. Chạy `python check_production_ready.py` (bản đầy đủ, có Docker) trong WSL2 ngày 2026-11-25. Image production: 273 MB.

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## Part 7: Benchmark & Observability

Báo cáo đầy đủ (bảng số liệu, thí nghiệm alert, trace, scaling): **`BENCHMARK_REPORT.md`**. Bằng chứng: `reports/` (7 file load test + 3 file eval), `benchmark-results/` (CSV Locust scale 1 / 3), 4 ảnh Part 7 trong `screenshots/`, job CI `.github/workflows/eval.yml`.

### Exercise 7.1: Đọc metrics của agent
Output `curl -s http://localhost:8002/metrics | grep -v "^#"` (sau 1 request `/ask` và 2 request URL lạ):
```text
http_requests_total{method="POST",route="/ask",status="200"} 1.0
http_requests_total{method="GET",route="unmatched",status="404"} 2.0
agent_in_flight_requests 0.0
llm_request_duration_seconds_bucket{le="0.2",model="mock-llm-small"} 1.0
llm_request_duration_seconds_count{model="mock-llm-small"} 1.0
llm_tokens_total{model="mock-llm-small",type="input"} 91.0
llm_cost_usd_total{model="mock-llm-small"} 4.6649999999999996e-05
agent_info{model="mock-llm-small",version="v2"} 1.0
agent_question_length_chars_bucket{le="50.0"} 1.0
agent_question_length_chars_sum 40.0
```
1. **Counter:** `http_requests_total`, `llm_tokens_total`, `llm_cost_usd_total` (chỉ tăng, dùng với `rate()`). **Gauge:** `agent_in_flight_requests` (lên xuống theo số request đang xử lý), `agent_info`. **Histogram:** `http_request_duration_seconds`, `llm_request_duration_seconds` (các series `_bucket{le=...}`, `_sum`, `_count` → tính percentile bằng `histogram_quantile`).
2. **Nếu dùng `request.url.path` làm label `route`:** mỗi URL lạ mà bot quét (`/wp-admin`, `/.env`, `/a1b2c3`...) tạo ra một giá trị label mới → một **time series mới** cho mỗi tổ hợp method × route × status (và × mỗi bucket của histogram). Hàng nghìn URL rác = hàng nghìn/chục nghìn series → **cardinality bùng nổ**: Prometheus tốn RAM/disk, query chậm, có thể OOM, và kẻ tấn công làm sập hệ thống giám sát chỉ bằng cách gọi URL ngẫu nhiên. Dùng route template thì mọi URL không khớp route gộp vào một series `route="unmatched"` (đã thấy ở trên: 2 request lạ → 1 series).
3. **Metric mới:** thêm `agent_question_length_chars` vào `develop/app.py` — Histogram với `buckets=(20, 50, 100, 200, 500, 1000, 2000)`, `QUESTION_LENGTH.observe(len(body.question))` trong `/ask`. Dùng Histogram chứ không dùng label `length=...` vì độ dài có vô số giá trị. Câu hỏi 40 ký tự ở trên rơi vào bucket `le="50"`, `_sum = 40`.

### Exercise 7.2 – 7.7
Xem `BENCHMARK_REPORT.md`: mục 2 (load test & tail latency), mục 3 (eval, sửa knowledge base, quality gate CI), mục 4 (dashboard, 7.4 Q&A, thí nghiệm A–E, trace), mục 5 (scaling).

---

## AI log

| # | Phần | Đã hỏi AI gì | AI trả về gì | Tôi tự sửa / tự kiểm tra thế nào |
|---|---|---|---|---|
| 1 | Setup | Nhờ Claude Code đọc toàn bộ tài liệu lab và liệt kê cần cài gì, các bước làm | Danh sách công cụ còn thiếu (Python 3.11 trong WSL, bật Docker WSL integration, Node.js cho Railway) và lộ trình CP0–CP8 | Tự cài `uv` và Python 3.11 trong WSL, tự bật WSL integration trong Docker Desktop; kiểm tra `os.name == posix`, `docker run hello-world` chạy được |
| 2 | Part 6 | Nhờ Claude Code viết code cho các TODO trong `06-lab-complete/` (`app/*.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) và giải thích từng phần | Code hoàn chỉnh + giải thích: API key 401, sliding-window rate limit bằng Redis sorted set (429), cost guard bằng `INCRBYFLOAT` theo ngày (402), `/health` vs `/ready`, log JSON, graceful shutdown qua lifespan, Dockerfile multi-stage non-root | Đọc lại từng file theo phần giải thích; chạy `python check_production_ready.py` bản đầy đủ trong WSL → `PASS 12/12`, 43/43 checks |
| 3 | Part 3 (CP6) | Nhờ Claude Code deploy agent Part 6 lên Railway, viết `DEPLOYMENT.md` và phần so sánh `railway.toml`/`render.yaml`, tóm tắt pipeline Cloud Run | Các lệnh `railway init/add/variables/up/domain`; phát hiện Railway CLI chạy trong WSL đọc file trên `/mnt/d` thành byte 0 (build lỗi "exclude-patterns ... non-printable") → chép thư mục deploy sang `~/day14-deploy` trong WSL rồi `railway up` từ đó | Tự đăng nhập Railway; chạy 4 lệnh tự kiểm CP6 trên URL public → 200/200/401/200, rate limit → 429; đối chiếu lại `cloudbuild.yaml`, `service.yaml` khi đọc phần tóm tắt |
| 4 | Part 1, 2, 4, 5, 7 (CP1–CP4, CP7, CP8) | Nhờ Claude Code chạy toàn bộ ví dụ Part 1–5, load test / eval / observability stack Part 7, chụp ảnh và viết câu trả lời + `BENCHMARK_REPORT.md` | Output thật của các lệnh (curl, `docker images`, `test_stateless.py`, `load_test.py`, `run_eval.py`, Locust CSV, Prometheus/Jaeger API); sửa `KNOWLEDGE_BASE` (thêm HPA, JWT), thêm metric `agent_question_length_chars`, job CI `eval.yml`; sửa `production/Dockerfile` Part 7 (thiếu `PYTHONUSERBASE` → container crash); phát hiện `LLMCostBurnRateHigh` firing sẵn ở tải thường | Đối chiếu mọi số trong báo cáo với file JSON/CSV đã nộp; eval cuối `--min-accuracy 1.0` PASS 23/23, 0 regression; ảnh Grafana/Jaeger/Prometheus chụp bằng Chrome headless và đã mở xem lại từng ảnh |
