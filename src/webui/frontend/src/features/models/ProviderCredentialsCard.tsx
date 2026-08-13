import type { Dispatch, SetStateAction } from "react";
import type { Provider } from "../../lib/api";
import styles from "./models.module.css";

export function ProviderCredentialsCard({
  providers,
  providerError,
  keys,
  setKeys,
  setKey,
  clearKey,
}: {
  providers: Provider[];
  providerError: string;
  keys: Record<string, string>;
  setKeys: Dispatch<SetStateAction<Record<string, string>>>;
  setKey: (provider: string) => void;
  clearKey: (provider: string) => void;
}) {
  return (
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
                    <td><b>{name}</b></td>
                    <td><code>{p.env_vars?.join(", ") || p.env_var}</code></td>
                    <td>
                      <span className={`badge ${configured ? "ok" : "muted"}`}>
                        {status}
                      </span>
                    </td>
                    <td>
                      <div className={styles.providerActions}>
                        <input
                          type="password"
                          placeholder="Paste key for this session"
                          aria-label={`Session key for ${name}`}
                          value={keys[name] || ""}
                          onChange={(e) =>
                            setKeys((current) => ({ ...current, [name]: e.target.value }))
                          }
                        />
                        <button type="button" className="secondary small" data-set={name} onClick={() => setKey(name)}>Set</button>
                        {p.session_configured && (
                          <button type="button" className="secondary small" data-clear={name} onClick={() => clearKey(name)}>Clear</button>
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
  );
}
