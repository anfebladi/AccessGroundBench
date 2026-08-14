import React, { useEffect, useMemo, useState } from "react";
import { api, enc } from "../../lib/api";
import { ExportButton } from "../shared/reporting/components/ExportButton";
import type { TabViewProps } from "../../lib/types";
import { Legend, PairedAccuracyChart } from "../shared/reporting/charts";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Card } from "../../components/ui/card";
import { LoadingState } from "../../components/ui/spinner";
import { Badge as UiBadge } from "../../components/ui/badge";
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
const compareCardClassName =
  "rounded-[var(--radius-lg)] border-[var(--on-dark-border)] bg-[var(--panel-dark)] text-[var(--on-dark)] [&_.card-sub]:text-[var(--on-dark-muted)] [&_button]:border-[var(--on-dark-border)] [&_button]:bg-[var(--panel-dark-2)] [&_button]:text-[var(--on-dark-muted)] [&_button:hover]:bg-[var(--panel-dark)]";

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
    <p
      className="rounded-md border border-[var(--err)]/40 bg-[var(--err)]/10 p-3 text-sm text-[var(--err)]"
      role="alert"
    >
      {message}
    </p>
  );
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
    [loading, setLoading] = useState(false),
    [modelsLoading, setModelsLoading] = useState(false);
  useEffect(() => {
    let active = true;
    if (!dataset) {
      setModels([]);
      return;
    }
    setModelsLoading(true);
    api<Result[]>(`/api/datasets/${enc(dataset)}/results`)
      .then((value) => active && setModels(value))
      .catch(() => active && setModels([]))
      .finally(() => active && setModelsLoading(false));
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
      className="tab min-w-0"
      aria-labelledby="head-compare"
      hidden={hidden}
    >
      <StageHeader stage="compare" title="Compare">
        Pick a model you've evaluated and compare accessibility profiles.
      </StageHeader>
      <Card className="rounded-[var(--radius-lg)]">
        <div className="flex flex-wrap items-end gap-3">
          <label
            className="flex min-w-0 flex-col gap-[var(--space-1)] text-[length:var(--text-sm)] font-medium text-[var(--text)]"
          >
            Prompt mode
            <Select value={mode} onValueChange={setMode}>
              <SelectTrigger id="compare-mode-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="vision">Vision</SelectItem>
                <SelectItem value="tree">Tree</SelectItem>
              </SelectContent>
            </Select>
          </label>
          <label
            className="flex min-w-0 flex-[1_1_22rem] flex-col gap-[var(--space-1)] text-[length:var(--text-sm)] font-medium text-[var(--text)]"
          >
            Model
            <Select disabled={!choices.length} value={model} onValueChange={setModel}>
              <SelectTrigger id="compare-model-select">
                <SelectValue
                  placeholder={modelsLoading ? "Loading results…" : choices.length ? "Select model" : `No ${mode} results yet`}
                />
              </SelectTrigger>
              <SelectContent>
                {choices.map((row) => (
                  <SelectItem value={row.model} key={row.filename}>
                    {row.model}
                    {row.accuracy == null
                      ? ""
                      : ` -- ${(row.accuracy * 100).toFixed(1)}% baseline overall`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        </div>
      </Card>
      <div id="compare-body">
        {loading ? (
          <LoadingState label="Comparing baseline against each profile..." />
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
      <Card
        className={compareCardClassName}
        id={`compare-${result.model}-${result.mode}`}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3>Baseline versus each profile</h3>
            <p className="text-sm text-[var(--on-dark-muted)]">
              {result.model} -- {rows.length} profile
              {rows.length === 1 ? "" : "s"} tested against baseline in the{" "}
              {result.mode} arm. The chart uses a zoomed accuracy scale.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <ExportButton
              name={`compare-${result.model}-${result.mode}`}
              targetId={`compare-${result.model}-${result.mode}`}
            />
          </div>
        </div>
        <Legend
          tone="dark"
          items={[
            { color: "var(--viz-blue)", label: "Baseline accuracy" },
            { color: "var(--viz-orange)", label: "Profile accuracy" },
            { color: "var(--on-dark-muted)", label: "† Underpowered" },
          ]}
        />
        <p className="mb-4 text-xs text-[var(--on-dark-muted)]">
          † Underpowered: too few informative paired comparisons to detect or rule out a real difference; ‘No change’ is inconclusive.
        </p>
        <div className="overflow-x-auto text-[var(--on-dark-muted)]">
          <PairedAccuracyChart
            tone="dark"
            rows={rows.map((row) => ({
              label: profileName(row.profile),
              from: row.baseline_accuracy / 100,
              to: row.profile_accuracy / 100,
              underpowered: row.significance_state === "underpowered",
            }))}
          />
        </div>
      </Card>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Profile</TableHead>
              <TableHead className="num">Baseline</TableHead>
              <TableHead className="num">Profile</TableHead>
              <TableHead className="num">Delta</TableHead>
              <TableHead className="num">b / c</TableHead>
              <TableHead className="num">Reachable</TableHead>
              <TableHead>Significance</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.profile}>
                <TableCell>{profileName(row.profile)}</TableCell>
                <TableCell className="num tabular">
                  {row.baseline_accuracy.toFixed(1)}%
                </TableCell>
                <TableCell className="num tabular">
                  {row.profile_accuracy.toFixed(1)}%
                </TableCell>
                <TableCell className="num">
                  {row.delta > 0 ? "-" : "+"}
                  {Math.abs(row.delta).toFixed(1)} pts
                </TableCell>
                <TableCell className="num tabular">
                  {row.b} / {row.c}
                </TableCell>
                <TableCell className="num tabular">
                  {row.reachability == null
                    ? "--"
                    : `${(row.reachability * 100).toFixed(1)}%`}
                </TableCell>
                <TableCell>
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
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm">
        <span className="mr-2 font-semibold">Note</span>Corrected across all{" "}
        {result.models_in_family.length} model
        {result.models_in_family.length === 1 ? "" : "s"} evaluated on this
        dataset's {result.mode} arm (Holm-Bonferroni, α = 0.05) -- per-model
        McNemar is secondary to the pooled permutation test on the Analyze view.
        An underpowered result is not evidence the model is resilient.
      </div>
    </>
  );
}
