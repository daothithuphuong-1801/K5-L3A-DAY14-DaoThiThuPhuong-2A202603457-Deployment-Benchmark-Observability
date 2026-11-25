# Day 14 Lab — Mission Answers

> Bài cá nhân · Lớp K5-L3A. Môi trường: Windows 11 + WSL2 Ubuntu, Python 3.11.18, Docker Desktop 29.9.3.

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
_(CP1 — chưa làm)_

### Exercise 1.2: Kết quả chạy bản develop
_(CP1 — chưa làm)_

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Tại sao quan trọng? |
|---------|---------|------------|---------------------|
| Config | | | |
| Health check | | | |
| Logging | | | |
| Shutdown | | | |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
_(CP2 — chưa làm)_

### Exercise 2.2: Build và run
_(CP2 — chưa làm)_

### Exercise 2.3: Image size comparison
- Develop: ___ MB
- Production: ___ MB
- Difference: ___ %

### Exercise 2.4: Docker Compose stack
_(CP2 — chưa làm)_

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

### Exercise 4.1–4.3: Test results
_(CP3 — chưa làm)_

### Exercise 4.4: Cost guard implementation
_(CP3 — chưa làm)_

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.5: Implementation notes
_(CP4 — chưa làm)_

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

## AI log

| # | Phần | Đã hỏi AI gì | AI trả về gì | Tôi tự sửa / tự kiểm tra thế nào |
|---|---|---|---|---|
| 1 | Setup | Nhờ Claude Code đọc toàn bộ tài liệu lab và liệt kê cần cài gì, các bước làm | Danh sách công cụ còn thiếu (Python 3.11 trong WSL, bật Docker WSL integration, Node.js cho Railway) và lộ trình CP0–CP8 | Tự cài `uv` và Python 3.11 trong WSL, tự bật WSL integration trong Docker Desktop; kiểm tra `os.name == posix`, `docker run hello-world` chạy được |
| 2 | Part 6 | Nhờ Claude Code viết code cho các TODO trong `06-lab-complete/` (`app/*.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) và giải thích từng phần | Code hoàn chỉnh + giải thích: API key 401, sliding-window rate limit bằng Redis sorted set (429), cost guard bằng `INCRBYFLOAT` theo ngày (402), `/health` vs `/ready`, log JSON, graceful shutdown qua lifespan, Dockerfile multi-stage non-root | Đọc lại từng file theo phần giải thích; chạy `python check_production_ready.py` bản đầy đủ trong WSL → `PASS 12/12`, 43/43 checks |
| 3 | Part 3 (CP6) | Nhờ Claude Code deploy agent Part 6 lên Railway, viết `DEPLOYMENT.md` và phần so sánh `railway.toml`/`render.yaml`, tóm tắt pipeline Cloud Run | Các lệnh `railway init/add/variables/up/domain`; phát hiện Railway CLI chạy trong WSL đọc file trên `/mnt/d` thành byte 0 (build lỗi "exclude-patterns ... non-printable") → chép thư mục deploy sang `~/day14-deploy` trong WSL rồi `railway up` từ đó | Tự đăng nhập Railway; chạy 4 lệnh tự kiểm CP6 trên URL public → 200/200/401/200, rate limit → 429; đối chiếu lại `cloudbuild.yaml`, `service.yaml` khi đọc phần tóm tắt |
