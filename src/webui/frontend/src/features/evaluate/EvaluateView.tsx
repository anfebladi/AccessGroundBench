import { FormEvent, useEffect, useState } from "react";
import { api, enc, Model, Preflight, StartedRun } from "../../lib/api";
import { RunMonitor } from "../shared/run-monitor/RunMonitor";
import type { PreflightSummary, TabViewProps } from "../../lib/types";
import { EvaluatePreflight } from "./EvaluatePreflight";
import { Input } from "../../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Alert, AlertDescription, AlertIcon, AlertTitle } from "../../components/ui/alert";
import {
  Collapsible,
  CollapsibleContent,
  DisclosureTrigger,
} from "../../components/ui/collapsible";
import { StageHeader } from "../shared/StageHeader";

interface EvaluateViewProps extends TabViewProps {
  dataset: string;
  models: Model[];
  onRunFinished?: () => void;
  onPreflightSummary?: (summary: PreflightSummary) => void;
}

export function EvaluateView({
  dataset,
  models,
  onRunFinished,
  onPreflightSummary,
  hidden,
}: EvaluateViewProps) {
  const [model, setModel] = useState(models[0]?.id || "");
  const [mode, setMode] = useState("vision");
  const [coord, setCoord] = useState<Model["coord_space"]>(
    models[0]?.coord_space || "pixel",
  );
  const [trials, setTrials] = useState(1);
  const [pace, setPace] = useState(0);
  const [fresh, setFresh] = useState(false);
  const [forceUnlock, setForceUnlock] = useState(false);
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [preflightKey, setPreflightKey] = useState("");
  const [error, setError] = useState("");
  const [run, setRun] = useState<StartedRun | null>(null);
  const [starting, setStarting] = useState(false);
  useEffect(() => {
    const found = models.find((m) => m.id === model);
    if (found) setCoord(found.coord_space);
    else if (!models.length) setModel("");
  }, [model, models]);
  useEffect(() => {
    setPreflight(null);
    setPreflightKey("");
    if (!dataset || !model) return;
    const key = `${dataset}\u0000${model}\u0000${mode}`;
    const controller = new AbortController();
    setError("");
    void api<Preflight>(
      `/api/datasets/${enc(dataset)}/preflight?model=${enc(model)}&use_a11y_tree=${mode === "tree"}`,
      { signal: controller.signal },
    )
      .then((value) => {
        setPreflight(value);
        setPreflightKey(key);
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setPreflight(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => controller.abort();
  }, [dataset, model, mode]);
  useEffect(() => {
    if (!onPreflightSummary) return;
    if (error) {
      onPreflightSummary({ text: error, tone: "error" });
      return;
    }
    const currentKey = `${dataset}\u0000${model}\u0000${mode}`;
    if (
      preflightKey !== currentKey ||
      !preflight ||
      !preflight.expected_total
    ) {
      onPreflightSummary({ text: "", tone: "muted" });
      return;
    }
    const remaining = preflight.expected_total - preflight.already_done;
    onPreflightSummary({
      text:
        preflight.already_done > 0
          ? `${remaining} queries left`
          : `${preflight.expected_total} queries planned`,
      tone: preflight.already_done > 0 ? "info" : "muted",
    });
  }, [
    dataset,
    model,
    mode,
    preflight,
    preflightKey,
    error,
    onPreflightSummary,
  ]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!model) {
      setError("Add a model on the Models step before starting a run.");
      return;
    }
    setStarting(true);
    try {
      setRun(
        await api<StartedRun>("/api/runs", {
          method: "POST",
          body: JSON.stringify({
            dataset,
            model,
            use_a11y_tree: mode === "tree",
            trials,
            pace_seconds: pace,
            coord_space: coord,
            fresh,
            force_unlock: forceUnlock,
          }),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };
  const remaining = preflight
    ? preflight.expected_total - preflight.already_done
    : 0;
  return (
    <section id="tab-evaluate" className="tab min-w-0" aria-labelledby="head-evaluate" hidden={hidden}>
      <StageHeader stage="evaluate" title="Evaluate">
        Query one model against every target on every profile. Runs append as
        they go and resume where they stopped, so an interrupted run never
        loses the calls it already paid for.
      </StageHeader>
      <Card className="mt-4 border-[var(--primary)] p-4">
        <form id="evaluate-form" onSubmit={submit}>
          <div className="flex flex-wrap items-end gap-4">
            <div className="min-w-0 flex-1">
              <label htmlFor="eval-model-select">Model</label>
              <Select value={model} disabled={!models.length} onValueChange={setModel}>
                <SelectTrigger id="eval-model-select">
                  <SelectValue placeholder={models.length ? "Select model" : "No models configured"} />
                </SelectTrigger>
                <SelectContent>
                  {models.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-48">
              <label htmlFor="eval-mode-select">Prompt mode</label>
              <Select value={mode} onValueChange={setMode}>
                <SelectTrigger id="eval-mode-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="vision">Vision only</SelectItem>
                  <SelectItem value="tree">Vision + a11y tree</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              type="submit"
              id="eval-start"
              disabled={!models.length || starting}
            >
              {starting ? "Starting…" : "Start evaluation"}
            </Button>
          </div>
          <Collapsible className="advanced mt-4">
            <DisclosureTrigger>Advanced options</DisclosureTrigger>
            <CollapsibleContent className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <label htmlFor="eval-trials">Trials per query</label>
                  <Input
                    id="eval-trials"
                    type="number"
                    min={1}
                    value={trials}
                    onChange={(e) => setTrials(Number(e.target.value) || 1)}
                  />
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    Runs each query N times; above 1, answers are
                    majority-voted and flip rate (% of trials disagreeing
                    with the majority) is reported. Costs N&times; the API
                    calls.
                  </p>
                </div>
                <div>
                  <label htmlFor="eval-pace">Pace (seconds)</label>
                  <Input
                    id="eval-pace"
                    type="number"
                    min={0}
                    step={0.1}
                    value={pace}
                    onChange={(e) => setPace(Number(e.target.value) || 0)}
                  />
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    Delay between calls, for rate-limited providers.
                  </p>
                </div>
                <div>
                  <label htmlFor="eval-coord-space">Coordinate space</label>
                  <Select
                    value={coord}
                    onValueChange={(v) => setCoord(v as Model["coord_space"])}
                  >
                    <SelectTrigger id="eval-coord-space">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pixel">Pixel</SelectItem>
                      <SelectItem value="norm1000">Normalized (0-1000)</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    Set per run, from the model's configuration.
                  </p>
                </div>
              </div>
              <div
                className="grid gap-4 md:grid-cols-2"
              >
                <label className="flex items-start gap-2">
                  <input
                    id="eval-fresh"
                    type="checkbox"
                    checked={fresh}
                    onChange={(e) => setFresh(e.target.checked)}
                  />
                  <span>
                    Start fresh
                    <span className="block text-xs text-[var(--muted)]">
                      Discards existing rows and re-runs every query. You pay
                      the full call count again.
                    </span>
                  </span>
                </label>
                <div id="eval-unlock-field">
                  {preflight?.lock_present && (
                    <label className="flex items-start gap-2">
                      <input
                        id="eval-force-unlock"
                        type="checkbox"
                        checked={forceUnlock}
                        onChange={(e) => setForceUnlock(e.target.checked)}
                      />
                      <span>
                        Override stale lock
                        <span className="block text-xs text-[var(--muted)]">
                          Only if you are certain no other run is writing this
                          file.
                        </span>
                      </span>
                    </label>
                  )}
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>
        </form>
        <div id="eval-preflight">
          <EvaluatePreflight preflight={preflight} />
        </div>
        <div id="eval-error">
          {error && (
            <Alert variant="danger">
              <AlertTitle>
                <AlertIcon variant="danger" />
                Evaluation failed
              </AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </div>
        <div id="eval-command" />
      </Card>
      <div id="eval-run">
        {run && (
          <RunMonitor
            runId={run.run_id}
            command={run.equivalent_command}
            expectedTotal={preflight?.expected_total}
            alreadyDone={fresh ? 0 : preflight?.already_done || 0}
            onFinish={onRunFinished}
          />
        )}
      </div>
    </section>
  );
}
