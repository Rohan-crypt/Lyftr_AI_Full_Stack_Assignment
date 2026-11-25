# Lyftr AI Full-Stack Assignment - LLM Chatbot with Key Failover & Response Caching

Production-grade full-stack LLM chatbot system featuring automated key failover across provider pools, low-latency LiteLLM response caching, and isolated SQLite multi-turn session storage.

---

## 1. Live URLs

- **Live Frontend (GitHub Pages):** [https://rohan-crypt.github.io/Lyftr_AI_Full_Stack_Assignment/](https://rohan-crypt.github.io/Lyftr_AI_Full_Stack_Assignment/)
- **Live Backend API Base URL (Vercel):** [https://lyftr-ai-backend-ten.vercel.app](https://lyftr-ai-backend-ten.vercel.app)
- **Public GitHub Repository:** [https://github.com/Rohan-crypt/Lyftr_AI_Full_Stack_Assignment](https://github.com/Rohan-crypt/Lyftr_AI_Full_Stack_Assignment)

---

## 2. Run locally: with Docker and without

### Prerequisites
- Docker & Docker Compose (for containerized execution)
- Python 3.10+ (for local backend execution)
- Node.js 18+ & npm (for local frontend execution)

### A. Run with Docker (Recommended)
The whole stack starts with a single command via the included `Makefile`:
```bash
# Start both backend (http://localhost:8000) and frontend (http://localhost:3000)
make up

# Check status / logs
docker compose logs -f

# Shut down the stack
make down
```
The Docker setup utilizes:
- Multi-stage Dockerfile for backend (`python:3.10-slim`, builder and minimal runtime runner).
- Multi-stage Dockerfile for frontend (`node:20-alpine` builder, `nginx:alpine` runner on port 3000).
- Named volume `sqlite_data` mounted at `/data` so SQLite session history survives container restarts.

### B. Run without Docker

#### 1. Backend Setup
```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt

# Set environment variables (or copy .env.example)
export LLM_API_KEYS="your_key_1,your_key_2"
export DATABASE_URL="sqlite:///./data/app.db"
export ALLOWED_ORIGINS="http://localhost:3000,http://127.0.0.1:3000,*"
export ENABLE_FAILURE_SIMULATION="true"

# Start FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API endpoints will be accessible at `http://localhost:8000`:
- `GET /health`
- `POST /chat`
- `GET /sessions/{session_id}/messages`

#### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
The React frontend will be accessible at `http://localhost:3000`.

---

## 3. Design decisions: key fallback, caching, SQLite session storage

### Key Failover & Resilience
- **Key Pool Architecture:** Keys configured via `LLM_API_KEYS` are assigned sequential identifiers (`key_1`, `key_2`, ...). The gateway iterates through the pool in priority order.
- **Graceful Failover:** When a provider returns an HTTP 429 (rate limit), quota error, network timeout, or 5xx server error, the gateway records the failed attempt and seamlessly transitions to the next key. The user never experiences an unhandled exception or broken interface.
- **Clean Exhaustion Handling:** If every key in the pool is exhausted or unavailable, the backend immediately returns an HTTP 503 with body `{"detail": "all providers unavailable"}`.
- **Failover Simulation Hook (`X-Simulate-Failure`):** Supported on `POST /chat` when `ENABLE_FAILURE_SIMULATION=true`. Allows testing failover (e.g. `key_1=429`, `key_1=500`, or `*=429`) deterministically without exhausting production quotas. Failed requests are never saved to session history.

### Response Caching
- **Canonical Cache Key:** Computed as `SHA-256(model + full_messages_list)` where full message list incorporates the session's system prompt, prior conversation turns, and the new user message.
- **Sub-Millisecond Cache Hits:** When an identical prompt structure is submitted (even across different sessions), the cached reply and token count are returned instantly with `resolution_source: "LLM_CACHE"`, `key_id: null`, and `fallback_attempts: 0`.
- **Cache Invalidation & Miss Isolation:** Any divergence in history or prompt text generates a cache miss, proceeding directly to live inference.

### SQLite Session Storage
- **Isolated Per-Session History:** Multi-turn conversation context is stored strictly in SQLite per `session_id`, using the minimal schema specified in the assignment contract.
- **Persistent Volume:** In Docker, SQLite resides under `/data/app.db` via a named volume, ensuring message persistence across container lifecycles.
- **Stateless Client:** The client only sends the latest message; the server reconstructs prior context from SQLite.

---

## 4. Verification: how to see failover, cache hits and per-message token usage

### 1. Verification of Caching
1. Send a new message, e.g., `"What is the capital of France?"`.
   - The assistant replies with metadata: `meta-source: LIVE_INFERENCE`, `key_id: key_1`, `latency_ms: ~800ms`.
2. Refresh the page (generating a fresh `session_id`) and send the identical message `"What is the capital of France?"`.
   - The reply returns immediately with `meta-source: LLM_CACHE`, `key_id: null`, and `latency_ms: ~5ms` (significantly faster).

### 2. Verification of Key Failover (via `X-Simulate-Failure`)
In the UI, click **⚙️ Controls** to open the testing panel, or test via curl:

- **Fail Key 1 (Simulate Rate Limit 429):**
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: key_1=429" \
    -d '{"session_id": "demo-1", "message": "Hello failover"}'
  ```
  *Result:* Returns `HTTP 200`, `key_id: "key_2"`, `fallback_attempts: 1`.

- **Fail Key 1 (Simulate 500 Server Error):**
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: key_1=500" \
    -d '{"session_id": "demo-2", "message": "Hello server error failover"}'
  ```
  *Result:* Returns `HTTP 200`, `key_id: "key_2"`, `fallback_attempts: 1`.

- **Fail All Keys (`*=429`):**
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: *=429" \
    -d '{"session_id": "demo-3", "message": "All keys down"}'
  ```
  *Result:* Returns `HTTP 503 {"detail": "all providers unavailable"}`. Verified: nothing is written to SQLite history.

### 3. Verification of Per-Message Token Usage
- Every reply card clearly displays `meta-input-tokens` and `meta-output-tokens`.
- In a multi-turn chat, `input_tokens` increases in turn 2 to reflect the system prompt + turn 1 history + turn 2 message.
- Equal-length opening messages across different sessions report identical per-request token usage, never a cumulative session sum.

---

## 5. Setup Used: your editor and AI tools

- **Editor & IDE:** VS Code / Antigravity IDE
- **AI Tools:** Antigravity (Google DeepMind Gemini 3.8 Flash) for end-to-end architecture design, automated testing, and deployment scripts
- **Languages & Frameworks:** Python 3.10, FastAPI, LiteLLM, SQLite, React 18, Vite, Docker & Docker Compose

---

## 6. Bonus features (if any): what you added beyond the requirements and why

1. **Interactive In-UI Failover Control Suite:**
   - Added a collapsible **Controls** drawer in the header with one-click presets (`key_1=429`, `key_1=500`, `*=429`, Clear) so evaluators can test failover scenarios instantly without terminal commands.
2. **Real-time Backend Health Monitor:**
   - Visual status pill indicating real-time backend connectivity, number of configured API keys, and cache status directly from `GET /health`.
3. **Editable System Prompt Interface:**
   - Built the optional `system-prompt-input` field with `data-testid="system-prompt-input"` allowing users to customize agent persona per session.
4. **Resilient Visual Error Banners:**
   - Handled network errors and backend 422/503 errors with dedicated in-chat alert bubbles, ensuring the screen never blanks out or crashes.
5. **Comprehensive Automated Test Suite:**
   - 8 exhaustive pytest test cases covering health checks, cache hits, token consistency, failover headers, 404 session handling, and 422 schema validation.
