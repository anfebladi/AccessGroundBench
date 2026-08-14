import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, enc, imageUrl } from "../../lib/api";
import { drawScreenshot, strokeWidthFor } from "../../lib/canvas";
import { ExportButton } from "../shared/reporting/components/ExportButton";
import type { TabViewProps } from "../../lib/types";
import { AccuracyChart } from "../shared/reporting/charts";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { LoadingState } from "../../components/ui/spinner";
import { Badge as UiBadge } from "../../components/ui/badge";
import { Checkbox } from "../../components/ui/checkbox";
import { SegmentedButton, SegmentedGroup } from "../../components/ui/segmented";
import { Alert, AlertDescription, AlertIcon, AlertTitle } from "../../components/ui/alert";
import { StageHeader } from "../shared/StageHeader";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../../components/ui/table";

type Result = {
  filename: string;
  model: string;
  prompt_mode: string;
  row_count: number;
  statuses: Record<string, number>;
  hits: number;
  co_present_count: number;
  accuracy: number | null;
  baseline_accuracy: number | null;
};
type CsvRow = Record<string, string | number | null | undefined>;
type Analysis = {
  available?: boolean;
  output_dir?: string;
  reachability: CsvRow[];
  pooled_permutation: CsvRow[];
  mcnemar_per_model: CsvRow[];
  direction_consistency: CsvRow[];
};
const text = (value: unknown) => String(value ?? "");
const number = (value: unknown) => {
  const n = Number(String(value ?? "").replace("%", ""));
  return Number.isFinite(n) ? n : NaN;
};
function Badge({
  className,
  children,
}: {
  className: string;
  children: React.ReactNode;
}) {
  return <UiBadge className={className}>{children}</UiBadge>;
}
function ErrorState({ message }: { message: string }) {
  return (
    <Alert variant="danger">
      <AlertTitle>
        <AlertIcon variant="danger" />
        Couldn't load results
      </AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}
const STATUS_COLUMNS: [string, string, string][] = [
  [
    "off_screen",
    "Off-screen",
    "Target absent from this profile; never queried.",
  ],
  [
    "label_changed",
    "Label changed",
    "Target text renders differently on this profile.",
  ],
  ["off_frame", "Off-frame", "Box centre falls outside the cropped image."],
  ["api_error", "API error", "The provider call failed after retries."],
];
function NotScored({ statuses }: { statuses: Record<string, number> }) {
  const parts = STATUS_COLUMNS.filter(([key]) => (statuses?.[key] || 0) > 0);
  if (!parts.length) return <span className="text-[var(--muted)]">--</span>;
  return (
    <div className="tally mt-0 flex flex-wrap gap-2">
      {parts.map(([key, label, hint]) =>
        key === "api_error" ? (
          <Badge className="err" key={key}>
            {statuses[key]} API errors
          </Badge>
        ) : (
          <span className="tally-item inline-flex items-baseline gap-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 text-xs" title={hint} key={key}>
            <b>{statuses[key]}</b> {label}
          </span>
        ),
      )}
    </div>
  );
}
function AccuracyCell({ row }: { row: Result }) {
  if (row.accuracy == null) return <span className="text-[var(--muted)]">--</span>;
  return (
    <div className="bar-cell">
      <span className="bar-track">
        <span
          className="bar-fill"
          style={{ width: `${(row.accuracy * 100).toFixed(1)}%` }}
        />
      </span>
      <span className="bar-value">{(row.accuracy * 100).toFixed(1)}%</span>
      <span className="bar-fraction">
        {row.hits} / {row.co_present_count}
      </span>
    </div>
  );
}

export function ResultsView({
  dataset,
  onCountChange,
  hidden,
}: TabViewProps & {
  dataset: string;
  onCountChange?: (count: number) => void;
}) {
  const [rows, setRows] = useState<Result[]>([]),
    [mode, setMode] = useState("all"),
    [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" }>({
      key: "accuracy",
      dir: "desc",
    }),
    [selected, setSelected] = useState<Set<string>>(new Set()),
    [inspect, setInspect] = useState<{
      filename: string;
      model: string;
    } | null>(null),
    [error, setError] = useState("");
  const [resultsLoading, setResultsLoading] = useState(false);
  useEffect(() => {
    let active = true;
    if (!dataset) { setRows([]); return; }
    setResultsLoading(true);
    setRows([]);
    setError("");
    api<Result[]>(`/api/datasets/${enc(dataset)}/results`)
      .then((value) => active && setRows(value))
      .catch(
        (e) =>
          active &&
          (setRows([]), setError(e instanceof Error ? e.message : String(e))),
      )
      .finally(() => active && setResultsLoading(false));
    return () => {
      active = false;
    };
  }, [dataset]);
  useEffect(() => {
    onCountChange?.(rows.length);
  }, [rows.length, onCountChange]);
  const modes = useMemo(
    () => [...new Set(rows.map((row) => row.prompt_mode).filter(Boolean))],
    [rows],
  );
  const visible = useMemo(
    () =>
      rows
        .filter((row) => mode === "all" || row.prompt_mode === mode)
        .sort((a, b) => {
          const av = a[sort.key as keyof Result],
            bv = b[sort.key as keyof Result];
          const cmp =
            typeof av === "string" || typeof bv === "string"
              ? text(av).localeCompare(text(bv))
              : Number(av ?? -1) - Number(bv ?? -1);
          return sort.dir === "asc" ? cmp : -cmp;
        }),
    [rows, mode, sort],
  );
  const selectedRows = visible.filter((row) => selected.has(row.filename));
  const showModeInLabels = mode === "all" && modes.length > 1;
  const chartLabel = (row: Result) =>
    showModeInLabels && row.prompt_mode
      ? `${row.model} (${row.prompt_mode})`
      : row.model;
  const toggle = (filename: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  const sortBy = (key: string) =>
    setSort((current) => ({
      key,
      dir: current.key === key && current.dir === "desc" ? "asc" : "desc",
    }));
  return (
    <section
      id="tab-results"
      className="tab min-w-0"
      aria-labelledby="head-results"
      hidden={hidden}
    >
      <StageHeader stage="results" title="Results">
        Per-model accuracy over the targets present on both profiles.
      </StageHeader>
      <Card className="rounded-[var(--radius-lg)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3>Evaluated models</h3>
          <div id="results-mode-filter">
            {modes.length > 1 && (
              <SegmentedGroup aria-label="Prompt mode filter">
                <SegmentedButton
                  data-mode="all"
                  pressed={mode === "all"}
                  onClick={() => setMode("all")}
                >
                  All
                </SegmentedButton>
                {modes.map((value) => (
                  <SegmentedButton
                    data-mode={value}
                    pressed={mode === value}
                    onClick={() => setMode(value)}
                    key={value}
                  >
                    {value}
                  </SegmentedButton>
                ))}
              </SegmentedGroup>
            )}
          </div>
        </div>
        <div id="results-body">
          {error ? (
            <ErrorState message={error} />
          ) : resultsLoading ? (
            <LoadingState label="Loading evaluation results…" />
          ) : !rows.length ? (
            <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border)] p-6 text-center">
              <h3>No evaluations yet</h3>
              <p>
                Result files appear here once a model has been evaluated against
                this dataset.
              </p>
              <Button asChild><a href="#evaluate">Go to Evaluate</a></Button>
            </div>
          ) : (
            <>
              {modes.length > 1 && (
                <Alert variant="neutral" className="mb-4">
                  <AlertTitle>
                    <AlertIcon variant="neutral" />
                    Vision and tree are never pooled
                  </AlertTitle>
                  <AlertDescription>
                    They answer different research questions. Analyze runs one
                    arm at a time.
                  </AlertDescription>
                </Alert>
              )}
              {visible.some((row) => row.accuracy != null) && (
                <Card id="results-overall-accuracy">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3>Overall accuracy</h3>
                      <p className="text-sm text-[var(--muted)]">
                        Blended across every profile, co-present targets only.
                        The exact figures and the baseline-only breakdown are in
                        the table below.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <ExportButton name="results-overall-accuracy" targetId="results-overall-accuracy" />
                    </div>
                  </div>
                  <div className="mb-4 flex items-baseline gap-2">
                    <span
                      className="font-display font-semibold tabular-nums text-[var(--text)]"
                      style={{ fontSize: "var(--text-stat)", lineHeight: "var(--lh-stat)", letterSpacing: "var(--ls-stat)" }}
                    >
                      {(
                        (visible
                          .filter((row) => row.accuracy != null)
                          .reduce((sum, row) => sum + (row.accuracy ?? 0), 0) /
                          Math.max(1, visible.filter((row) => row.accuracy != null).length)) *
                        100
                      ).toFixed(1)}
                      %
                    </span>
                    <span className="text-xs font-medium uppercase tracking-[var(--ls-xs)] text-[var(--muted)]">
                      Average across evaluated models
                    </span>
                  </div>
                  <div className="chart-draw-in">
                    <AccuracyChart
                      rows={visible
                        .filter((row) => row.accuracy != null)
                        .sort((a, b) => (b.accuracy || 0) - (a.accuracy || 0))
                        .map((row) => ({
                          id: row.filename,
                          label: chartLabel(row),
                          value: row.accuracy ?? 0,
                        }))}
                    />
                  </div>
                </Card>
              )}
              {selectedRows.length >= 2 && (
                <Card id="results-selected-comparison">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3>Comparing {selectedRows.length} selected models</h3>
                      <p className="text-sm text-[var(--muted)]">
                        Same accuracy figures as the table below, isolated for a
                        direct look.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <ExportButton name="results-selected-comparison" targetId="results-selected-comparison" />
                      <Button
                        type="button"
                        className="text-sm"
                        id="results-compare-clear"
                        onClick={() => setSelected(new Set())}
                      >
                        Clear selection
                      </Button>
                    </div>
                  </div>
                  <div className="chart-dark rounded-[var(--radius-lg)] bg-[var(--surface-dark,var(--surface))] p-2 text-[var(--on-dark-muted)]">
                    <AccuracyChart
                      tone="dark"
                      rows={selectedRows
                        .filter((row) => row.accuracy != null)
                        .map((row) => ({
                          id: row.filename,
                          label: chartLabel(row),
                          value: row.accuracy ?? 0,
                        }))}
                    />
                  </div>
                </Card>
              )}
              <div className="table-stack min-w-0">
                <div className="overflow-x-auto">
                  <Table id="results-table">
                    <TableHeader>
                      <TableRow>
                        <TableHead
                          className="num"
                          title="Check models to compare them side by side"
                        >
                          Compare
                        </TableHead>
                        {[
                          ["model", "Model"],
                          ["prompt_mode", "Mode"],
                          ["row_count", "Rows"],
                          ["accuracy", "Accuracy"],
                        ].map(([key, label]) => (
                          <TableHead
                            key={key}
                            className="sortable cursor-pointer"
                            data-sort={key}
                            aria-sort={
                              sort.key === key
                                ? sort.dir === "asc"
                                  ? "ascending"
                                  : "descending"
                                : "none"
                            }
                            onClick={() => sortBy(key)}
                          >
                            {label}
                          </TableHead>
                        ))}
                        <TableHead title="Blended accuracy compared with baseline-only accuracy">
                          vs. baseline
                        </TableHead>
                        <TableHead title="Rows excluded from the accuracy denominator, by CSV status">
                          Not scored
                        </TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {visible.map((row) => (
                        <TableRow key={row.filename}>
                          <TableCell className="num" data-label="Compare">
                            <Checkbox
                              data-compare-select={row.filename}
                              checked={selected.has(row.filename)}
                              onCheckedChange={() => toggle(row.filename)}
                              aria-label={`Compare ${row.model} (${row.prompt_mode})`}
                            />
                          </TableCell>
                          <TableCell data-label="Model">
                            <b>{row.model}</b>
                          </TableCell>
                          <TableCell data-label="Mode">
                            {row.prompt_mode || (
                              <span className="text-[var(--muted)]">--</span>
                            )}
                          </TableCell>
                          <TableCell className="num" data-label="Rows">
                            {row.row_count}
                          </TableCell>
                          <TableCell data-label="Accuracy">
                            <AccuracyCell row={row} />
                          </TableCell>
                          <TableCell data-label="vs. baseline">
                            {row.accuracy == null ||
                            row.baseline_accuracy == null ? (
                              <span className="text-[var(--muted)]">--</span>
                            ) : (
                              `${((row.baseline_accuracy - row.accuracy) * 100).toFixed(1)} pts`
                            )}
                          </TableCell>
                          <TableCell data-label="Not scored">
                            <NotScored statuses={row.statuses || {}} />
                          </TableCell>
                          <TableCell data-label="" style={{ textAlign: "right" }}>
                            <Button
                              type="button"
                              className="text-sm"
                              data-inspect={row.filename}
                              data-model={row.model}
                              onClick={() =>
                                setInspect({
                                  filename: row.filename,
                                  model: row.model,
                                })
                              }
                            >
                              Misses
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            </>
          )}
        </div>
      </Card>
      {inspect && (
        <MissInspector
          dataset={dataset}
          info={inspect}
          close={() => setInspect(null)}
        />
      )}
    </section>
  );
}

function MissInspector({
  dataset,
  info,
  close,
}: {
  dataset: string;
  info: { filename: string; model: string };
  close: () => void;
}) {
  const [rows, setRows] = useState<CsvRow[]>([]),
    [index, setIndex] = useState(0),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const rowsLengthRef = useRef(0);
  rowsLengthRef.current = rows.length;
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    let active = true;
    setLoading(true);
    api<CsvRow[]>(
      `/api/datasets/${enc(dataset)}/results/${enc(info.filename)}/rows`,
    )
      .then(
        (value) =>
          active &&
          setRows(
            value.filter(
              (row) =>
                text(row.status) === "co_present" && text(row.score) === "0",
            ),
          ),
      )
      .catch(
        (e) => active && setError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [dataset, info]);
  useEffect(() => {
    setIndex(0);
  }, [dataset, info]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        setIndex((current) => {
          const length = rowsLengthRef.current;
          const next = length
            ? event.key === "ArrowRight"
              ? (current + 1) % length
              : (current - 1 + length) % length
            : 0;
          return next;
        });
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);
  const current = rows[index];
  const content = (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/60 p-5"
      onClick={(event) => event.currentTarget === event.target && close()}
    >
      <div
        className="flex max-h-[min(88vh,100%)] w-full max-w-[1000px] flex-col overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border)]/60 bg-[var(--surface)] shadow-[var(--elev-overlay)]"
        role="dialog"
        aria-modal="true"
        aria-label="Miss inspector"
      >
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--border)] p-4">
          <h3>Misses -- {info.model}</h3>
          {!loading && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs tabular-nums text-[var(--muted)]">
                {rows.length ? `${index + 1} of ${rows.length}` : ""}
              </span>
              {rows.length > 0 && (
                <>
                  <Button
                    type="button"
                    className="text-sm"
                    data-step="-1"
                    aria-label="Previous miss"
                    onClick={() =>
                      setIndex(
                        (currentIndex) =>
                          (currentIndex - 1 + rows.length) % rows.length,
                      )
                    }
                  >
                    Prev
                  </Button>
                  <Button
                    type="button"
                    className="text-sm"
                    data-step="1"
                    aria-label="Next miss"
                    onClick={() =>
                      setIndex(
                        (currentIndex) => (currentIndex + 1) % rows.length,
                      )
                    }
                  >
                    Next
                  </Button>
                </>
              )}
              <Button
                type="button"
                className="text-sm"
                id="drawer-close"
                onClick={close}
              >
                Close
              </Button>
            </div>
          )}
        </div>
        <div className="overflow-y-auto p-4">
          {loading ? (
            <LoadingState label="Loading result rows" />
          ) : error ? (
            <ErrorState message={error} />
          ) : !current ? (
            <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border)] p-6 text-center">
              <h3>No misses to inspect</h3>
              <p>This model scored every co-present target on this dataset.</p>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-2 text-sm [&>dt]:text-[var(--muted)] [&>dd]:min-w-0">
                  <dt>Target</dt>
                  <dd>
                    <b>{text(current.target_text)}</b>
                  </dd>
                  <dt>Screen</dt>
                  <dd>
                    <code>{text(current.screen)}</code> /{" "}
                    <code>{text(current.profile)}</code>
                  </dd>
                  <dt>Raw reply</dt>
                  <dd>
                    <code>{text(current.raw_response)}</code>
                  </dd>
                  <dt>Parsed by</dt>
                  <dd>{text(current.parse_method) || "unknown"}</dd>
                </dl>
                <div className="mt-4 flex flex-wrap gap-4 text-xs text-[var(--muted)]">
                  <span className="legend-item" style={{ color: "var(--ok)" }}>
                    <span className="legend-swatch" />
                    Ground truth
                  </span>
                  <span className="legend-item" style={{ color: "var(--err)" }}>
                    <span className="legend-swatch filled" />
                    Predicted point
                  </span>
                </div>
              </div>
              <div>
                <div className="overflow-hidden rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-2)]">
                  <MissCanvas dataset={dataset} row={current} />
                </div>
              </div>
            </div>
          )}
        </div>
        {!loading && rows.length > 0 && (
          <div className="flex gap-2 overflow-x-auto border-t border-[var(--border)] bg-[var(--surface-2)] p-2 px-4" aria-label="Miss filmstrip">
            {rows.map((row, rowIndex) => (
              <Button
                type="button"
                data-jump={rowIndex}
                aria-current={rowIndex === index}
                className={`block min-h-8 max-w-48 shrink-0 overflow-hidden text-ellipsis whitespace-nowrap border border-[var(--border-strong)] bg-[var(--surface)] px-2.5 py-1 text-xs text-[var(--text-2)] shadow-none hover:bg-[var(--surface-2)] ${rowIndex === index ? "!border-[var(--primary)] !bg-[var(--primary)] !text-[var(--primary-fg)]" : ""}`}
                key={`${text(row.screen)}-${rowIndex}`}
                onClick={() => setIndex(rowIndex)}
              >
                {text(row.target_text)}
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
  const root = document.getElementById("drawer-root");
  return root ? createPortal(content, root) : content;
}
function MissCanvas({ dataset, row }: { dataset: string; row: CsvRow }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    drawScreenshot(
      ref.current,
      imageUrl(dataset, text(row.screen), text(row.profile)),
      (ctx, img) => {
        ctx.lineWidth = strokeWidthFor(img);
        if (row.x_min !== "" && row.y_min !== "") {
          ctx.strokeStyle = "#157a41";
          ctx.strokeRect(
            number(row.x_min),
            number(row.y_min),
            number(row.x_max) - number(row.x_min),
            number(row.y_max) - number(row.y_min),
          );
        }
        if (row.x_pred !== "" && row.y_pred !== "") {
          ctx.fillStyle = "#b3221a";
          ctx.beginPath();
          ctx.arc(
            number(row.x_pred),
            number(row.y_pred),
            Math.max(6, img.width / 80),
            0,
            2 * Math.PI,
          );
          ctx.fill();
        }
      },
    );
  }, [dataset, row]);
  return (
    <canvas
      ref={ref}
      id="miss-canvas"
      style={{ maxHeight: "56vh", width: "auto" }}
    />
  );
}
