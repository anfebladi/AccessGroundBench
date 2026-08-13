import type { FormEvent, RefObject } from "react";
import type { Model } from "../../lib/api";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Alert } from "../../components/ui/alert";

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
    <Card className="mt-4 border-[var(--primary)] p-4"><div className="pb-3"><h3>Add a model</h3></div>
      <form id="add-model-form" onSubmit={submit}>
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-0 flex-1">
            <label htmlFor="model-id-input">Model id</label>
            <Input
              id="model-id-input"
              ref={modelInput}
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="openai/gpt-4o-mini"
              required
            />
            <p className="mt-1 text-xs text-[var(--muted)]">Any LiteLLM model string, or a <code>9router/</code> / <code>openai_compatible/</code> route.</p>
          </div>
          <div className="min-w-48">
            <label htmlFor="model-coord-space">Coordinate space</label>
            <NativeSelect id="model-coord-space" value={space} onChange={(e) => setSpace(e.target.value as Model["coord_space"]) }>
              <option value="pixel">Pixel</option>
              <option value="norm1000">Normalized (0-1000 grid)</option>
            </NativeSelect>
            <p className="mt-1 text-xs text-[var(--muted)]">Gemini, Qwen and GLM answer normalized.</p>
          </div>
          <Button type="submit">Add model</Button>
        </div>
      </form>
      <div id="add-model-error">{error && <Alert className="mt-3 border-[var(--danger)]">{error}</Alert>}</div>
    </Card>
  );
}
