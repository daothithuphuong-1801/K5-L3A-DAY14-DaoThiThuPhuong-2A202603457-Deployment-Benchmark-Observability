# Benchmark & Observability Report — Day 14

> Mọi con số lấy từ report JSON (`reports/`), CSV Locust (`benchmark-results/`), Prometheus API và screenshot (`screenshots/`) của chính lần chạy này.

**Họ tên:** Đào Thị Thu Phương — 2A202603457
**Ngày chạy:** 2026-11-25
**Môi trường:** Laptop Windows 11 + WSL2 Ubuntu, 8 logical CPU / 7,7 GB RAM; Docker Desktop 29.9.3; Python 3.11.18. Agent develop chạy 1 process uvicorn; stack production: mỗi container agent giới hạn 0,5 CPU / 256 MB.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Lúc bình thường p95 ≈ 220 ms (mock LLM ~120–180 ms + retrieval ~20 ms), nên 500 ms còn dư cho tải tăng nhưng vẫn bắt được khi hệ thống quá tải (c=100 → p95 4,5 s) hoặc tail latency lan lên p95 (slow rate 10% → p95 1,7 s). Alert đặt lỏng hơn (p95 > 1 s trong 2 phút) để tránh báo động vì spike ngắn |
| Error rate `/ask` | < 2 % | Mock LLM tự lỗi ~1% (`MOCK_ERROR_RATE=0.01`) — đó là mức nền chấp nhận được; 2% cho error budget gấp đôi mức nền. Alert ở 5% trong 1 phút |
| Accuracy trên golden dataset | ≥ 85 % và không regression | Bản v2 đạt 91,3% trước khi sửa và 100% sau khi sửa; ngưỡng 85% (dùng trong job CI) chặn được bản tệ như v1 (4,3%), còn điều kiện "không regression" chặn việc sửa câu này làm hỏng câu khác |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 request mỗi mức, `MOCK_SLOW_RATE=0.03`)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.68 | 190.2 | 218.0 | 1682.8 | 1.00 % | ✅ PASS |
| 10 | 40.2 | 191.7 | 221.4 | 1692.6 | 1.00 % | ✅ PASS |
| 50 | 104.36 | 202.8 | 388.0 | 1710.5 | 0.67 % | ✅ PASS |
| 100 | 48.76 | 693.3 | 4464.1 | 4868.8 | 1.33 % | ❌ FAIL (p95) |

(Nguồn: `reports/load_v2_c1.json`, `load_v2_c10.json`, `load_v2_c50.json`, `load_v2_c100.json`.)

**Nhận xét:** RPS tăng gần **tuyến tính** từ c=1 tới c=10 (4,68 → 40,2, ×8,6) vì mỗi request chủ yếu là *chờ* LLM (~200 ms, `asyncio.sleep`), agent xử lý song song được: theo Little's law RPS ≈ concurrency / latency = 10 / 0,22 s ≈ 45. Từ c=10 lên c=50 RPS chỉ ×2,6 (104) và p95 bắt đầu tăng (388 ms): process uvicorn duy nhất bắt đầu nghẽn (event loop phải xử lý JSON, log, metrics cho rất nhiều request cùng lúc, trên cùng máy với load generator). Tới c=100 hệ thống **quá tải**: request phải xếp hàng, p50 lên 693 ms, p95 4,5 s và RPS còn **giảm** xuống 48,8 — thêm concurrency không tăng throughput mà chỉ tăng thời gian chờ. Muốn chịu c=100 phải scale ngang (nhiều instance) chứ không chỉ tăng tải.

### 2.2 Tail latency (agent v2, `--requests 300 --concurrency 20`)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 188.9 | 218.1 | 227.0 |
| 0.03 (mặc định) | 245.8 | 227.1 | 1691.2 |
| 0.1 | 402.5 | 1699.1 | 1715.5 |

(Nguồn: `reports/load_v2_slow_0.json`, `load_v2_slow_0.03.json`, `load_v2_slow_0.1.json`.)

