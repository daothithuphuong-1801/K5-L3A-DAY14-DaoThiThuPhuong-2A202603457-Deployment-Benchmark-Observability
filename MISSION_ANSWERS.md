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

### Exercise 3.1 / 3.2: Deploy agent Part 6
- URL: _(CP6 — chưa làm)_
- Chi tiết: xem `DEPLOYMENT.md`

### So sánh `railway.toml` và `render.yaml`
_(CP6 — chưa làm)_

### Exercise 3.3: Pipeline CI/CD Cloud Run
_(CP6 — chưa làm)_

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
