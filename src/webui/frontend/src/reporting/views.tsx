import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, enc, imageUrl } from "../lib/api";
import { drawScreenshot, strokeWidthFor } from "../lib/canvas";
import { exportSvgAsPng } from "../lib/export";
import type { TabViewProps } from "../lib/types";
import {
  AccuracyChart,
  DiscordantChart,
  DirectionChart,
  DumbbellChart,
  Legend,
  ReachabilityChart,
} from "./charts";

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
type Compare = {
  model: string;
  mode: string;
  models_in_family: string[];
  profiles: Array<{
    profile: string;
    baseline_accuracy: number;
    profile_accuracy: number;
    delta: number;
    b: number;
    c: number;
    reachability: number | null;
    significance_state: string;
    power_flag?: string;
  }>;
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
const profileLabels: Record<string, string> = {
  baseline: "Baseline",
  font_scale_1_3: "Font scale 1.3",
  font_scale_1_5: "Font scale 1.5",
  high_contrast: "High contrast",
  grayscale: "Grayscale",
  talkback: "TalkBack",
};
const text = (value: unknown) => String(value ?? "");
const number = (value: unknown) => {
  const n = Number(String(value ?? "").replace("%", ""));
  return Number.isFinite(n) ? n : NaN;
};
const fraction = (value: unknown) => {
  const n = number(value);
  return typeof value === "string" && value.trim().endsWith("%") ? n / 100 : n;
};
const pct = (value: unknown) => {
  const n = fraction(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : "--";
};
const profileName = (value: string) => profileLabels[value] || value;

function ExportButton({ name }: { name: string }) {
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <button
      ref={ref}
      type="button"
      className="secondary small icon-btn"
      data-export-chart={name}
      title="Export chart as PNG"
      aria-label="Export chart as PNG"
      onClick={() => {
        const svg = ref.current?.closest(".card")?.querySelector("svg.chart");
        if (svg instanceof SVGSVGElement) exportSvgAsPng(svg, `${name}.png`);
      }}
    >
      ⇩
    </button>
  );
}
function Table({
  headers,
  rows,
}: {
  headers: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <details className="data-table">
      <summary>Show table</summary>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th key={`${h}-${i}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
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

export function CompareView({
  dataset,
  onCountChange,
  hidden,
}: TabViewProps & {
  dataset: string;
  onCountChange?: (count: number) => void;
}) {
  const [mode, setMode] = useState("vision"),
    [models, setModels] = useState<Result[]>([]),
    [model, setModel] = useState(""),
    [result, setResult] = useState<Compare | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    if (!dataset) {
      setModels([]);
      return;
    }
    api<Result[]>(`/api/datasets/${enc(dataset)}/results`)
      .then((value) => active && setModels(value))
      .catch(() => active && setModels([]));
    return () => {
      active = false;
    };
  }, [dataset]);
  useEffect(() => {
    onCountChange?.(models.length);
  }, [models.length, onCountChange]);
  const choices = useMemo(
    () =>
      models
        .filter((row) => row.prompt_mode === mode)
        .sort((a, b) => (b.accuracy ?? -1) - (a.accuracy ?? -1)),
    [models, mode],
  );
  useEffect(() => {
    setModel((current) =>
      choices.some((row) => row.model === current)
        ? current
        : choices[0]?.model || "",
    );
  }, [choices]);
  useEffect(() => {
    let active = true;
    if (!dataset || !model) {
      setResult(null);
      return;
    }
    setLoading(true);
    setError("");
    api<Compare>(
      `/api/datasets/${enc(dataset)}/results/compare?model=${enc(model)}&mode=${enc(mode)}&sample=primary`,
    )
      .then((value) => {
        if (active) setResult(value);
      })
      .catch((e) => {
        if (active) {
          setResult(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [dataset, model, mode]);
  return (
    <section id="tab-compare" className="tab" aria-labelledby="head-compare" hidden={hidden}>
      <div className="view-head">
        <h2 id="head-compare">Compare</h2>
        <p className="lead">
          Pick a model you've evaluated and compare accessibility profiles.
        </p>
      </div>
      <div className="card">
        <div className="field-row">
          <label className="field">
            Prompt mode
            <select
              id="compare-mode-select"
              value={mode}
              onChange={(event) => setMode(event.target.value)}
            >
              <option value="vision">Vision</option>
              <option value="tree">Tree</option>
            </select>
          </label>
          <label className="field field-wide">
            Model
            <select
              id="compare-model-select"
              disabled={!choices.length}
              value={model}
              onChange={(event) => setModel(event.target.value)}
            >
              <option value="">
                {choices.length ? "Select model" : `No ${mode} results yet`}
              </option>
              {choices.map((row) => (
                <option value={row.model} key={row.filename}>
                  {row.model}
                  {row.accuracy == null
                    ? ""
                    : ` -- ${(row.accuracy * 100).toFixed(1)}% baseline overall`}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <div id="compare-body">
        {loading ? (
          <LoadingState message="Comparing baseline against each profile..." />
        ) : error ? (
          <ErrorState message={error} />
        ) : result ? (
          <CompareResult result={result} />
        ) : null}
      </div>
    </section>
  );
}
function CompareResult({ result }: { result: Compare }) {
  const rows = result.profiles;
  return (
    <>
      <div className="card card-dark">
        <div className="card-head">
          <div>
            <h3>Baseline versus each profile</h3>
            <p className="card-sub">
              {result.model} -- {rows.length} profile
              {rows.length === 1 ? "" : "s"} tested against baseline,{" "}
              {result.mode} arm.
            </p>
          </div>
          <div className="card-head-actions">
            <ExportButton name={`compare-${result.model}-${result.mode}`} />
          </div>
        </div>
        <Legend
          items={[
            { color: "var(--viz-blue)", label: "Baseline accuracy" },
            { color: "var(--viz-orange)", label: "Profile accuracy" },
          ]}
        />
        <div className="chart-dark chart-draw-in">
          <DumbbellChart
            rows={rows.map((row) => ({
              label: profileName(row.profile),
              from: row.baseline_accuracy / 100,
              to: row.profile_accuracy / 100,
              underpowered: row.significance_state === "underpowered",
            }))}
          />
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Profile</th>
              <th className="num">Baseline</th>
              <th className="num">Profile</th>
              <th className="num">Delta</th>
              <th className="num">b / c</th>
              <th className="num">Reachable</th>
              <th>Significance</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.profile}>
                <td>{profileName(row.profile)}</td>
                <td className="num tabular">
                  {row.baseline_accuracy.toFixed(1)}%
                </td>
                <td className="num tabular">
                  {row.profile_accuracy.toFixed(1)}%
                </td>
                <td className="num">
                  {row.delta > 0 ? "-" : "+"}
                  {Math.abs(row.delta).toFixed(1)} pts
                </td>
                <td className="num tabular">
                  {row.b} / {row.c}
                </td>
                <td className="num tabular">
                  {row.reachability == null
                    ? "--"
                    : `${(row.reachability * 100).toFixed(1)}%`}
                </td>
                <td>
                  {row.significance_state === "underpowered" ? (
                    <Badge className="sig-underpowered">
                      Underpowered -- can't tell (
                      {row.power_flag || "ceiling/floor"})
                    </Badge>
                  ) : row.significance_state === "significant" ? (
                    <Badge className="sig-yes">significant</Badge>
                  ) : (
                    <Badge className="sig-no">No significant change</Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="note">
        <span className="note-label">Note</span>Corrected across all{" "}
        {result.models_in_family.length} model
        {result.models_in_family.length === 1 ? "" : "s"} evaluated on this
        dataset's {result.mode} arm (Holm-Bonferroni, α = 0.05) -- per-model
        McNemar is secondary to the pooled permutation test on the Analyze view.
        An underpowered result is not evidence the model is resilient.
      </div>
    </>
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
    <section id="tab-results" className="tab" aria-labelledby="head-results" hidden={hidden}>
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
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "ArrowRight" || event.key === "ArrowLeft")
        setIndex((current) => {
          const next = rows.length
            ? event.key === "ArrowRight"
              ? (current + 1) % rows.length
              : (current - 1 + rows.length) % rows.length
            : 0;
          document
            .querySelectorAll("#drawer-root .filmstrip button")
            .forEach((button, i) =>
              button.classList.toggle("selected", i === next),
            );
          return next;
        });
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [close, rows.length]);
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

export function AnalyzeView({ dataset, hidden }: TabViewProps & { dataset: string }) {
  const [mode, setMode] = useState("vision"),
    [sample, setSample] = useState("all"),
    [permutations, setPermutations] = useState(20000),
    [seed, setSeed] = useState(0),
    [result, setResult] = useState<Analysis | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [activeSample, setActiveSample] = useState<string | null>(null),
    [activeProfile, setActiveProfile] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    if (!dataset) {
      setResult(null);
      return;
    }
    api<Analysis>(
      `/api/datasets/${enc(dataset)}/analysis?mode=${enc(mode)}&sample=${enc(sample)}`,
    )
      .then((value) => {
        if (active) {
          setResult(value.available ? value : null);
          setError("");
          setActiveSample(null);
          setActiveProfile(null);
        }
      })
      .catch(
        (e) => active && setError(e instanceof Error ? e.message : String(e)),
      );
    return () => {
      active = false;
    };
  }, [dataset, mode, sample]);
  const run = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      setResult(
        await api<Analysis>("/api/analyze", {
          method: "POST",
          body: JSON.stringify({ dataset, sample, mode, permutations, seed }),
        }),
      );
      setActiveSample(null);
      setActiveProfile(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };
  return (
    <section id="tab-analyze" className="tab" aria-labelledby="head-analyze" hidden={hidden}>
      <div className="view-head">
        <h2 id="head-analyze">Analyze</h2>
        <p className="lead">
          Reachability, pooled permutation tests, and per-model tests.
        </p>
      </div>
      <div className="card card-primary">
        <form id="analyze-form" onSubmit={run}>
          <div className="field-row">
            <label className="field field-wide">
              Sample
              <select
                id="analyze-sample"
                value={sample}
                onChange={(event) => setSample(event.target.value)}
              >
                <option value="all">All samples</option>
                <option value="primary">Primary</option>
                <option value="full">Full</option>
                <option value="precautionary">Precautionary</option>
                <option value="uniform">Uniform</option>
              </select>
            </label>
            <label className="field">
              Prompt mode
              <select
                id="analyze-mode"
                value={mode}
                onChange={(event) => setMode(event.target.value)}
              >
                <option value="vision">Vision only</option>
                <option value="tree">Vision + a11y tree</option>
              </select>
            </label>
            <button type="submit" id="analyze-submit" disabled={loading}>
              {loading ? "Running" : "Run analysis"}
            </button>
          </div>
          <details className="advanced">
            <summary>Advanced options</summary>
            <div className="advanced-body">
              <label className="field">
                Permutations
                <input
                  id="analyze-permutations"
                  type="number"
                  min="1"
                  value={permutations}
                  onChange={(event) =>
                    setPermutations(Number(event.target.value) || 1)
                  }
                />
              </label>
              <label className="field">
                Seed
                <input
                  id="analyze-seed"
                  type="number"
                  value={seed}
                  onChange={(event) => setSeed(Number(event.target.value) || 0)}
                />
              </label>
            </div>
          </details>
        </form>
        <div id="analyze-error">{error && <ErrorState message={error} />}</div>
      </div>
      <div id="analyze-results">
        {loading ? (
          <div className="card">
            <LoadingState
              message={`Running ${permutations.toLocaleString()} permutations. This can take a minute.`}
            />
            <div
              className="progress is-indeterminate"
              style={{ marginTop: "var(--space-3)" }}
            >
              <div className="progress-fill" />
            </div>
          </div>
        ) : result ? (
          <AnalysisResult
            result={result}
            activeSample={activeSample}
            setActiveSample={setActiveSample}
            activeProfile={activeProfile}
            setActiveProfile={setActiveProfile}
          />
        ) : (
          <div className="note">
            <span className="note-label">Note</span>No analysis has been run yet
            for <code>{mode}</code> / <code>{sample}</code>. Run one below --
            results appear here immediately for any mode/sample combination that
            already has tables, without waiting on a new run.
          </div>
        )}
      </div>
    </section>
  );
}

function AnalysisResult({
  result,
  activeSample,
  setActiveSample,
  activeProfile,
  setActiveProfile,
}: {
  result: Analysis;
  activeSample: string | null;
  setActiveSample: (value: string) => void;
  activeProfile: string | null;
  setActiveProfile: (value: string) => void;
}) {
  const all = [
    ...(result.reachability || []),
    ...(result.pooled_permutation || []),
    ...(result.mcnemar_per_model || []),
    ...(result.direction_consistency || []),
  ];
  const samples = [
    ...new Set(all.map((row) => text(row.Sample)).filter(Boolean)),
  ];
  const sample =
    activeSample && samples.includes(activeSample) ? activeSample : samples[0];
  const filter = (rows: CsvRow[]) =>
    rows.filter((row) => text(row.Sample) === sample);
  const reach = filter(result.reachability || []),
    pooled = filter(result.pooled_permutation || []),
    mcn = filter(result.mcnemar_per_model || []),
    direction = filter(result.direction_consistency || []);
  const profiles = [...new Set(mcn.map((row) => text(row.Profile)))];
  const profile =
    activeProfile && profiles.includes(activeProfile)
      ? activeProfile
      : profiles[0];
  return (
    <>
      {
        <div className="note note-info">
          <span className="note-label">Note</span>
          <b>
            Pooled permutation is the primary test; per-model McNemar is
            secondary.
          </b>{" "}
          Rows flagged ceiling or floor are underpowered, and an underpowered
          null is not evidence that a model is resilient. Reachability carries a
          survivorship caveat on the heaviest profiles: the co-present set is
          not profile-independent, so baseline accuracy measured only over the
          targets that survived a hard profile reads higher than the model's
          true baseline. See <code>docs/methods.md</code>.
        </div>
      }
      {result.output_dir && (
        <p className="muted small" style={{ margin: "0 0 var(--space-4)" }}>
          Tables written to <code>{result.output_dir}/</code> -- the dataset's
          own analysis files are left alone.
        </p>
      )}
      {samples.length > 1 && (
        <div
          className="segmented"
          role="group"
          aria-label="Sample"
          style={{ marginBottom: "var(--space-4" }}
        >
          {samples.map((value) => (
            <button
              type="button"
              data-sample={value}
              aria-pressed={value === sample}
              onClick={() => setActiveSample(value)}
              key={value}
            >
              {value}
            </button>
          ))}
        </div>
      )}
      <AnalysisCard
        title="Reachability"
        subtitle="Share of baseline targets that still render under each profile. A target that is gone cannot be grounded by any model."
        exportName="reachability"
        empty="No reachability rows were produced."
      >
        <ReachabilityChart
          rows={reach.map((row) => ({
            label: text(row.Profile),
            value: fraction(row.Reachability),
            lo: fraction(row.CI_Low),
            hi: fraction(row.CI_High),
          }))}
        />
        <Table
          headers={[
            "Sample",
            "Profile",
            "Present / total",
            "Reachability",
            "95% CI",
          ]}
          rows={reach.map((row) => [
            text(row.Sample),
            text(row.Profile),
            `${text(row.Targets_Present)}/${text(row.Targets_Total)}`,
            pct(row.Reachability),
            `[${pct(row.CI_Low)}, ${pct(row.CI_High)}]`,
          ])}
        />
      </AnalysisCard>
      <AnalysisCard
        title="Pooled permutation (primary)"
        subtitle="Cluster permutation across models, clustered on target. Discordant pairs only."
        exportName="pooled-permutation"
        empty="No pooled rows were produced."
      >
        <Legend
          items={[
            { color: "var(--viz-red)", label: "Broke it (b)" },
            { color: "var(--viz-blue)", label: "Recovered (c)" },
            {
              color: "var(--text)",
              label: "Filled square: significant after Holm",
            },
            {
              color: "var(--text-2)",
              label: "Hollow square: not significant",
              shape: "hollow",
            },
          ]}
        />
        <DiscordantChart
          rows={pooled.map((row) => ({
            label: text(row.Profile),
            left: number(row.Broke_It_b),
            right: number(row.Fluke_Recovery_c),
            significant: text(row.Significant) === "Yes",
            annotation: `p = ${number(row.P_Value).toFixed(4)}`,
          }))}
        />
        <Table
          headers={[
            "Sample",
            "Profile",
            "Broke it (b)",
            "Recovered (c)",
            "p",
            "Holm-significant",
          ]}
          rows={pooled.map((row) => [
            text(row.Sample),
            text(row.Profile),
            text(row.Broke_It_b),
            text(row.Fluke_Recovery_c),
            number(row.P_Value).toFixed(4),
            text(row.Significant) === "Yes" ? (
              <Badge className="ok">significant</Badge>
            ) : (
              <Badge className="muted">ns</Badge>
            ),
          ])}
        />
      </AnalysisCard>
      <AnalysisCard
        title="Per-model McNemar (secondary)"
        subtitle="Co-present targets only, Holm-corrected across the family."
        exportName={`per-model-mcnemar-${profile || ""}`}
        empty="No per-model rows were produced."
        id="per-model-card"
      >
        <div className="segmented" role="group" aria-label="Profile">
          {profiles.map((value) => (
            <button
              type="button"
              data-dumbbell-profile={value}
              aria-pressed={value === profile}
              onClick={() => setActiveProfile(value)}
              key={value}
            >
              {value}
            </button>
          ))}
        </div>
        <Legend
          items={[
            { color: "var(--viz-blue)", label: "Baseline accuracy" },
            {
              color: "var(--viz-orange)",
              label: "Accuracy under this profile",
            },
            {
              color: "var(--text-2)",
              label: "† underpowered (ceiling or floor)",
            },
          ]}
        />
        <DumbbellChart
          rows={mcn
            .filter((row) => text(row.Profile) === profile)
            .map((row) => ({
              label: text(row.Model),
              from: fraction(row.Baseline_Acc),
              to: fraction(row.Exp_Acc),
              underpowered: Boolean(
                text(row.Power_Limit) &&
                text(row.Power_Limit) !== "-" &&
                text(row.Power_Limit) !== "none",
              ),
            }))}
        />
        <Table
          headers={[
            "Sample",
            "Model",
            "Profile",
            "Baseline",
            "Profile acc",
            "p",
            "Power",
          ]}
          rows={mcn.map((row) => [
            text(row.Sample),
            text(row.Model),
            text(row.Profile),
            pct(row.Baseline_Acc),
            pct(row.Exp_Acc),
            number(row.P_Value).toFixed(4),
            text(row.Power_Limit),
          ])}
        />
      </AnalysisCard>
      <AnalysisCard
        title="Direction consistency (descriptive)"
        subtitle="Counts models by direction of change. Result CSVs are not independent models -- configuration variants of one base model share a row here."
        exportName="direction-consistency"
        empty="No sign-test rows were produced."
      >
        <Legend
          items={[
            { color: "var(--viz-red)", label: "Accuracy down" },
            { color: "var(--viz-neutral)", label: "Tied" },
            { color: "var(--viz-blue)", label: "Accuracy up" },
          ]}
        />
        <DirectionChart
          rows={direction.map((row) => ({
            label: text(row.Profile),
            down: number(row.Models_Down),
            up: number(row.Models_Up),
            tied: number(row.Models_Tied),
            p: number(row.Sign_P_Value).toFixed(4),
          }))}
        />
        <Table
          headers={["Sample", "Profile", "Down", "Up", "Tied", "Sign p"]}
          rows={direction.map((row) => [
            text(row.Sample),
            text(row.Profile),
            text(row.Models_Down),
            text(row.Models_Up),
            text(row.Models_Tied),
            number(row.Sign_P_Value).toFixed(4),
          ])}
        />
      </AnalysisCard>
    </>
  );
}
function AnalysisCard({
  title,
  subtitle,
  exportName,
  empty,
  id,
  children,
}: {
  title: string;
  subtitle: string;
  exportName: string;
  empty: string;
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card" id={id}>
      <div className="card-head">
        <div>
          <h3>{title}</h3>
          <p className="card-sub">{subtitle}</p>
        </div>
        <div className="card-head-actions">
          <ExportButton name={exportName} />
        </div>
      </div>
      {children || <p className="muted small">{empty}</p>}
    </div>
  );
}
