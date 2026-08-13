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

const EXAMPLES: Array<[string, Model["coord_space"]]> = [
  ["openai/gpt-4o-mini", "pixel"],
  ["gemini/gemini-2.0-flash", "norm1000"],
  ["ollama/llama3.2-vision:11b", "pixel"],
];

export function ModelsView({
  onChange,
  dataset,
  screen,
  hidden,
}: TabViewProps & {
  onChange?: (models: Model[]) => void;
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
      setProviders(await api<Provider[]>("/api/providers"));
      setProviderError("");
    } catch (e) {
      setProviders([]);
      setProviderError(e instanceof Error ? e.message : String(e));
    }
  };
  useEffect(() => {
    void loadProviders();
  }, []);
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
    <section id="tab-models" className="tab" aria-labelledby="head-models" hidden={hidden}>
      <div className="view-head">
        <h2 id="head-models">Models</h2>
        <p className="lead">
          Configure the models to evaluate and check each one with a single real
          query before spending a full run. This catches a bad key, a wrong
          coordinate convention, or a malformed model id early.
        </p>
      </div>
      <div className="card">
        <div className="card-head">
          <div>
            <h3>Providers</h3>
            <p className="card-sub">
              Session keys stay in this server's memory and are never written to
              disk.
            </p>
          </div>
        </div>
        <div className="table-wrap">
          <table id="provider-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Environment variable</th>
                <th>Status</th>
                <th>Session key</th>
              </tr>
            </thead>
            <tbody>
              {providerError ? (
                <tr>
                  <td colSpan={4}>
                    <p className="state-error" role="alert">
                      {providerError}
                    </p>
                  </td>
                </tr>
              ) : (
                providers.map((p) => {
                  const name = p.provider || p.name || "";
                  const configured =
                    p.configured || p.env_configured || p.session_configured;
                  const status = p.env_configured
                    ? "From .env"
                    : p.session_configured
                      ? "Session key"
                      : "Not configured";
                  return (
                    <tr key={name}>
                      <td>
                        <b>{name}</b>
                      </td>
                      <td>
                        <code>{p.env_vars?.join(", ") || p.env_var}</code>
                      </td>
                      <td>
                        <span
                          className={`badge ${configured ? "ok" : "muted"}`}
                        >
                          {status}
                        </span>
                      </td>
                      <td>
                        <div
                          style={{
                            display: "flex",
                            gap: "var(--space-2)",
                            alignItems: "center",
                          }}
                        >
                          <input
                            type="password"
                            placeholder="Paste key for this session"
                            aria-label={`Session key for ${name}`}
                            value={keys[name] || ""}
                            onChange={(e) =>
                              setKeys({ ...keys, [name]: e.target.value })
                            }
                          />
                          <button
                            type="button"
                            className="secondary small"
                            data-set={name}
                            onClick={() => void setKey(name)}
                          >
                            Set
                          </button>
                          {p.session_configured && (
                            <button
                              type="button"
                              className="secondary small"
                              data-clear={name}
                              onClick={() => void clearKey(name)}
                            >
                              Clear
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card card-primary">
        <div className="card-head">
          <h3>Add a model</h3>
        </div>
        <form id="add-model-form" onSubmit={submit}>
          <div className="field-row">
            <div className="field field-wide">
              <label htmlFor="model-id-input">Model id</label>
              <input
                id="model-id-input"
                ref={modelInput}
                value={id}
                onChange={(e) => setId(e.target.value)}
                placeholder="openai/gpt-4o-mini"
                required
              />
              <p className="field-hint">
                Any LiteLLM model string, or a <code>9router/</code> /{" "}
                <code>openai_compatible/</code> route.
              </p>
            </div>
            <div className="field">
              <label htmlFor="model-coord-space">Coordinate space</label>
              <select
                id="model-coord-space"
                value={space}
                onChange={(e) =>
                  setSpace(e.target.value as Model["coord_space"])
                }
              >
                <option value="pixel">Pixel</option>
                <option value="norm1000">Normalized (0-1000 grid)</option>
              </select>
              <p className="field-hint">
                Gemini, Qwen and GLM answer normalized.
              </p>
            </div>
            <button type="submit">Add model</button>
          </div>
        </form>
        <div id="add-model-error">
          {error && (
            <p className="state-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
      <div className="card">
        <div className="card-head">
          <h3>Configured models</h3>
        </div>
        <div id="model-list">
          {models.length ? (
            <>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Coordinate space</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {models.map((m) => (
                      <tr key={m.id}>
                        <td>
                          <code>{m.id}</code>
                        </td>
                        <td>
                          {m.coord_space === "norm1000"
                            ? "Normalized (0-1000)"
                            : "Pixel"}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <button
                            type="button"
                            className="secondary small"
                            data-test={m.id}
                            onClick={() => void runSmoke(m)}
                          >
                            Test model
                          </button>
                          <button
                            type="button"
                            className="ghost small"
                            data-remove={m.id}
                            onClick={() =>
                              save(models.filter((x) => x.id !== m.id))
                            }
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="field-hint" style={{ marginTop: "var(--space-3)" }}>
                Test model sends one real query against one target and draws the
                answer over the ground-truth box.
              </p>
            </>
          ) : (
            <div className="empty-state">
              <p className="empty-state-title">No models configured yet</p>
              <p className="empty-state-body">
                A model id is a LiteLLM model string. Add one above, or start
                from an example:
              </p>
              <div className="empty-state-action">
                {EXAMPLES.map(([example, exampleSpace]) => (
                  <button
                    type="button"
                    className="secondary small"
                    key={example}
                    onClick={() => {
                      setId(example);
                      setSpace(exampleSpace);
                      modelInput.current?.focus();
                    }}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
      <div id="smoke-test-result">
        {smoke && (
          <div className="card">
            {smoke.loading ? (
              <p className="state-loading">
                Querying {smoke.model.id} on {screen}...
              </p>
            ) : smoke.result?.ok ? (
              <SmokeSuccess
                dataset={dataset}
                screen={screen}
                result={smoke.result}
                model={smoke.model}
              />
            ) : (
              <p className="state-error" role="alert">
                {smoke.result?.error || "The model call failed."}
              </p>
            )}
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
