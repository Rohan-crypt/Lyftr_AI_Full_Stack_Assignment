import os
import json
import time
import hashlib
import logging
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException
import litellm
from litellm.caching import Cache
from app.config import (
    KEY_POOL,
    DEFAULT_MODEL,
    ENABLE_FAILURE_SIMULATION
)

logger = logging.getLogger("llm_service")

# Enable LiteLLM built-in cache
try:
    litellm.cache = Cache(type="local")
except Exception as e:
    logger.warning(f"Could not initialize litellm Cache: {e}")

# In-memory fast cache to guarantee contract behavior:
# Cache key: model + full message list sent to LLM
# Returns identical reply, stored token usage, key_id=null, fallback_attempts=0
_response_cache: Dict[str, Dict[str, Any]] = {}

def get_cache_key(model: str, messages: List[Dict[str, str]]) -> str:
    canonical = json.dumps({"model": model, "messages": messages}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def parse_simulation_header(header_val: Optional[str]) -> Dict[str, int]:
    if not header_val or not header_val.strip():
        return {}
    res = {}
    parts = header_val.split(",")
    for part in parts:
        part = part.strip()
        if "=" in part:
            k, s = part.split("=", 1)
            k = k.strip()
            s = s.strip()
            if s.isdigit():
                res[k] = int(s)
    return res

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def calculate_prompt_tokens(messages: List[Dict[str, str]]) -> int:
    total_chars = sum(len(m.get("content", "")) + len(m.get("role", "")) for m in messages)
    return max(4, total_chars // 4)

async def generate_chat_reply(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    simulate_header: Optional[str] = None
) -> Dict[str, Any]:
    active_model = model or DEFAULT_MODEL
    cache_key = get_cache_key(active_model, messages)
    
    sim_map = {}
    if ENABLE_FAILURE_SIMULATION and simulate_header:
        sim_map = parse_simulation_header(simulate_header)

    start_time = time.perf_counter()

    # If no failure simulation header is active, check cache first
    # (Failure simulation on keys is intended to test provider key failover)
    if not sim_map and cache_key in _response_cache:
        cached = _response_cache[cache_key]
        latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        return {
            "reply": cached["reply"],
            "resolution_source": "LLM_CACHE",
            "model": active_model,
            "latency_ms": latency_ms,
            "input_tokens": cached["input_tokens"],
            "output_tokens": cached["output_tokens"],
            "key_id": None,
            "fallback_attempts": 0
        }

    fallback_attempts = 0
    last_error = None
    prompt_tokens = calculate_prompt_tokens(messages)

    for key_id, api_key in KEY_POOL:
        # Check if failure simulation applies to this key
        sim_status = sim_map.get("*") or sim_map.get(key_id)
        if sim_status:
            logger.info(f"Simulating failure {sim_status} for {key_id}")
            fallback_attempts += 1
            last_error = f"Simulated HTTP {sim_status}"
            continue

        try:
            # Check for dummy or real keys
            if api_key.startswith("dummy_") or api_key.startswith("mock_"):
                # Deterministic simulation for test/mock keys
                completion_tokens = 12
                reply_text = f"Response from {active_model} using {key_id}."
            else:
                resp = await litellm.acompletion(
                    model=active_model,
                    messages=messages,
                    api_key=api_key,
                    timeout=20
                )
                reply_text = resp.choices[0].message.content or ""
                if hasattr(resp, "usage") and resp.usage:
                    prompt_tokens = getattr(resp.usage, "prompt_tokens", prompt_tokens) or prompt_tokens
                    completion_tokens = getattr(resp.usage, "completion_tokens", estimate_tokens(reply_text)) or estimate_tokens(reply_text)
                else:
                    completion_tokens = estimate_tokens(reply_text)

            latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))

            # Store in cache
            _response_cache[cache_key] = {
                "reply": reply_text,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens
            }

            return {
                "reply": reply_text,
                "resolution_source": "LIVE_INFERENCE",
                "model": active_model,
                "latency_ms": latency_ms,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "key_id": key_id,
                "fallback_attempts": fallback_attempts
            }

        except Exception as e:
            logger.warning(f"Key {key_id} failed: {e}")
            fallback_attempts += 1
            last_error = str(e)
            continue

    # Every key failed
    logger.error(f"All keys failed. Last error: {last_error}")
    raise HTTPException(status_code=503, detail="all providers unavailable")
