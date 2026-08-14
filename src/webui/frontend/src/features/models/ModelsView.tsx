import { FormEvent, useEffect, useRef, useState } from "react";
import {
  api,
  enc,
  Model,
  Provider,
  readModels,
  SmokeResult,
  writeModels,
} from "../../lib/api";
import { drawScreenshot, strokeWidthFor } from "../../lib/canvas";
import type { TabViewProps } from "../../lib/types";
import { SmokeTestResult } from "./SmokeTestResult";
import { ProviderCredentialsCard } from "./ProviderCredentialsCard";
import { AddModelForm } from "./AddModelForm";
import { ConfiguredModelsCard } from "./ConfiguredModelsCard";
import { Card } from "../../components/ui/card";
import { LoadingState } from "../../components/ui/spinner";
import { Alert, AlertDescription, AlertIcon, AlertTitle } from "../../components/ui/alert";
import { StageHeader } from "../shared/StageHeader";

const EXAMPLES: Array<[string, Model["coord_space"]]> = [
  ["openai/gpt-4o-mini", "pixel"],
  ["gemini/gemini-2.0-flash", "norm1000"],
  ["ollama/llama3.2-vision:11b", "pixel"],
];

export function ModelsView({
  onChange,
  onProvidersChange,
  dataset,
  screen,
  hidden,
}: TabViewProps & {
  onChange?: (models: Model[]) => void;
  onProvidersChange?: (providers: Provider[]) => void;
  dataset?: string;
  screen?: string;
}) {
  const [models, setModels] = useState<Model[]>(readModels);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providersLoading, setProvidersLoading] = useState(true);
  const [id, setId] = useState("");
  const [space, setSpace] = useState<Model["coord_space"]>("pixel");
  const [error, setError] = useState("");
  const [keys, setKeys] = useState<Record<string, string>>({});
  const modelInput = useRef<HTMLInputElement>(null);
  const [providerError, setProviderError] = useState("");
  const [smoke, setSmoke] = useState<{
    model: Model;
    loading?: boolean;
    result?: SmokeResult;
  } | null>(null);
  const loadProviders = async () => {
    setProvidersLoading(true);
    try {
      const next = await api<Provider[]>("/api/providers");
      setProviders(next);
      onProvidersChange?.(next);
      setProviderError("");
    } catch (e) {
      setProviders([]);
      setProviderError(e instanceof Error ? e.message : String(e));
    } finally {
      setProvidersLoading(false);
    }
  };
  useEffect(() => {
    void loadProviders();
  }, [onProvidersChange]);
  const save = (next: Model[]) => {
    setModels(next);
    writeModels(next);
    onChange?.(next);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const value = id.trim();
    if (!value) return;
    if (models.some((m) => m.id === value)) {
      setError(`${value} is already configured.`);
      return;
    }
    save([...models, { id: value, coord_space: space }]);
    setId("");
    setError("");
  };
  const setKey = async (provider: string) => {
    const value = keys[provider]?.trim();
    if (!value) return;
    try {
      await api("/api/keys", {
        method: "POST",
        body: JSON.stringify({ provider, value }),
      });
      setKeys((v) => ({ ...v, [provider]: "" }));
      await loadProviders();
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : String(e));
    }
  };
  const clearKey = async (provider: string) => {
    try {
      await api(`/api/keys/${enc(provider)}`, { method: "DELETE" });
      await loadProviders();
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : String(e));
    }
  };
  const runSmoke = async (model: Model) => {
    if (!dataset || !screen) {
      setSmoke({
        model,
        result: {
          ok: false,
          error: "Select a dataset with at least one screen first.",
        },
      });
      return;
    }
    setSmoke({ model, loading: true });
    const result = await api<SmokeResult>("/api/smoke-test", {
      method: "POST",
      body: JSON.stringify({
        dataset,
        model: model.id,
        screen,
        coord_space: model.coord_space,
      }),
    }).catch((e) => ({
      ok: false,
      error: e instanceof Error ? e.message : String(e),
    }));
    setSmoke({ model, result });
  };
  return (
    <section
      id="tab-models"
      className="tab min-w-0"
      aria-labelledby="head-models"
      hidden={hidden}
    >
      <StageHeader stage="models" title="Models">
        Configure the models to evaluate and check each one with a single real
        query before spending a full run. This catches a bad key, a wrong
        coordinate convention, or a malformed model id early.
      </StageHeader>
      {providersLoading ? <Card className="mt-4 p-4"><LoadingState label="Loading providers" /></Card> : <ProviderCredentialsCard
        providers={providers}
        providerError={providerError}
        keys={keys}
        setKeys={setKeys}
        setKey={(provider) => void setKey(provider)}
        clearKey={(provider) => void clearKey(provider)}
      />}
      <AddModelForm
        id={id}
        space={space}
        error={error}
        modelInput={modelInput}
        setId={setId}
        setSpace={setSpace}
        submit={submit}
      />
      <ConfiguredModelsCard
        models={models}
        modelInput={modelInput}
        setId={setId}
        setSpace={setSpace}
        runSmoke={(model) => void runSmoke(model)}
        removeModel={(model) =>
          save(models.filter((candidate) => candidate.id !== model.id))
        }
        examples={EXAMPLES}
      />
      <div id="smoke-test-result">
        {smoke && (
          <Card className="mt-4 p-4">
            <SmokeTestResult
              smoke={smoke}
              dataset={dataset}
              screen={screen}
              success={
                <SmokeSuccess
                  dataset={dataset}
                  screen={screen}
                  result={smoke.result!}
                  model={smoke.model}
                />
              }
            />
          </Card>
        )}
      </div>
    </section>
  );
}

