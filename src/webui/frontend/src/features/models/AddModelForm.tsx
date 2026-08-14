import type { FormEvent, RefObject } from "react";
import type { Model } from "../../lib/api";
import { Input } from "../../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
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
    <Card className="mt-4 rounded-[var(--radius-lg)] border-[var(--primary)] p-4">
      <div className="pb-3">
        <p className="mb-1 text-xs font-semibold uppercase tracking-[0.1em] text-[var(--primary)]">
          Model roster
        </p>
        <h3>Add a model</h3>
      </div>
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
            <p className="mt-1 text-xs text-[var(--muted)]">
              Any LiteLLM model string. To route through 9router, prefix the model id yourself, e.g.{" "}
              <code>9router/openai/gpt-4o-mini</code>.
            </p>
          </div>
          <div className="min-w-48">
            <label htmlFor="model-coord-space">Coordinate space</label>
            <Select value={space} onValueChange={(v) => setSpace(v as Model["coord_space"])}>
              <SelectTrigger id="model-coord-space">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="pixel">Pixel</SelectItem>
                <SelectItem value="norm1000">Normalized (0-1000 grid)</SelectItem>
              </SelectContent>
            </Select>
            <p className="mt-1 text-xs text-[var(--muted)]">Gemini, Qwen and GLM answer normalized.</p>
          </div>
          <Button type="submit">Add model</Button>
        </div>
      </form>
      <div id="add-model-error">{error && <Alert className="mt-3 border-[var(--danger)]">{error}</Alert>}</div>
    </Card>
  );
}