**Nhận xét:** chỉ số nhạy nhất là **p99**, rồi tới **p95**. Với 3% request chậm, avg chỉ tăng 57 ms (188,9 → 245,8) và p95 gần như không đổi (227 ms), nhưng p99 nhảy từ 227 ms lên **1691 ms** ×7,5 — vì 3% request chậm nằm hết ở 1% cuối. Với 10% request chậm (> 5%), p95 cũng lên **1699 ms** trong khi avg mới 402 ms. Average trộn 90–97% request nhanh với vài request rất chậm thành một con số "trông ổn", che mất nhóm người dùng phải chờ gần 2 giây; SLO đặt theo p95/p99 nói thẳng "x% người dùng phải chờ lâu hơn ngưỡng" nên phản ánh đúng trải nghiệm xấu nhất. (Lần chạy 0.03 có error rate 2,33% — do mock lỗi ngẫu nhiên 7/300 lần, không liên quan slow rate.)

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`, 23 câu)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35 % (1/23) | 91.3 % (21/23) | 100 % (23/23) |
| Avg tokens / câu | 57.5 | 108.7 | 113.7 |
| Tổng cost (USD) | 0.000409 | 0.000756 | 0.000790 |
| Cost / câu đúng (USD) | 0.00040935 | 0.00003599 | 0.00003436 |
| Latency p50 / p95 (ms) | 150.4 / 190.7 | 194.1 / 217.9 | 189.6 / 213.2 |
| Quality gate | FAIL (accuracy ≥ 80%) | PASS (≥ 80%, 0 regression so với v1) | PASS (≥ 100%, 0 regression so với v2) |

(Nguồn: `reports/eval_v1.json`, `eval_v2.json`, `eval_v2_fixed.json`.)

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| scaling-03 ("Kubernetes HPA scale dựa trên những chỉ số nào?") | `cpu`, `memory`, `custom metrics` | Thêm vào `KNOWLEDGE_BASE` tài liệu với keyword `["hpa", "kubernetes", "autoscal"]`: "Kubernetes HPA (Horizontal Pod Autoscaler) scale số pod dựa trên CPU, memory hoặc custom metrics như RPS hay độ dài hàng đợi." |
| security-02 ("JWT khác gì API key trong xác thực?") | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu với keyword `["jwt"]`: "API key là chuỗi bí mật cố định, không tự hết hạn. JWT là token có chữ ký số, chứa thông tin user và thời điểm hết hạn; server xác minh chữ ký mà không cần tra database." |

Trước khi sửa, retrieval không tìm thấy tài liệu nào cho 2 câu này nên v2 rơi về câu trả lời chung chung. Keyword mới (`hpa`, `kubernetes`, `jwt`) không xuất hiện trong 21 câu còn lại nên không đổi kết quả retrieval của chúng: chạy lại với `--baseline reports/eval_v2.json` → **2 câu cải thiện, 0 regression**, gate `--min-accuracy 1.0` PASS. Cùng thay đổi được chép sang `production/utils/mock_llm.py`. Không sửa `golden_dataset.jsonl`.

**Quality gate trong CI:** `run_eval.py` trả **exit code 1** khi accuracy < `--min-accuracy` hoặc có regression so với `--baseline`. Kiểm chứng: chạy v1 với `--baseline reports/eval_v2.json` → 20 câu regression, `exit=1`; v2 đã sửa → `exit=0`. Job `.github/workflows/eval.yml` chạy agent v2 (`MOCK_ERROR_RATE=0`) rồi `python eval/run_eval.py --min-accuracy 0.85 --baseline reports/eval_v2_fixed.json`; exit code 1 làm step fail → job fail → bật branch protection "Require status checks to pass" thì PR không merge được.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:** v2 thêm bước retrieval nên prompt dài hơn: **~1,9× token/câu** (57,5 → 108,7), **~1,85× tổng cost** và p95 cao hơn ~27 ms (thêm bước retrieval ~20 ms). Đổi lại accuracy từ 4,35% lên 91,3%, nên **cost trên mỗi câu đúng rẻ hơn ~11 lần** ($0,00040935 → $0,00003599). So 2 phiên bản bằng "cost / câu" thì v1 rẻ hơn, nhưng câu sai là vô giá trị (còn tốn thêm chi phí xử lý hậu quả), nên "cost / câu đúng" mới là chỉ số đúng. Sửa KB tăng thêm ~5 token/câu nhưng cost/câu đúng còn giảm tiếp.

---

## 4. Observability stack (production)

Stack: `docker compose -p k5-day14-observability up -d --build` (agent ×2 + Nginx + Prometheus + Grafana + Jaeger + Locust). Unit test alert rules: `promtool test rules /p/alert_rules_test.yml` → **SUCCESS**.

> Sửa 1 lỗi để stack chạy được: `production/Dockerfile` copy package vào `/home/agent/.local` nhưng user `agent` có HOME=`/app`, container crash `No module named 'uvicorn'` (Nginx trả 502). Thêm `ENV PYTHONUSERBASE=/home/agent/.local` là chạy.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (span lỗi, HTTP 503, event `exception`) — `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với 2 alert đang **firing** (`AgentHighErrorRate`, `AgentHighLatencyP95`) — `screenshots/prometheus-alert-firing.png`

