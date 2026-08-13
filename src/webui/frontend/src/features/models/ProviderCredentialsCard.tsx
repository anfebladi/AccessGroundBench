import type { Dispatch, SetStateAction } from "react";
import type { Provider } from "../../lib/api";
import styles from "./models.module.css";
import { Input } from "../../components/ui/input";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Card } from "../../components/ui/card";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "../../components/ui/table";
import { Alert } from "../../components/ui/alert";

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
    <Card className="card">
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
        <Table id="provider-table">
          <TableHeader><TableRow><TableHead>Provider</TableHead><TableHead>Environment variable</TableHead><TableHead>Status</TableHead><TableHead>Session key</TableHead></TableRow></TableHeader>
          <TableBody>
            {providerError ? (
              <TableRow>
                <TableCell colSpan={4}>
                  <Alert className="state-error">
                    {providerError}
                  </Alert>
                </TableCell>
              </TableRow>
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
                  <TableRow key={name}>
                    <TableCell><b>{name}</b></TableCell>
                    <TableCell><code>{p.env_vars?.join(", ") || p.env_var}</code></TableCell>
                    <TableCell>
                        <Badge className={configured ? "text-green-700" : "text-gray-500"}>
                        {status}
                        </Badge>
                    </TableCell>
                    <TableCell>
                      <div className={styles.providerActions}>
                        <Input
                          type="password"
                          placeholder="Paste key for this session"
                          aria-label={`Session key for ${name}`}
                          value={keys[name] || ""}
                          onChange={(e) =>
                            setKeys((current) => ({ ...current, [name]: e.target.value }))
                          }
                        />
                        <Button type="button" variant="secondary" size="sm" data-set={name} onClick={() => setKey(name)}>Set</Button>
                        {p.session_configured && (
                          <Button type="button" variant="secondary" size="sm" data-clear={name} onClick={() => clearKey(name)}>Clear</Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}
