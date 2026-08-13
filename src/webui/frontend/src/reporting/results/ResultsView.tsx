import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, enc, imageUrl } from "../../lib/api";
import { drawScreenshot, strokeWidthFor } from "../../lib/canvas";
import { ExportButton } from "../components/ExportButton";
import type { TabViewProps } from "../../lib/types";
import { AccuracyChart } from "../charts";

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
  return <span className={`badge ${className}`}>{children}</span>;
}
function ErrorState({ message }: { message: string }) {
  return (
    <p className="state-error" role="alert">
      {message}
    </p>
  );
}
function LoadingState({ message }: { message: string }) {
  return <p className="state-loading">{message}</p>;
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
  if (!parts.length) return <span className="muted">--</span>;
  return (
    <div className="tally" style={{ marginTop: 0 }}>
      {parts.map(([key, label, hint]) =>
        key === "api_error" ? (
          <Badge className="err" key={key}>
            {statuses[key]} API errors
          </Badge>
        ) : (
          <span className="tally-item" title={hint} key={key}>
            <b>{statuses[key]}</b> {label}
          </span>
        ),
      )}
    </div>
  );
}
function AccuracyCell({ row }: { row: Result }) {
  if (row.accuracy == null) return <span className="muted">--</span>;
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
  useEffect(() => {
    let active = true;
    if (!dataset) return;
    api<Result[]>(`/api/datasets/${enc(dataset)}/results`)
      .then((value) => active && setRows(value))
      .catch(
        (e) =>
          active &&
          (setRows([]), setError(e instanceof Error ? e.message : String(e))),
      );
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
      className="tab"
      aria-labelledby="head-results"
      hidden={hidden}
    >
      <div className="view-head">
        <h2 id="head-results">Results</h2>
        <p className="lead">
          Per-model accuracy over the targets present on both profiles.
        </p>
      </div>
      <div className="card">
        <div className="card-head">
          <h3>Evaluated models</h3>
          <div id="results-mode-filter">
            {modes.length > 1 && (
              <div
                className="segmented"
                role="group"
                aria-label="Prompt mode filter"
              >
                <button
                  type="button"
                  data-mode="all"
                  aria-pressed={mode === "all"}
                  onClick={() => setMode("all")}
                >
                  All
                </button>
                {modes.map((value) => (
                  <button
                    type="button"
                    data-mode={value}
                    aria-pressed={mode === value}
                    onClick={() => setMode(value)}
                    key={value}
                  >
                    {value}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div id="results-body">
          {error ? (
            <ErrorState message={error} />
          ) : !rows.length ? (
            <div className="empty-state">
              <h3>No evaluations yet</h3>
              <p>
                Result files appear here once a model has been evaluated against
                this dataset.
              </p>
              <a href="#evaluate">
                <button type="button">Go to Evaluate</button>
              </a>
            </div>
          ) : (
            <>
              {modes.length > 1 && (
                <div className="note">
                  <span className="note-label">Note</span>Vision and tree
                  results answer different research questions and are never
                  pooled. Analyze runs one arm at a time.
                </div>
              )}
              {visible.some((row) => row.accuracy != null) && (
                <div className="card">
                  <div className="card-head">
                    <div>
                      <h3>Overall accuracy</h3>
                      <p className="card-sub">
                        Blended across every profile, co-present targets only.
                        The exact figures and the baseline-only breakdown are in
                        the table below.
                      </p>
                    </div>
                    <div className="card-head-actions">
                      <ExportButton name="results-overall-accuracy" />
                    </div>
                  </div>
                  <div className="chart-draw-in">
                    <AccuracyChart
                      rows={visible
                        .filter((row) => row.accuracy != null)
                        .sort((a, b) => (b.accuracy || 0) - (a.accuracy || 0))
                        .map((row) => ({
                          label: row.model,
                          value: row.accuracy || 0,
                        }))}
                    />
                  </div>
                </div>
              )}
              {selectedRows.length >= 2 && (
                <div className="card card-dark">
                  <div className="card-head">
                    <div>
                      <h3>Comparing {selectedRows.length} selected models</h3>
                      <p className="card-sub">
                        Same accuracy figures as the table below, isolated for a
                        direct look.
                      </p>
                    </div>
                    <div className="card-head-actions">
                      <ExportButton name="results-selected-comparison" />
                      <button
                        type="button"
                        className="secondary small"
                        id="results-compare-clear"
                        onClick={() => setSelected(new Set())}
                      >
                        Clear selection
                      </button>
                    </div>
                  </div>
                  <div className="chart-dark">
                    <AccuracyChart
                      rows={selectedRows
                        .filter((row) => row.accuracy != null)
                        .map((row) => ({
                          label: `${row.model}${row.prompt_mode ? ` (${row.prompt_mode})` : ""}`,
                          value: row.accuracy || 0,
                        }))}
                    />
                  </div>
                </div>
              )}
              <div className="table-stack">
                <div className="table-wrap">
                  <table id="results-table">
                    <thead>
                      <tr>
                        <th
                          className="num"
                          title="Check models to compare them side by side"
                        >
                          Compare
                        </th>
                        {[
                          ["model", "Model"],
                          ["prompt_mode", "Mode"],
                          ["row_count", "Rows"],
                          ["accuracy", "Accuracy"],
                        ].map(([key, label]) => (
                          <th
                            key={key}
                            className="sortable"
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
                          </th>
                        ))}
                        <th title="Blended accuracy compared with baseline-only accuracy">
                          vs. baseline
                        </th>
                        <th title="Rows excluded from the accuracy denominator, by CSV status">
                          Not scored
                        </th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((row) => (
                        <tr key={row.filename}>
                          <td className="num" data-label="Compare">
                            <input
                              type="checkbox"
                              data-compare-select={row.filename}
                              checked={selected.has(row.filename)}
                              onChange={() => toggle(row.filename)}
                              aria-label={`Compare ${row.model} (${row.prompt_mode})`}
                            />
                          </td>
                          <td data-label="Model">
                            <b>{row.model}</b>
                          </td>
                          <td data-label="Mode">
                            {row.prompt_mode || (
                              <span className="muted">--</span>
                            )}
                          </td>
                          <td className="num" data-label="Rows">
                            {row.row_count}
                          </td>
                          <td data-label="Accuracy">
                            <AccuracyCell row={row} />
                          </td>
                          <td data-label="vs. baseline">
                            {row.accuracy == null ||
                            row.baseline_accuracy == null ? (
                              <span className="muted">--</span>
                            ) : (
                              `${((row.baseline_accuracy - row.accuracy) * 100).toFixed(1)} pts`
                            )}
                          </td>
                          <td data-label="Not scored">
                            <NotScored statuses={row.statuses || {}} />
                          </td>
                          <td data-label="" style={{ textAlign: "right" }}>
                            <button
                              type="button"
                              className="secondary small"
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
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
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
      className="drawer-backdrop"
      onClick={(event) => event.currentTarget === event.target && close()}
    >
      <div
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Miss inspector"
      >
        <div className="drawer-head">
          <h3>Misses -- {info.model}</h3>
          {!loading && (
            <div className="drawer-nav">
              <span className="drawer-position">
                {rows.length ? `${index + 1} of ${rows.length}` : ""}
              </span>
              {rows.length > 0 && (
                <>
                  <button
                    type="button"
                    className="secondary small"
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
                  </button>
                  <button
                    type="button"
                    className="secondary small"
                    data-step="1"
                    aria-label="Next miss"
                    onClick={() =>
                      setIndex(
                        (currentIndex) => (currentIndex + 1) % rows.length,
                      )
                    }
                  >
                    Next
                  </button>
                </>
              )}
              <button
                type="button"
                className="secondary small"
                id="drawer-close"
                onClick={close}
              >
                Close
              </button>
            </div>
          )}
        </div>
        <div className="drawer-body">
          {loading ? (
            <LoadingState message="Loading rows..." />
          ) : error ? (
            <ErrorState message={error} />
          ) : !current ? (
            <div className="empty-state">
              <h3>No misses to inspect</h3>
              <p>This model scored every co-present target on this dataset.</p>
            </div>
          ) : (
            <div className="row">
              <div className="grow">
                <dl className="kv">
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
                <div className="overlay-legend">
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
                <div className="image-frame">
                  <MissCanvas dataset={dataset} row={current} />
                </div>
              </div>
            </div>
          )}
        </div>
        {!loading && rows.length > 0 && (
          <div className="filmstrip" aria-label="Miss filmstrip">
            {rows.map((row, rowIndex) => (
              <button
                type="button"
                data-jump={rowIndex}
                aria-current={rowIndex === index}
                className={rowIndex === index ? "selected" : ""}
                key={`${text(row.screen)}-${rowIndex}`}
                onClick={() => setIndex(rowIndex)}
              >
                {text(row.target_text)}
              </button>
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