### 4.1b Exercise 7.4 — đọc dashboard (Locust 30 users, ramp 5, 2 instance; số từ Prometheus API lúc 09:16 UTC)

| Chỉ số | Giá trị |
|---|---|
| Traffic `/ask` | 18.87 req/s (instance 172.19.0.5: 9.51, 172.19.0.8: 9.36) |
| p50 / avg / p95 / p99 | 172.5 / 224.0 / 291.0 / 1792.4 ms |
| Error rate | 0.87 % |
| Tokens/s | input 1451.2, output 758.6 |
| LLM p95 | 197.4 ms |
| Cost burn | $4.01 / giờ |

(Ảnh Grafana chụp lúc 16:21 giờ VN: Traffic 13.8 req/s, Error rate 1.24 %, p95 296 ms, in-flight 4, 2 instances, LLM cost 1h $0.7365.)

1. **p95 và avg:** p95 ≈ 291 ms, avg ≈ 224 ms, còn p99 ≈ 1,79 s. Khoảng cách p95–avg nhỏ (~67 ms) nghĩa là phần lớn request đồng đều quanh 200 ms; nhưng p99 cách xa avg cho thấy có một nhóm nhỏ (~3% request "slow" của mock) chậm gần 2 s — avg không thể hiện điều này.
2. **Requests/s theo instance:** 9.51 vs 9.36 req/s — Nginx chia gần như **đều** (round-robin) cho 2 instance.
3. **Input tokens/s > output tokens/s** (1451 vs 759, ~1,9×) vì agent v2 nhét tài liệu retrieval vào prompt: input = câu hỏi + context, output chỉ là câu trả lời ngắn.
4. **`curl http://localhost:8080/metrics`** trả **404 Not Found** từ Nginx: `nginx.conf` chặn `/metrics` từ bên ngoài. Prometheus scrape trực tiếp từng container trong network nội bộ (DNS service discovery), còn người ngoài không được đọc metrics (lộ thông tin nội bộ: số request, cost, version...) hay spam endpoint này.