function SmokeSuccess({
  dataset,
  screen,
  result,
  model,
}: {
  dataset?: string;
  screen?: string;
  result: SmokeResult;
  model: Model;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!canvas.current || !dataset || !screen) return;
    drawScreenshot(
      canvas.current,
      `/api/datasets/${enc(dataset)}/image/${enc(screen)}/baseline?_=${Date.now()}`,
      (ctx, img) => {
        if (result.box) {
          ctx.strokeStyle = "#157a41";
          ctx.lineWidth = strokeWidthFor(img);
          ctx.strokeRect(
            result.box[0],
            result.box[1],
            result.box[2] - result.box[0],
            result.box[3] - result.box[1],
          );
        }
        if (result.x_pred != null && result.y_pred != null) {
          ctx.fillStyle = "#b3221a";
          ctx.beginPath();
          ctx.arc(
            result.x_pred,
            result.y_pred,
            Math.max(6, img.width / 80),
            0,
            2 * Math.PI,
          );
          ctx.fill();
        }
      },
    );
  }, [dataset, screen, result]);
  return (
    <>
      <div className="flex items-center justify-between gap-3 pb-3">
        <div>
          <h3>Test result -- {model.id}</h3>
          <p className="text-sm text-[var(--muted)]">
            One query against <code>{screen}</code> at baseline.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={result.hit === 1 ? "text-[var(--ok)]" : result.hit === 0 ? "text-[var(--err)]" : "text-[var(--warn)]"}
          >
            {result.hit === 1
              ? "Hit"
              : result.hit === 0
                ? "Miss"
                : "Out of frame"}
          </span>
        </div>
      </div>
      {result.coord_space_mismatch && (
        <Alert variant="warning" className="mt-3">
          <AlertTitle>
            <AlertIcon variant="warning" />
            Coordinate-space mismatch
          </AlertTitle>
          <AlertDescription>
            This reply looks like <code>{result.coord_space_detected}</code>{" "}
            but the model is configured as{" "}
            <code>{result.coord_space_used || model.coord_space}</code>. Switch
            this model's coordinate space before a full run, or it will score
            near zero while appearing to answer normally.
          </AlertDescription>
        </Alert>
      )}
      <div className="flex min-w-0 flex-wrap gap-4">
        <div className="min-w-0 flex-1">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt>Target</dt>
            <dd>
              <b>{result.target_text}</b>
            </dd>
            <dt>Latency</dt>
            <dd>{(result.latency_seconds || 0).toFixed(2)}s</dd>
            <dt>Detected space</dt>
            <dd>
              <code>{result.coord_space_detected}</code>
            </dd>
            <dt>Raw reply</dt>
            <dd>
              <code>{result.raw_response || ""}</code>
            </dd>
          </dl>
        </div>
        <div>
          <div className="grid min-w-0 place-items-center rounded-[var(--radius-lg)] bg-[var(--panel-dark)] p-3">
            <canvas
              id="smoke-canvas"
              ref={canvas}
              style={{ maxHeight: "52vh", width: "auto" }}
            />
          </div>
          <div
            className="mt-2 flex justify-center gap-3 text-xs"
          >
            <span className="flex items-center gap-1 text-[var(--ok)]">
              <span className="size-2 rounded-full border border-current" />
              Ground truth
            </span>
            <span className="flex items-center gap-1 text-[var(--err)]">
              <span className="size-2 rounded-full bg-current" />
              Predicted point
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
