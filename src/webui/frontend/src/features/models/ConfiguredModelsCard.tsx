import type { RefObject } from "react";
import type { Model } from "../../lib/api";
import styles from "./models.module.css";

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
                  {models.map((model) => (
                    <tr key={model.id}>
                      <td>
                        <code>{model.id}</code>
                      </td>
                      <td>
                        {model.coord_space === "norm1000"
                          ? "Normalized (0-1000)"
                          : "Pixel"}
                      </td>
                      <td className={styles.modelActions}>
                        <button
                          type="button"
                          className="secondary small"
                          data-test={model.id}
                          onClick={() => runSmoke(model)}
                        >
                          Test model
                        </button>
                        <button
                          type="button"
                          className="ghost small"
                          data-remove={model.id}
                          onClick={() => removeModel(model)}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className={`field-hint ${styles.hint}`}>
              Test model sends one real query against one target and draws the
              answer over the ground-truth box.
            </p>
          </>
        ) : (
          <div className="empty-state">
            <p className="empty-state-title">No models configured yet</p>
            <p className="empty-state-body">
              A model id is a LiteLLM model string. Add one above, or start from
              an example:
            </p>
            <div className="empty-state-action">
              {examples.map(([example, exampleSpace]) => (
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
  );
}
