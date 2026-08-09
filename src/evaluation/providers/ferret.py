"""Local Ferret-UI prompt, HTTP transport, and response conversion."""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import FERRET_MODEL_ID
from .coord_prompting import extract_target_from_prompt, resolve_image_dims
from .retry import (
    DEFAULT_RATE_LIMIT_BACKOFF_SECONDS,
    REQUEST_TIMEOUT_ENV_VAR,
    is_retryable_error,
    resolve_max_retries,
    resolve_request_timeout,
)

FERRET_SERVER_URL = "http://localhost:8000/"
FERRET_VOCAB_SIZE = 1000
FERRET_REQUEST_TIMEOUT_SECONDS = 1800.0
_FERRET_DOUBLE_BRACKET_RE = re.compile(
    r"\[\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,"
    r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]\]"
)
_FERRET_SINGLE_BRACKET_RE = re.compile(
    r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,"
    r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]"
)

def _sanitize_for_ferret(text: str) -> str:
    """
    Strip characters that would confuse ferret_server.py's prompt parsing.

    ferret_server.py:40-41 does `if "<image>" in qs: qs = qs.split('\\n')[1]`,
    so a UI label containing that literal token would silently shred the
    prompt down to a single line. Newlines are flattened too, so a tree row
    label can never masquerade as that split point.
    """
    return text.replace("<image>", "").replace("\n", " ").replace("\r", " ")


def build_ferret_prompt(
    target_text: str,
    tree_rows: list[tuple[str, list[int]]] | None,
    img_width: int,
    img_height: int,
) -> str:
    """Build the prompt Ferret-UI expects.

    Vision mode (tree_rows falsy) returns exactly the fine-tuned grounding
    line Ferret was trained on. Tree mode prepends nearby elements before it.
    """
    grounding_line = f"Provide the bounding box of the text '{_sanitize_for_ferret(target_text)}'."
    if not tree_rows:
        return grounding_line

    # Tree rows are scaled to Ferret's own 0-1000 "vocabulary" coordinate
    # space (see FERRET_VOCAB_SIZE), formatted the way
    # ferret_ui/model_UI.py:126-140 formats an input box: single bracket,
    # comma-space, `int()`-truncated (not rounded) after scaling -- matching
    # ferret_ui/model_UI.py:131,136 exactly. The grounding line always comes
    # last, since Ferret's fine-tuning expects the instruction to be the
    # final thing it reads.
    ratio_w = FERRET_VOCAB_SIZE / img_width
    ratio_h = FERRET_VOCAB_SIZE / img_height
    lines = []
    for label, box in tree_rows:
        x1, y1, x2, y2 = box
        vx1, vy1 = int(x1 * ratio_w), int(y1 * ratio_h)
        vx2, vy2 = int(x2 * ratio_w), int(y2 * ratio_h)
        lines.append(
            f'"{_sanitize_for_ferret(label)}" [{vx1}, {vy1}, {vx2}, {vy2}]'
        )

    return "Nearby elements:\n" + "\n".join(lines) + "\n\n" + grounding_line


def parse_ferret_bbox(ferret_text: str) -> tuple[float, float, float, float] | None:
    """
    Extract an [x1, y1, x2, y2] box from a Ferret-UI reply.

    Prefers the anchored double-bracket [[...]] form the model is fine-tuned
    to emit. Falls back to the LAST single-bracket 4-tuple (int or float) in
    the reply -- "last" matters once the prompt itself can contain bracketed
    boxes (the injected tree) that the model might echo back before its
    actual answer.
    """
    match = _FERRET_DOUBLE_BRACKET_RE.search(ferret_text)
    if match:
        return tuple(float(v) for v in match.groups())

    matches = _FERRET_SINGLE_BRACKET_RE.findall(ferret_text)
    if matches:
        return tuple(float(v) for v in matches[-1])

    return None


