"""
vlm_provider.py
---------------
LiteLLM-backed VLM provider helpers.

The evaluator only needs one operation: send a screenshot plus prompt to a
vision-capable model and return the raw text response.
"""

import base64
import os
import re
import time
from pathlib import Path
from typing import Any

MAX_RETRIES_ENV_VAR = "VLM_MAX_RETRIES"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 0.5


def image_to_data_url(image_path: Path) -> str:
    """Convert a local PNG screenshot to a base64 data URL."""
    image_bytes = image_path.read_bytes()
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _completion(**kwargs: Any) -> Any:
    """Import LiteLLM lazily so non-evaluator imports do not require it."""
    try:
        from litellm import completion
    except ImportError as exc:
        raise RuntimeError(
            "litellm package not installed. Run: pip install litellm"
        ) from exc

    return completion(**kwargs)


def _resolve_max_retries(max_retries: int | None = None) -> int:
    """Resolve retry count from explicit argument or VLM_MAX_RETRIES."""
    if max_retries is not None:
        resolved = max_retries
    else:
        raw_retries = os.environ.get(MAX_RETRIES_ENV_VAR, "").strip()
        resolved = DEFAULT_MAX_RETRIES if not raw_retries else int(raw_retries)

    if resolved < 0:
        raise ValueError(f"{MAX_RETRIES_ENV_VAR} must be >= 0")

    return resolved


def _is_rate_limit_error(exc: Exception) -> bool:
    """Detect LiteLLM/provider rate-limit errors without importing LiteLLM eagerly."""
    class_name = exc.__class__.__name__.lower()
    if "ratelimit" in class_name or "rate_limit" in class_name or "overload" in class_name:
        return True

    status_code = getattr(exc, "status_code", None)
    if status_code in (429, 503):
        return True

    exc_str = str(exc).lower()
    return "rate limit" in exc_str or "try again" in exc_str or "later" in exc_str or "overload" in exc_str


def _retry_delay_seconds(exc: Exception, fallback: float) -> float:
    """Extract retry delay hints from provider errors, falling back to backoff."""
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        try:
            return max(float(retry_after), 0.0)
        except (TypeError, ValueError):
            pass

    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) if response is not None else {}
    header_retry_after = None
    if headers:
        header_retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if header_retry_after is not None:
        try:
            return max(float(header_retry_after), 0.0)
        except (TypeError, ValueError):
            pass

    message = str(exc)
    ms_match = re.search(r"(?:try again|retry) in\s+(\d+(?:\.\d+)?)\s*ms", message, re.I)
    if ms_match:
        return max(float(ms_match.group(1)) / 1000.0, 0.0)

    seconds_match = re.search(r"(?:try again|retry) in\s+(\d+(?:\.\d+)?)\s*s", message, re.I)
    if seconds_match:
        return max(float(seconds_match.group(1)), 0.0)

    return fallback


def _extract_response_text(response: Any) -> str:
    """Extract assistant text from LiteLLM's OpenAI-compatible response shape."""
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError):
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(str(part.get("text", "")))
        return "".join(text_parts)

    return "" if content is None else str(content)


def call_vlm(
    model: str,
    image_path: Path,
    prompt: str,
    max_retries: int | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    Send image + prompt to a LiteLLM vision model and return raw text.

    Model examples:
      - openai/gpt-4o-mini
      - gemini/gemini-2.5-flash
      - anthropic/claude-3-5-sonnet-latest
    """
    if model == "local/ferret-ui-llama8b":
        import urllib.request
        import urllib.error
        import json
        import re
        from PIL import Image
        
        # Rewrite prompt for Ferret-UI to trigger bounding box grounding.
        # The generic zero-shot prompt confuses Ferret, causing it to just repeat the text.
        target_match = re.search(r"click on the text element:\s*'([^']+)'", prompt)
        ferret_prompt = prompt
        if target_match:
            target_text = target_match.group(1)
            ferret_prompt = f"What is the bounding box of {target_text}?"
            
        data = {
            "image_path": str(image_path),
            "prompt": ferret_prompt
        }
        
        req = urllib.request.Request(
            "http://localhost:8000/", 
            data=json.dumps(data).encode('utf-8'), 
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                ferret_text = result.get('text', '')
                
                bbox_match = re.search(r'\[\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]\]', ferret_text)
                if bbox_match:
                    try:
                        with Image.open(image_path) as img:
                            w, h = img.size
                    except:
                        w, h = 1000, 1000 # Fallback
                        
                    x1, y1, x2, y2 = map(float, bbox_match.groups())
                    
                    # Convert from 1000-scale to absolute pixels and find center
                    cx = ((x1 + x2) / 2.0 / 1000.0) * w
                    cy = ((y1 + y2) / 2.0 / 1000.0) * h
                    
                    return f"[{cx:.1f}, {cy:.1f}]"
                
                return ferret_text
                
        except urllib.error.URLError as e:
            if isinstance(e.reason, ConnectionRefusedError):
                print("\n[ERROR] Could not connect to the Ferret-UI inference server!")
                print("Please start the server in a separate terminal:")
                print("  cd ferret_ui")
                print("  .\\venv\\Scripts\\activate")
                print("  python ferret_server.py")
                print("Wait for 'Model loaded successfully!' before running the evaluator.\n")
                raise SystemExit(1)
            else:
                print(f"Error communicating with local ferret model: {e}")
                raise e

    data_url = image_to_data_url(image_path)
    retries = _resolve_max_retries(max_retries)
    delay = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS

    for attempt in range(retries + 1):
        try:
            kwargs = dict(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                        ],
                    }
                ],
            )
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            response = _completion(**kwargs)
            return _extract_response_text(response)
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt >= retries:
                raise

            sleep_seconds = _retry_delay_seconds(exc, delay)
            print(
                f"    [RETRY] Rate limited; sleeping {sleep_seconds:.2f}s "
                f"before retry {attempt + 1}/{retries}"
            )
            time.sleep(sleep_seconds)
            delay = max(sleep_seconds * 2, DEFAULT_RATE_LIMIT_BACKOFF_SECONDS)

    raise RuntimeError("unreachable retry state")
