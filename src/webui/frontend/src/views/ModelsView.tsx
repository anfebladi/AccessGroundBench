import { FormEvent, useEffect, useRef, useState } from "react";
import {
  api,
  enc,
  Model,
  Provider,
  readModels,
  SmokeResult,
  writeModels,
} from "../lib/api";
import { drawScreenshot, strokeWidthFor } from "../lib/canvas";
import type { TabViewProps } from "../lib/types";
import styles from "./models.module.css";
import { SmokeTestResult } from "../features/models/SmokeTestResult";
import { ProviderCredentialsCard } from "../features/models/ProviderCredentialsCard";
import { AddModelForm } from "../features/models/AddModelForm";
import { ConfiguredModelsCard } from "../features/models/ConfiguredModelsCard";

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
    try {
      const next = await api<Provider[]>("/api/providers");
      setProviders(next);
      onProvidersChange?.(next);
      setProviderError("");
    } catch (e) {
      setProviders([]);
      setProviderError(e instanceof Error ? e.message : String(e));
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
      className={`tab ${styles.root}`}
      aria-labelledby="head-models"
      hidden={hidden}
    >
      <div className="view-head">
        <h2 id="head-models">Models</h2>
        <p className="lead">
          Configure the models to evaluate and check each one with a single real
          query before spending a full run. This catches a bad key, a wrong
          coordinate convention, or a malformed model id early.
        </p>
      </div>
      <ProviderCredentialsCard
        providers={providers}
        providerError={providerError}
        keys={keys}
        setKeys={setKeys}
        setKey={(provider) => void setKey(provider)}
        clearKey={(provider) => void clearKey(provider)}
      />
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
          <div className="card">
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
          </div>
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
      <div className="card-head">
        <div>
          <h3>Test result -- {model.id}</h3>
          <p className="card-sub">
            One query against <code>{screen}</code> at baseline.
          </p>
        </div>
        <div className="card-head-actions">
          <span
            className={`badge ${result.hit === 1 ? "ok" : result.hit === 0 ? "err" : "warn"}`}
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
        <div className="note note-warn">
          <span className="note-label">Warning</span>{" "}
          <b>Coordinate-space mismatch.</b> This reply looks like{" "}
          <code>{result.coord_space_detected}</code> but the model is configured
          as <code>{result.coord_space_used || model.coord_space}</code>. Switch
          this model's coordinate space before a full run, or it will score near
          zero while appearing to answer normally.
        </div>
      )}
      <div className="row">
        <div className="grow">
          <dl className="kv">
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
          <div className="image-frame">
            <canvas
              id="smoke-canvas"
              ref={canvas}
              style={{ maxHeight: "52vh", width: "auto" }}
            />
          </div>
          <div
            className="overlay-legend"
            style={{ justifyContent: "center", marginTop: "var(--space-2)" }}
          >
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
      </div>
    </>
  );
}