### 4.2 Thí nghiệm "phá hệ thống" (Locust 30 users chạy suốt; thời gian tính từ lúc `docker compose up -d` áp cấu hình mới)

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` (áp cùng lúc với B) | `AgentHighErrorRate` (giá trị 19.0 %) | pending sau 28 s → **firing sau 83 s** | Error rate (đỏ), "LLM calls theo kết quả" (error tăng), "Requests/s theo status code" (503 tăng) |
| B | `MOCK_SLOW_RATE=0.3` (áp cùng lúc với A) | `AgentHighLatencyP95` (p95 = 1.89 s) | pending sau 33 s → **firing sau 148 s** | Latency p50/p95/p99: p95 và p99 vọt lên ~1,8 s, avg tăng ít hơn |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (giá trị $16.09/giờ) | pending sau 28 s → **firing sau 149 s** | Cost burn rate (USD/giờ): ~$35/giờ (rate 1m) so với ~$4/giờ lúc bình thường; LLM latency tăng |
| D | `docker pause k5-day14-observability-agent-1` | `AgentInstanceDown` (172.19.0.5:8000, `up=0`) | pending sau 15 s → **firing sau 45 s** | Instances up (2 → 1). Error rate của agent vẫn xanh (1.5 %) dù Locust ghi thêm 34 lỗi và max response time lên 10 s |
| E | `AGENT_VERSION=v1` | **Không có** (theo dõi 150 s) | — | Bảng "Phiên bản đang chạy" đổi sang v1; Tokens/s giảm (input 1451 → 678/s); error rate 1.2 %, p95 199 ms vẫn xanh |

Ảnh `prometheus-alert-firing.png` chụp khi A + B đang chạy: 2 alert cùng FIRING.

Ghi chú khi làm:
- `LLMCostBurnRateHigh` **đã firing ngay ở tải bình thường** (30 user, mock-llm-small ≈ $4/giờ > ngưỡng $2/giờ) từ lúc chạy benchmark scale; nó chỉ tắt khi A+B làm throughput giảm. Ngưỡng $2/giờ quá thấp so với mức tải này → alert "kêu" thường xuyên = alert fatigue; nên đặt ngưỡng theo budget thật (vd > 2× mức chi tiêu bình thường).
- Mỗi lần `docker compose up -d` tạo lại container agent, `AgentInstanceDown` vào **pending** vài giây cho IP cũ rồi tự hết (không firing nhờ `for: 30s`) — ví dụ vì sao cần `for`.
- Thí nghiệm D: lỗi 504/timeout xảy ra ở **Nginx** (chờ instance bị pause tới `proxy_read_timeout`), request chưa bao giờ được agent xử lý xong nên metric của agent không đếm → panel Error rate của agent vẫn xanh. Cần giám sát thêm ở tầng load balancer hoặc synthetic check từ ngoài. `docker pause` (không phải `stop`) để container vẫn còn trong DNS nhưng không trả lời → Prometheus thấy `up == 0`.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Đổi sang v1 làm **chất lượng** sụp (accuracy 91% → 4%, theo eval ở mục 3) nhưng hạ tầng vẫn khoẻ: không lỗi 5xx, latency còn thấp hơn, cost giảm. Metrics hạ tầng chỉ trả lời "có chạy không / nhanh không", không trả lời "có đúng không". Cách phát hiện:
1. **Chặn trước khi deploy:** quality gate eval trong CI (job `eval.yml`) — v1 có 20 câu regression → exit code 1 → không merge/deploy được.
2. **Giám sát chất lượng khi chạy:** chạy eval định kỳ (canary/synthetic) với golden dataset trên môi trường production và xuất accuracy thành metric (vd `agent_eval_accuracy`) để alert khi giảm; theo dõi các proxy metric như retrieval hit ratio, độ dài câu trả lời, tỉ lệ câu trả lời "chung chung"; thu feedback người dùng (👍/👎) và LLM-as-judge trên mẫu traffic thật; alert khi `agent_info{version}` đổi ngoài quy trình release.

### 4.3 Debug bằng trace

Trace chậm nhất (tìm theo `llm_ms` lớn nhất trong log, mở bằng `http://localhost:16686/trace/<trace_id>`):

