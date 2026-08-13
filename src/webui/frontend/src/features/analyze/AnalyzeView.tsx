import React, { useEffect, useState } from "react";
import { api, enc } from "../../lib/api";
import { ExportButton } from "../shared/reporting/components/ExportButton";
import type { TabViewProps } from "../../lib/types";
import {
  DiscordantChart,
  DirectionChart,
  DumbbellChart,
  Legend,
  ReachabilityChart,
} from "../shared/reporting/charts";
import "../shared/reporting/reporting.module.css";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";
import { Card } from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";
import { Progress } from "../../components/ui/progress";
import { Badge as UiBadge } from "../../components/ui/badge";
import {
  Table as UiTable,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../../components/ui/table";

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
const fraction = (value: unknown) => {
  const n = number(value);
  return typeof value === "string" && value.trim().endsWith("%") ? n / 100 : n;
};
const pct = (value: unknown) => {
  const n = fraction(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : "--";
};
function Badge({
  className,
  children,
}: {
  className: string;
  children: React.ReactNode;
}) {
  return <UiBadge className={`badge ${className}`}>{children}</UiBadge>;
}
function ErrorState({ message }: { message: string }) {
  return (
    <p className="state-error" role="alert">
      {message}
    </p>
  );
}
function LoadingState({ message }: { message: string }) {
  return <div aria-label={message}><p className="state-loading">{message}</p><Skeleton className="skeleton-row" /><Skeleton className="skeleton-block" /></div>;
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
        <UiTable>
          <TableHeader>
            <TableRow>
              {headers.map((h, i) => (
                <TableHead key={`${h}-${i}`}>{h}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, i) => (
              <TableRow key={i}>
                {row.map((cell, j) => (
                  <TableCell key={j}>{cell}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </UiTable>
      </div>
    </details>
  );
}

export function AnalyzeView({
  dataset,
  hidden,
}: TabViewProps & { dataset: string }) {
  const [mode, setMode] = useState("vision"),
    [sample, setSample] = useState("all"),
    [permutations, setPermutations] = useState(20000),
    [seed, setSeed] = useState(0),
    [result, setResult] = useState<Analysis | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [readLoading, setReadLoading] = useState(false),
    [activeSample, setActiveSample] = useState<string | null>(null),
    [activeProfile, setActiveProfile] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    if (!dataset) {
      setResult(null);
      return;
    }
    setReadLoading(true);
    setResult(null);
    setError("");
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
      )
      .finally(() => active && setReadLoading(false));
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
    <section
      id="tab-analyze"
      className="tab"
      aria-labelledby="head-analyze"
      hidden={hidden}
    >
      <div className="view-head">
        <h2 id="head-analyze">Analyze</h2>
        <p className="lead">
          Reachability, pooled permutation tests, and per-model tests.
        </p>
      </div>
      <Card className="card card-primary">
        <form id="analyze-form" onSubmit={run}>
          <div className="field-row">
            <label className="field field-wide">
              Sample
              <NativeSelect
                id="analyze-sample"
                value={sample}
                onChange={(event) => setSample(event.target.value)}
              >
                <option value="all">All samples</option>
                <option value="primary">Primary</option>
                <option value="full">Full</option>
                <option value="precautionary">Precautionary</option>
                <option value="uniform">Uniform</option>
              </NativeSelect>
            </label>
            <label className="field">
              Prompt mode
              <NativeSelect
                id="analyze-mode"
                value={mode}
                onChange={(event) => setMode(event.target.value)}
              >
                <option value="vision">Vision only</option>
                <option value="tree">Vision + a11y tree</option>
              </NativeSelect>
            </label>
            <Button type="submit" id="analyze-submit" disabled={loading}>
              {loading ? "Running" : "Run analysis"}
            </Button>
          </div>
          <details className="advanced">
            <summary>Advanced options</summary>
            <div className="advanced-body">
              <label className="field">
                Permutations
                <Input
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
                <Input
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
      </Card>
      <div id="analyze-results">
        {loading ? (
          <Card className="card">
            <LoadingState
              message={`Running ${permutations.toLocaleString()} permutations. This can take a minute.`}
            />
            <Progress
              value={undefined}
              className="progress is-indeterminate"
              style={{ marginTop: "var(--space-3)" }}
            />
          </Card>
        ) : readLoading ? (
          <Card className="card" aria-label="Loading analysis">
            <LoadingState message="Loading analysis results…" />
          </Card>
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
          style={{ marginBottom: "var(--space-4)" }}
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
        id="analyze-reachability"
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
        id="analyze-pooled-permutation"
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
        subtitle={
          "Counts models by direction of change. Result CSVs are not independent " +
          "models -- configuration variants of one base model share a row here."
        }
        exportName="direction-consistency"
        id="analyze-direction-consistency"
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
    <Card className="card" id={id}>
      <div className="card-head">
        <div>
          <h3>{title}</h3>
          <p className="card-sub">{subtitle}</p>
        </div>
        <div className="card-head-actions">
          <ExportButton name={exportName} targetId={id || exportName} />
        </div>
      </div>
      {children || <p className="muted small">{empty}</p>}
    </Card>
  );
}
