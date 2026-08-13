import React, { useEffect, useMemo, useState } from "react";
import { api, enc } from "../../lib/api";
import { ExportButton } from "../components/ExportButton";
import type { TabViewProps } from "../../lib/types";
import { DumbbellChart, Legend } from "../charts";
import "../reporting.module.css";

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
    <section
      id="tab-compare"
      className="tab"
      aria-labelledby="head-compare"
      hidden={hidden}
    >
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
