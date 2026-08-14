import type { Dispatch, SetStateAction } from "react";
import type { Provider } from "../../lib/api";
import { cn } from "../../lib/utils";
import { Input } from "../../components/ui/input";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Card } from "../../components/ui/card";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "../../components/ui/table";
import { Alert } from "../../components/ui/alert";
import { DocDialog } from "../../components/ui/doc-dialog";

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
    <Card className="mt-4 rounded-[var(--radius-lg)] p-4">
      <div className="flex items-center justify-between gap-3 pb-3">
        <div>
          <h3>Providers</h3>
          <p className="text-sm text-[var(--muted)]">
            Session keys stay in this server's memory and are never written to
            disk.
          </p>
        </div>
      </div>
      <div className="w-full overflow-x-auto">
        <Table id="provider-table">
          <TableHeader><TableRow><TableHead>Provider</TableHead><TableHead>Environment variable</TableHead><TableHead>Status</TableHead><TableHead>Session key</TableHead></TableRow></TableHeader>
          <TableBody>
            {providerError ? (
              <TableRow>
                <TableCell colSpan={4}>
                  <Alert className="border-[var(--danger)]">
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
                    <TableCell>
                      <code>{p.env_vars?.join(", ") || p.env_var}</code>
                      {name === "9router" && (
                        <p className="mt-1 text-xs text-[var(--muted)]">
                          <code>NINEROUTER_BASE_URL</code> must be set in{" "}
                          <code>.env</code> — it can't be set as a session key
                          below. See{" "}
                          <DocDialog
                            doc="9router.md"
                            trigger={
                              <button
                                type="button"
                                className="cursor-pointer underline decoration-dotted underline-offset-2"
                              >
                                <code>docs/9router.md</code>
                              </button>
                            }
                          />{" "}
                          for how to run 9router and get an API key.
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                        <Badge
                          className={cn(
                            status === "From .env"
                              ? "text-green-700"
                              : status === "Session key"
                                ? "rounded-none bg-transparent px-0 py-0 text-green-700"
                                : "rounded-none bg-transparent px-0 py-0 text-gray-500",
                          )}
                        >
                          {status}
                        </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
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
