import { useEffect, useRef, useState } from "react";
import { api, isTerminalRunStatus } from "../lib/api";
import { RunTally } from "./run-monitor/RunTally";
const POLL_MS = 1200;
const RESULT =
  /^ {4}\[(HIT|MISS|OFF-SCREEN|OFF-FRAME|LABEL-CHANGED|API-ERROR)\]/;

function duration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}
export function RunMonitor({
  runId,
  command,
  expectedTotal,
  alreadyDone = 0,
  onFinish,
}: {
  runId: string;
  command?: string;
  expectedTotal?: number | null;
  alreadyDone?: number;
  onFinish?: (status: string) => void;
}) {
  const [status, setStatus] = useState("running");
  const [lines, setLines] = useState<string[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [cancelled, setCancelled] = useState(false);
  const [stick, setStick] = useState(true);
  const [startedAt] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);
  const log = useRef<HTMLPreElement>(null);
  const finished = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    let cursor = 0;
    let nextSince = 0;
    const ingest = (next: string[]) => {
      if (!next.length) return;
      setLines((old) => [...old, ...next]);
      setCounts((old) => {
        const result = { ...old };
        next.forEach((line) => {
          const key = line.match(RESULT)?.[1];
          if (key) result[key] = (result[key] || 0) + 1;
        });
        return result;
      });
      cursor += next.filter((line) => RESULT.test(line)).length;
    };
    const poll = async (): Promise<void> => {
      try {
        const snap = await api<{
          status: string;
          lines?: string[];
          next_since: number;
        }>(`/api/runs/${encodeURIComponent(runId)}?since=${nextSince}`, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        ingest(snap.lines || []);
        nextSince = snap.next_since;
        setStatus(snap.status);
        setElapsed((Date.now() - startedAt) / 1000);
        if (isTerminalRunStatus(snap.status)) {
          const tail = await api<{ lines?: string[]; next_since: number }>(
            `/api/runs/${encodeURIComponent(runId)}?since=${nextSince}`,
            { signal: controller.signal },
          ).catch(() => null);
          if (!controller.signal.aborted && tail?.lines?.length) {
            ingest(tail.lines);
            nextSince = tail.next_since;
          }
          if (!finished.current && !controller.signal.aborted) {
            finished.current = true;
            onFinish?.(snap.status);
          }
          return;
        }
        timer = window.setTimeout(() => void poll(), POLL_MS);
      } catch (error) {
        if (!controller.signal.aborted) {
          setStatus("failed");
          if (!finished.current) {
            finished.current = true;
            onFinish?.("failed");
          }
        }
      }
    };
    void poll();
    return () => {
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [runId, onFinish, startedAt]);
  useEffect(() => {
    if (stick && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [lines, stick]);
  const done = alreadyDone + Object.values(counts).reduce((a, b) => a + b, 0);
  const ratio = expectedTotal ? Math.min(1, done / expectedTotal) : 0;
  const timing = `${duration(elapsed)} elapsed${status === "running" && expectedTotal && done > alreadyDone ? ` -- about ${duration((elapsed / (done - alreadyDone)) * Math.max(0, expectedTotal - done))} left` : ""}`;
  const kind =
    status === "running" ? "warn" : status === "completed" ? "ok" : "err";
  return (
    <div className="card run-panel">
      <div className="run-header">
        <div className="run-header-top">
          <div className="run-title">
            <span id="run-badge">
              <span className={`badge ${kind}`}>{status}</span>
            </span>
            <span className="run-counts" id="run-counts">
              {expectedTotal
                ? `${done} / ${expectedTotal} queries (${Math.round(ratio * 100)}%)`
                : done
                  ? `${done} queries`
                  : ""}
            </span>
          </div>
          <div className="run-title">
            <span id="run-timing" className="run-timing">
              {timing}
            </span>
            <button
              type="button"
              className={`secondary small ${status !== "running" ? "hidden" : ""}`}
              id="run-cancel"
              disabled={cancelled}
              onClick={async () => {
                setCancelled(true);
                await api(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
                  method: "POST",
                }).catch(() => undefined);
              }}
            >
              Cancel run
            </button>
          </div>
        </div>
        <div
          className={`progress ${expectedTotal && status === "running" ? "" : expectedTotal ? "" : status === "running" ? "is-indeterminate" : ""}`}
          id="run-progress"
          role="progressbar"
          aria-label="Run progress"
          aria-valuemin={0}
          aria-valuemax={expectedTotal || undefined}
          aria-valuenow={expectedTotal ? done : undefined}
        >
          <div
            id="run-progress-fill"
            className="progress-fill"
            style={{
              width: expectedTotal
                ? `${(ratio * 100).toFixed(1)}%`
                : status !== "running"
                  ? "100%"
                  : undefined,
            }}
          />
        </div>
        <RunTally counts={counts} />
        <p id="run-live" className="sr-only" aria-live="polite">
          Run {status}. {done}
          {expectedTotal ? ` of ${expectedTotal}` : ""} queries done.
        </p>
      </div>
      <details className="run-log-wrap" id="run-log-details">
        <summary>Show raw log</summary>
        <pre
          id="run-log"
          ref={log}
          tabIndex={0}
          onScroll={(e) => {
            const el = e.currentTarget;
            setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 12);
          }}
        >
          {lines.join("\n")}
          {lines.length ? "\n" : ""}
        </pre>
        <p
          id="run-log-paused"
          className={stick ? "log-paused hidden" : "log-paused"}
        >
          Auto-scroll paused.{" "}
          <button
            type="button"
            className="ghost small"
            id="run-log-resume"
            onClick={() => {
              setStick(true);
              if (log.current) log.current.scrollTop = log.current.scrollHeight;
            }}
          >
            Jump to latest
          </button>
        </p>
      </details>
      {command && (
        <div className="run-log-wrap" style={{ paddingTop: 0 }}>
          <p className="command-label">Equivalent command</p>
          <div className="command-block">
            <code>{command}</code>
            <button
              type="button"
              className="secondary small"
              data-copy-run
              onClick={async (e) => {
                try {
                  await navigator.clipboard.writeText(command);
                  e.currentTarget.textContent = "Copied";
                  window.setTimeout(() => {
                    e.currentTarget.textContent = "Copy";
                  }, 1200);
                } catch {
                  e.currentTarget.textContent = "Select and copy";
                }
              }}
            >
              Copy
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