- `trace_id`: `eaa07736a2d964615af7ffe99a12553e`
- Tổng thời gian: **1715.0 ms** (`POST /ask`, HTTP 200)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**1697.9 ms, 99.0 %**) — `gen_ai.request.model=mock-llm-small`, `gen_ai.usage.input_tokens=95`, `gen_ai.usage.output_tokens=55`. Các span khác: `agent.run` 1712.4 ms (span cha), `agent.retrieve_context` 14.3 ms. → Chậm do LLM upstream (request "slow" của mock), không phải code của agent hay retrieval.
- Dòng log tương ứng (grep theo `trace_id` trong `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-25T09:13:19.749675+00:00", "level": "INFO", "service": "observable-agent", "instance": "6dd77d383e20", "event": "llm_call", "trace_id": "eaa07736a2d964615af7ffe99a12553e", "span_id": "d62254e9a23c09ce", "request_id": "07c9cc94a404", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1698.4}
{"ts": "2026-11-25T09:13:19.750530+00:00", "level": "INFO", "service": "observable-agent", "instance": "6dd77d383e20", "event": "http_request", "trace_id": "eaa07736a2d964615af7ffe99a12553e", "span_id": "d62254e9a23c09ce", "request_id": "07c9cc94a404", "method": "POST", "route": "/ask", "status": 200, "ms": 1714.4}
```

Trace lỗi (`screenshots/jaeger-error-trace.png`):

- `trace_id`: `5f4b719c3dcffbf501b3f0253d307d38` — `POST /ask` 99.7 ms, HTTP **503**; span `chat mock-llm-small` (76.9 ms) có status ERROR, `error.type=upstream_unavailable` và event `exception`: "Upstream LLM error: 503 Service Unavailable (mock)"; `agent.run` cũng ghi event `exception`.

```json
{"ts": "2026-11-25T09:11:04.756252+00:00", "level": "INFO", "service": "observable-agent", "instance": "6dd77d383e20", "event": "llm_error", "trace_id": "5f4b719c3dcffbf501b3f0253d307d38", "span_id": "fe31fd7971360a2d", "request_id": "bfa0325c31a3", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, ramp 10/s, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.31 | 200 | 280 | 1700 | 81 / 7098 (1.14 %) |
| 3 | 59.67 | 190 | 270 | 1700 | 84 / 7137 (1.18 %) |

(Dòng `POST /ask` trong `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv`. Dòng Aggregated, gồm cả `GET /health`: 65.69 vs 65.57 req/s. Mọi failure là 503 do mock LLM lỗi ~1%.)

**Giải thích kết quả:** scale 1 → 3 instance **gần như không đổi** RPS (59,3 → 59,7) và p95 (280 → 270 ms). Lý do:
1. **Tải bị giới hạn bởi load generator, không phải agent:** Locust là closed-loop — 100 user, mỗi user chờ `between(0.5, 2)` giây giữa 2 request → tối đa ~100 / (1,25 + 0,22) ≈ 68 req/s. Một instance (0,5 CPU, async) đã phục vụ đủ mức này với p50 ~200 ms, nên thêm instance không có thêm việc để làm.
2. **Nút thắt latency là LLM:** p50 ~190–200 ms gần bằng latency của mock LLM (120 ms + jitter 0–60 ms + retrieval ~20 ms); p99 1,7 s là request "slow" của LLM. Thêm instance không làm LLM nhanh hơn — scale ngang chỉ tăng **throughput tối đa** (khi agent bị CPU/queue nghẽn như c=100 ở mục 2.1), không giảm latency của từng request khi upstream là phần chậm nhất.
Muốn thấy lợi ích của scale cần tăng tải tới khi 1 instance bão hoà (nhiều user hơn / wait_time nhỏ hơn).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Average nói dối:** 3% request chậm làm p99 tăng 7,5× trong khi avg chỉ tăng 30%. SLO và alert phải đặt theo percentile, và luôn nhìn cả p99.
  2. **Hạ tầng xanh ≠ agent đúng:** đổi sang v1 accuracy rơi từ 91% xuống 4% mà không alert nào kêu; lỗi 504 ở Nginx cũng không hiện trên metric của agent. Cần eval chất lượng trong CI/production và giám sát ở nhiều tầng.
  3. **Metrics → traces → logs liên kết bằng `trace_id`:** dashboard cho biết p99 cao, Jaeger chỉ ra 99% thời gian nằm ở span LLM, log JSON cùng `trace_id` cho chi tiết token/cost của đúng request đó. Ngoài ra số liệu chỉ có nghĩa khi hiểu cách đo (closed-loop Locust không chứng minh được lợi ích scale).
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - Metric chất lượng: `agent_eval_accuracy` từ eval định kỳ, tỉ lệ feedback 👎, retrieval hit ratio theo version; alert khi giảm so với baseline.
  - Giám sát ở Nginx/LB (tỉ lệ 5xx/504 của upstream) và synthetic check từ bên ngoài gọi `/ask` mỗi phút.
  - Alert dự báo hết budget (cost theo ngày so với `DAILY_BUDGET_USD`, tỉ lệ 402) với ngưỡng theo budget thật thay vì $2/giờ cố định; alert rate 429 tăng bất thường.
  - Saturation: `agent_in_flight_requests` cao kéo dài, CPU/memory container gần limit, độ dài hàng đợi — để autoscale trước khi p95 vượt SLO.
  - Error budget burn-rate alert (multi-window) thay cho ngưỡng cố định để vừa nhạy vừa ít báo động giả.
