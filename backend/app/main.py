import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder

from app.config import (
    KEY_POOL,
    ALLOWED_ORIGINS,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_MODEL
)
from app.database import (
    init_db,
    check_db_health,
    save_message,
    get_session_messages
)
from app.schemas import (
    HealthResponse,
    ChatRequest,
    ChatResponse,
    ChatMetadata,
    SessionMessagesResponse,
    SessionMessageItem
)
from app.llm_service import generate_chat_reply

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized successfully.")
    yield

app = FastAPI(title="LLM Chatbot Gateway", version="1.0.0", lifespan=lifespan)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure standard JSON error shape
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

@app.get("/health", response_model=HealthResponse)
def health_check():
    db_ok = check_db_health()
    if not db_ok:
        raise HTTPException(status_code=500, detail="Database unreachable")
    
    return HealthResponse(
        status="ok",
        keys_configured=len(KEY_POOL),
        cache_enabled=True
    )

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure")
):
    session_id = req.session_id
    user_message = req.message
    system_prompt = req.system_prompt or DEFAULT_SYSTEM_PROMPT

    # 1. Fetch existing session history
    stored_messages = get_session_messages(session_id) or []

    # 2. Build full message list sent to LLM: system prompt + history + new user message
    llm_messages = [{"role": "system", "content": system_prompt}]
    for msg in stored_messages:
        llm_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    llm_messages.append({"role": "user", "content": user_message})

    # 3. Call LLM gateway (with caching and key failover)
    result = await generate_chat_reply(
        messages=llm_messages,
        model=DEFAULT_MODEL,
        simulate_header=x_simulate_failure
    )

    metadata_payload = {
        "resolution_source": result["resolution_source"],
        "model": result["model"],
        "latency_ms": result["latency_ms"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "key_id": result["key_id"],
        "fallback_attempts": result["fallback_attempts"]
    }

    # 4. Save to SQLite ONLY upon successful completion
    save_message(session_id, "user", user_message, metadata=None)
    save_message(
        session_id,
        "assistant",
        result["reply"],
        metadata={
            "resolution_source": result["resolution_source"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"]
        }
    )

    return ChatResponse(
        session_id=session_id,
        reply=result["reply"],
        metadata=ChatMetadata(**metadata_payload)
    )

@app.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
def get_session_history(session_id: str):
    history = get_session_messages(session_id)
    if history is None:
        raise HTTPException(status_code=404, detail="session not found")
    
    formatted_messages = [
        SessionMessageItem(
            role=item["role"],
            content=item["content"],
            metadata=item.get("metadata")
        )
        for item in history
    ]

    return SessionMessagesResponse(
        session_id=session_id,
        messages=formatted_messages
    )
