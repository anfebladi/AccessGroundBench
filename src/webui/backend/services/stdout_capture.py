"""Concurrency-safe capture of process-global standard output."""

from __future__ import annotations

import contextlib
import io
import threading
from collections.abc import Iterator


_stdout_capture_lock = threading.RLock()


@contextlib.contextmanager
def capture_stdout(buffer: io.TextIOBase | None = None) -> Iterator[io.TextIOBase]:
    """Capture stdout while serializing access to the process-global stream.

    ``sys.stdout`` is process-global, so concurrent web requests cannot safely
    redirect it independently. The lock remains held for the entire context,
    preventing one request from restoring stdout while another is still
    writing. A caller may provide a buffer when it needs the captured output.
    """
    target = buffer if buffer is not None else io.StringIO()
    with _stdout_capture_lock:
        with contextlib.redirect_stdout(target):
            yield target
