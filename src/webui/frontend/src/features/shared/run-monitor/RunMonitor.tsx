import { useEffect, useRef, useState } from "react";
import { api, isTerminalRunStatus } from "../../../lib/api";
import { RunTally } from "./RunTally";
import { Button } from "../../../components/ui/button";
import { Badge } from "../../../components/ui/badge";
import { Card } from "../../../components/ui/card";
import { Progress } from "../../../components/ui/progress";
import {
  Collapsible,
  CollapsibleContent,
  DisclosureTrigger,
} from "../../../components/ui/collapsible";
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
  const remaining =
    status === "running" && expectedTotal && done > alreadyDone
      ? ` -- about ${duration(
          (elapsed / (done - alreadyDone)) * Math.max(0, expectedTotal - done),
        )} left`
      : "";
  const timing = `${duration(elapsed)} elapsed${remaining}`;
  const kind =
    status === "running" ? "warn" : status === "completed" ? "ok" : "err";
  return (
    <Card className="min-w-0 p-0">
      <div className="sticky top-[var(--space-2)] z-[5] rounded-t-[var(--radius-lg)] border-b border-[var(--border)] bg-[var(--surface)] p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span id="run-badge">
              <Badge
                className={
                  kind === "ok"
                    ? "text-[var(--ok)]"
                    : kind === "err"
                      ? "text-[var(--err)]"
                      : "text-[var(--warn)]"
                }
              >
                {status}
              </Badge>
            </span>
            <span id="run-counts" className="font-mono text-xl font-medium tabular-nums">
              {expectedTotal
                ? `${done} / ${expectedTotal} queries (${Math.round(ratio * 100)}%)`
                : done
                  ? `${done} queries`
                  : ""}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span id="run-timing" className="font-mono text-xs tabular-nums text-[var(--muted)]">{timing}</span>
            <Button
              type="button"
              className={`text-sm ${status !== "running" ? "hidden" : ""}`}
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
            </Button>
          </div>
        </div>
        <Progress
          className={`h-1.5 overflow-hidden rounded-full bg-[var(--surface-3)] [&>div]:h-full [&>div]:rounded-full [&>div]:bg-[var(--primary)] ${
            expectedTotal && status === "running"
              ? ""
              : expectedTotal
                ? ""
                : status === "running"
                  ? "is-indeterminate"
                  : ""
          }`}
          id="run-progress"
          role="progressbar"
          aria-label="Run progress"
          aria-valuemin={0}
          aria-valuemax={expectedTotal || undefined}
          aria-valuenow={expectedTotal ? done : undefined}
          value={expectedTotal ? done : status !== "running" ? 100 : 0}
        />
        <div id="run-progress-fill" className="sr-only" aria-hidden="true" />
        <RunTally counts={counts} />
        <p id="run-live" className="sr-only" aria-live="polite">
          Run {status}. {done}
          {expectedTotal ? ` of ${expectedTotal}` : ""} queries done.
        </p>
      </div>
      <Collapsible className="p-4" id="run-log-details">
        <DisclosureTrigger className="min-h-8 w-fit">Show raw log</DisclosureTrigger>
        <CollapsibleContent>
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
            className={stick ? "hidden" : "mt-2 text-xs text-[var(--warn)]"}
          >
            Auto-scroll paused.{" "}
            <Button
              type="button"
              className="text-sm"
              id="run-log-resume"
              onClick={() => {
                setStick(true);
                if (log.current) log.current.scrollTop = log.current.scrollHeight;
              }}
            >
              Jump to latest
            </Button>
          </p>
        </CollapsibleContent>
      </Collapsible>
      {command && (
        <div style={{ paddingTop: 0 }}>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Equivalent command
          </p>
          <div className="flex items-center justify-between gap-3 rounded-[var(--radius-md)] bg-[var(--surface-2)] p-3 font-mono text-xs">
            <code>{command}</code>
            <Button
              type="button"
              className="text-sm"
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
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
