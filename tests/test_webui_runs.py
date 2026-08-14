import os
import subprocess
import threading
import time
import unittest
from unittest import mock

from webui.backend.services import runs as runs_mod


class RunTailTests(unittest.TestCase):
    def test_tail_returns_only_new_lines_and_advances_since(self):
        run = runs_mod.Run(id="x", command=[], env_summary={}, started_at=0.0)
        run.append_line("line 1")
        run.append_line("line 2")

        first_batch, next_since = run.tail(0)
        self.assertEqual(["line 1", "line 2"], first_batch)
        self.assertEqual(2, next_since)

        run.append_line("line 3")
        second_batch, next_since2 = run.tail(next_since)
        self.assertEqual(["line 3"], second_batch)
        self.assertEqual(3, next_since2)

    def test_tail_with_no_new_lines_is_empty(self):
        run = runs_mod.Run(id="x", command=[], env_summary={}, started_at=0.0)
        run.append_line("only line")
        _batch, next_since = run.tail(0)

        empty_batch, unchanged_since = run.tail(next_since)
        self.assertEqual([], empty_batch)
        self.assertEqual(next_since, unchanged_since)


class StartRunLifecycleTests(unittest.TestCase):
    def test_extract_with_no_args_reaches_failed_status_with_exit_code_one(self):
        # `agb extract` with no xml_path prints a usage line and exits 1 --
        # deterministic, instantaneous, and touches no dataset files, so it
        # is a safe real subprocess to exercise the full lifecycle against.
        run = runs_mod.start_run(
            "extract", [], extra_env={}, env_summary={},
        )
        deadline = time.monotonic() + 15
        while run.status == runs_mod.STATUS_RUNNING and time.monotonic() < deadline:
            time.sleep(0.1)

        self.assertEqual(runs_mod.STATUS_FAILED, run.status)
        self.assertEqual(1, run.exit_code)
        lines, _ = run.tail(0)
        self.assertTrue(any("Usage:" in line for line in lines))

    def test_get_run_and_list_runs_reflect_started_run(self):
        run = runs_mod.start_run("extract", [], extra_env={}, env_summary={})
        self.assertIs(run, runs_mod.get_run(run.id))
        self.assertIn(run.id, [r.id for r in runs_mod.list_runs()])

        deadline = time.monotonic() + 15
        while run.status == runs_mod.STATUS_RUNNING and time.monotonic() < deadline:
            time.sleep(0.1)


class CancelRunTests(unittest.TestCase):
    def test_cancel_unknown_run_id_returns_false(self):
        self.assertFalse(runs_mod.cancel_run("not-a-real-run-id"))

    def test_cancel_already_finished_run_returns_false(self):
        run = runs_mod.start_run("extract", [], extra_env={}, env_summary={})
        deadline = time.monotonic() + 15
        while run.status == runs_mod.STATUS_RUNNING and time.monotonic() < deadline:
            time.sleep(0.1)

        self.assertFalse(runs_mod.cancel_run(run.id))

    def test_cancel_running_process_terminates_it_and_sets_cancelled_status(self):
        # A real pipe with the write end held open blocks the reader
        # thread's `for line in stdout` exactly like a live subprocess with
        # output still pending -- an empty StringIO would hit EOF instantly
        # and not exercise the "still running" path at all.
        read_fd, write_fd = os.pipe()

        class FakeProcess:
            def __init__(self):
                self.stdout = os.fdopen(read_fd, "r")
                self._terminated = threading.Event()

            def terminate(self):
                self._terminated.set()
                os.close(write_fd)  # EOF unblocks the reader thread

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                if self._terminated.wait(timeout):
                    return 0
                raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)

        fake_process = FakeProcess()
        with mock.patch.object(runs_mod.subprocess, "Popen", return_value=fake_process):
            run = runs_mod.start_run("evaluate", [], extra_env={}, env_summary={})

        time.sleep(0.1)  # let the reader thread reach its blocking read
        self.assertEqual(runs_mod.STATUS_RUNNING, run.status)

        ok = runs_mod.cancel_run(run.id)
        self.assertTrue(ok)
        self.assertTrue(fake_process._terminated.is_set())

        deadline = time.monotonic() + 5
        while run.exit_code is None and time.monotonic() < deadline:
            time.sleep(0.05)
        # Cancellation wins even though the reader thread observes a clean
        # (0) exit_code after EOF -- see _reader_thread's status guard.
        self.assertEqual(runs_mod.STATUS_CANCELLED, run.status)
        self.assertEqual(0, run.exit_code)


if __name__ == "__main__":
    unittest.main()
