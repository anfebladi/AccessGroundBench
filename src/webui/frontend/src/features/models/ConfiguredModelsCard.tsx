import type { RefObject } from "react";
import type { Model } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "../../components/ui/table";
import { Card } from "../../components/ui/card";

interface ConfiguredModelsCardProps {
  models: Model[];
  modelInput: RefObject<HTMLInputElement | null>;
  setId: (value: string) => void;
  setSpace: (value: Model["coord_space"]) => void;
  runSmoke: (model: Model) => void;
  removeModel: (model: Model) => void;
  examples: Array<[string, Model["coord_space"]]>;
}

export function ConfiguredModelsCard({
  models,
  modelInput,
  setId,
  setSpace,
  runSmoke,
  removeModel,
  examples,
}: ConfiguredModelsCardProps) {
  return (
    <Card className="mt-4 rounded-[var(--radius-lg)] p-4">
      <div className="flex items-center justify-between gap-3 pb-3">
        <div>
          <h3>Configured models</h3>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Use a smoke test to validate coordinates before a full evaluation.
          </p>
        </div>
      </div>
      <div id="model-list">
        {models.length ? (
          <>
            <div className="w-full overflow-x-auto">
              <Table>
                <TableHeader><TableRow><TableHead>Model</TableHead><TableHead>Coordinate space</TableHead><TableHead /></TableRow></TableHeader>
                <TableBody>
                  {models.map((model) => (
                    <tr key={model.id}>
                      <TableCell>
                        <code>{model.id}</code>
                      </TableCell><TableCell>
                        {model.coord_space === "norm1000"
                          ? "Normalized (0-1000)"
                          : "Pixel"}
                      </TableCell><TableCell className="text-right">
                        <Button
                          type="button"
                          variant="secondary" size="sm"
                          data-test={model.id}
                          onClick={() => runSmoke(model)}
                        >
                          Test model
                        </Button><Button
                          type="button"
                          variant="ghost" size="sm"
                          data-remove={model.id}
                          onClick={() => removeModel(model)}
                        >
                          Remove
                        </Button>
                      </TableCell>
                    </tr>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="mt-3 text-sm text-[var(--muted)]">
              Test model sends one real query against one target and draws the
              answer over the ground-truth box.
            </p>
          </>
        ) : (
          <div className="rounded-md border border-dashed border-[var(--border)] p-6 text-center">
            <p className="font-medium">No models configured yet</p>
            <p className="mt-1 text-sm text-[var(--muted)]">
              A model id is a LiteLLM model string. Add one above, or start from
              an example:
            </p>
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              {examples.map(([example, exampleSpace]) => (
                <Button
                  type="button"
                  variant="secondary" size="sm"
                  key={example}
                  onClick={() => {
                    setId(example);
                    setSpace(exampleSpace);
                    modelInput.current?.focus();
                  }}
                >
                  {example}
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
