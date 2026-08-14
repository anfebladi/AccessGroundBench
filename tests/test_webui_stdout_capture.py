"""Concurrency regression tests for the Web UI stdout capture helper."""

from __future__ import annotations

import io
import threading
import unittest
from contextlib import redirect_stdout

from webui.backend.stdout_capture import capture_stdout


class StdoutCaptureTests(unittest.TestCase):
    def test_concurrent_captures_do_not_leak_to_outer_stdout(self) -> None:
        """Each request keeps its report in its own buffer when requests overlap."""

        outer = io.StringIO()
        first_active = threading.Event()
        second_attempted = threading.Event()
        release_first = threading.Event()
        first_done = threading.Event()
        start = threading.Barrier(2)
        captured: dict[str, str] = {}
        failures: list[BaseException] = []

        def first_request() -> None:
            try:
                start.wait()
                with capture_stdout() as buffer:
                    print("first-before")
                    first_active.set()
                    if not release_first.wait(timeout=2):
                        raise AssertionError("first request was not released")
                    print("first-after")
                captured["first"] = buffer.getvalue()
                first_done.set()
            except BaseException as exc:  # pragma: no cover - surfaced below
                failures.append(exc)
                first_done.set()

        def second_request() -> None:
            try:
                start.wait()
                if not first_active.wait(timeout=2):
                    raise AssertionError("first request did not start")
                second_attempted.set()
                with capture_stdout() as buffer:
                    print("second-before")
                    if not first_done.wait(timeout=2):
                        raise AssertionError("first request did not finish")
                    print("second-after")
                captured["second"] = buffer.getvalue()
            except BaseException as exc:  # pragma: no cover - surfaced below
                failures.append(exc)

        with redirect_stdout(outer):
            first = threading.Thread(target=first_request)
            second = threading.Thread(target=second_request)
            first.start()
            second.start()

            self.assertTrue(first_active.wait(timeout=2))
            self.assertTrue(second_attempted.wait(timeout=2))
            release_first.set()

            first.join(timeout=2)
            second.join(timeout=2)

        self.assertFalse(first.is_alive(), "first request thread did not finish")
        self.assertFalse(second.is_alive(), "second request thread did not finish")
        self.assertEqual([], failures)
        self.assertEqual("first-before\nfirst-after\n", captured["first"])
        self.assertEqual("second-before\nsecond-after\n", captured["second"])
        self.assertEqual("", outer.getvalue())

    def test_supplied_buffer_is_reused_and_yielded(self) -> None:
        supplied = io.StringIO("existing\n")
        supplied.seek(0, io.SEEK_END)

        with capture_stdout(supplied) as yielded:
            self.assertIs(yielded, supplied)
            print("captured")

        self.assertEqual("existing\ncaptured\n", supplied.getvalue())


if __name__ == "__main__":
    unittest.main()