def call_ferret(
    image_path: Path,
    prompt: str,
    target_text: str | None,
    tree_rows: list[tuple[str, list[int]]] | None,
    img_width: int | None,
    img_height: int | None,
    max_retries: int | None,
    request_timeout: float | None,
) -> str:
    """Send a request to the local Ferret-UI inference server."""
    resolved_target = target_text
    if resolved_target is None:
        # Fallback for callers that don't pass structured target_text.
        resolved_target = extract_target_from_prompt(prompt)
        if resolved_target is not None:
            print(
                "    [WARN] call_vlm invoked for Ferret-UI without "
                "target_text; falling back to regex extraction from the "
                "prompt string."
            )

    w, h = resolve_image_dims(image_path, img_width, img_height)

    if resolved_target is None:
        # No target could be determined at all; send the raw prompt through
        # rather than fabricate a grounding line (this will confuse Ferret,
        # but that is a caller bug this fallback cannot repair).
        ferret_prompt = prompt
    else:
        ferret_prompt = build_ferret_prompt(resolved_target, tree_rows, w, h)

    data = {
        "image_path": str(image_path),
        "prompt": ferret_prompt,
    }
    body = json.dumps(data).encode("utf-8")

    retries = resolve_max_retries(max_retries)
    timeout = resolve_request_timeout(request_timeout, default=FERRET_REQUEST_TIMEOUT_SECONDS)
    delay = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS

    attempt = 0
    while True:
        req = urllib.request.Request(
            FERRET_SERVER_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", "")
            except Exception:
                detail = ""
            raise RuntimeError(
                f"Ferret-UI server rejected the request (HTTP {e.code}): {detail}"
            ) from e
        except TimeoutError as e:
            # Raised directly by urlopen on a read timeout, not wrapped in
            # URLError, so it needs its own clause. Not retried: the server
            # is still generating for this same request, so a retry would
            # queue behind it and time out again rather than making progress.
            raise RuntimeError(
                f"Ferret-UI request exceeded the {timeout:.0f}s timeout "
                f"({REQUEST_TIMEOUT_ENV_VAR}). The server is likely still "
                "generating a reply for a long target string, not down; "
                "raise the timeout rather than retrying."
            ) from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, ConnectionRefusedError):
                if attempt < retries:
                    # A single-threaded server with a full listen backlog
                    # refuses new connections while busy; that looks
                    # identical to "not running" but resolves once the
                    # in-flight request finishes, so it is worth retrying
                    # before concluding the server is actually down.
                    sleep_seconds = delay
                    print(
                        f"    [RETRY] Ferret-UI server refused the connection "
                        f"(likely busy); sleeping {sleep_seconds:.2f}s before "
                        f"retry {attempt + 1}/{retries}"
                    )
                    time.sleep(sleep_seconds)
                    delay = max(delay * 2, DEFAULT_RATE_LIMIT_BACKOFF_SECONDS)
                    attempt += 1
                    continue
                print("\n[ERROR] Could not connect to the Ferret-UI inference server!")
                print("Please start the server in a separate terminal:")
                print("  cd ferret_ui")
                print("  .\\venv\\Scripts\\activate")
                print("  python ferret_server.py")
                print("Wait for 'Model loaded successfully!' before running the evaluator.\n")
                raise SystemExit(1)
            if is_retryable_error(e) and attempt < retries:
                sleep_seconds = delay
                print(
                    f"    [RETRY] Ferret-UI request failed; sleeping "
                    f"{sleep_seconds:.2f}s before retry {attempt + 1}/{retries}"
                )
                time.sleep(sleep_seconds)
                delay = max(delay * 2, DEFAULT_RATE_LIMIT_BACKOFF_SECONDS)
                attempt += 1
                continue
            print(f"Error communicating with local ferret model: {e}")
            raise e
        break

    ferret_text = result.get("text", "")
    bbox = parse_ferret_bbox(ferret_text)
    if bbox is None:
        return ferret_text

    x1, y1, x2, y2 = bbox
    # Convert from Ferret's 0-1000 vocabulary scale to absolute pixels.
    cx = ((x1 + x2) / 2.0 / FERRET_VOCAB_SIZE) * w
    cy = ((y1 + y2) / 2.0 / FERRET_VOCAB_SIZE) * h
    return f"[{cx:.1f}, {cy:.1f}]"
