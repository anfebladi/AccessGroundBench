import type { FormEvent, RefObject } from "react";
import type { Model } from "../../lib/api";

export function AddModelForm({
  id,
  space,
  error,
  modelInput,
  setId,
  setSpace,
  submit,
}: {
  id: string;
  space: Model["coord_space"];
  error: string;
  modelInput: RefObject<HTMLInputElement | null>;
  setId: (value: string) => void;
  setSpace: (value: Model["coord_space"]) => void;
  submit: (event: FormEvent) => void;
}) {
  return (
    <div className="card card-primary">
      <div className="card-head"><h3>Add a model</h3></div>
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
            <p className="field-hint">Any LiteLLM model string, or a <code>9router/</code> / <code>openai_compatible/</code> route.</p>
          </div>
          <div className="field">
            <label htmlFor="model-coord-space">Coordinate space</label>
            <select id="model-coord-space" value={space} onChange={(e) => setSpace(e.target.value as Model["coord_space"])}>
              <option value="pixel">Pixel</option>
              <option value="norm1000">Normalized (0-1000 grid)</option>
            </select>
            <p className="field-hint">Gemini, Qwen and GLM answer normalized.</p>
          </div>
          <button type="submit">Add model</button>
        </div>
      </form>
      <div id="add-model-error">{error && <p className="state-error" role="alert">{error}</p>}</div>
    </div>
  );
}
