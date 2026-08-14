import { FormEvent, useEffect, useState } from "react";
import { api, CollectPreflight, StartedRun } from "../../lib/api";
import { RunMonitor } from "../shared/run-monitor/RunMonitor";
import type { TabViewProps } from "../../lib/types";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Alert } from "../../components/ui/alert";
import { Skeleton } from "../../components/ui/skeleton";
import { Badge } from "../../components/ui/badge";
export function CollectView({
  onRunFinished,
  hidden,
}: TabViewProps & {
  onRunFinished?: (status: string) => void;
}) {
  const [screens, setScreens] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [dry, setDry] = useState(true);
  const [rebuild, setRebuild] = useState(false);
  const [preflight, setPreflight] = useState<CollectPreflight | null>(null);
  const [error, setError] = useState("");
  const [run, setRun] = useState<StartedRun | null>(null);
  const [checking, setChecking] = useState(false);
  const [starting, setStarting] = useState(false);
  useEffect(() => {
    const c = new AbortController();
    void api<{ all_screens: string[] }>("/api/collect/screens", {
      signal: c.signal,
    })
      .then((v) => setScreens(v.all_screens || []))
      .catch(() => {
        if (!c.signal.aborted) setScreens([]);
      });
    return () => c.abort();
  }, []);
  const check = async () => {
    setChecking(true);
    setPreflight(null);
    try {
      setPreflight(await api<CollectPreflight>("/api/collect/preflight"));
    } catch (e) {
      setPreflight({
        adb_available: false,
        error: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setChecking(false);
    }
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!name.trim()) {
      setError("Enter a dataset name.");
      return;
    }
    setStarting(true);
    try {
      setRun(
        await api<StartedRun>("/api/collect/runs", {
          method: "POST",
          body: JSON.stringify({
            name: name.trim(),
            screens: selected,
            dry_run: dry,
            rebuild_manifest: rebuild,
          }),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };
  const devices = preflight?.devices || [];
  const authorized = devices.filter((d) => d.status === "device");
  return (
    <section
      id="tab-collect"
      className="tab min-w-0"
      aria-labelledby="head-collect"
      hidden={hidden}
    >
      <div className="view-head mb-[var(--space-5)] max-w-[var(--prose-max)]">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--primary)]">Capture evidence</p>
        <h2 id="head-collect" className="text-[length:var(--text-display)] leading-[var(--lh-display)] tracking-[var(--ls-display)] max-[767px]:text-[1.375rem]">Collect</h2>
        <p className="mt-2 font-[var(--font-ui)] text-[length:var(--text-lead)] leading-[var(--lh-lead)] text-[var(--text-2)]">
          Capture a new dataset from a live Android emulator. Collection always
          writes to <code>datasets/&lt;name&gt;/</code>, so it can never
          overwrite the shipped dataset or an archived run.
        </p>
      </div>
      <Card className="mt-4 p-4">
        <div className="flex items-center justify-between gap-3 pb-3">
          <div>
            <h3>Emulator preflight</h3>
            <p className="text-sm text-[var(--muted)]">
              Checks that adb sees an authorized device.
            </p>
          </div>
          <div>
            <Button
              type="button"
              variant="secondary"
              id="collect-preflight-btn"
              onClick={() => void check()}
              disabled={checking}
            >
              {checking ? "Checking…" : "Check emulator"}
            </Button>
          </div>
        </div>
        <div id="collect-preflight-result">
          {checking && <div aria-label="Checking adb"><Alert className="text-sm text-[var(--muted)]">Checking adb...</Alert><Skeleton className="h-4 w-full" /></div>}
          {preflight &&
            !checking &&
            (!preflight.adb_available ? (
              <>
                <Badge className="text-[var(--err)]">adb not found</Badge>
                <p className="text-sm text-[var(--muted)]">
                  {preflight.error ||
                    "Install the Android platform tools and put adb on PATH."}
                </p>
              </>
            ) : preflight.error ? (
              <>
                <Badge className="text-[var(--warn)]">
                  adb found, but listing devices failed
                </Badge>
                <p className="text-sm text-[var(--muted)]">
                  <code>{preflight.adb_path}</code>
                </p>
                <p className="text-sm text-[var(--muted)]">{preflight.error}</p>
              </>
            ) : authorized.length ? (
              <>
                <Badge className="text-[var(--ok)]">
                  {authorized.length} authorized device
                  {authorized.length === 1 ? "" : "s"}
                </Badge>
                <ul className="text-sm text-[var(--muted)]">
                  {authorized.map((d) => (
                    <li key={d.serial}>
                      <code>{d.serial}</code>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <>
                <Badge className="text-[var(--warn)]">
                  adb is working, but no authorized device
                </Badge>
                <ul className="text-sm text-[var(--muted)]">
                  {devices.map((d) => (
                    <li key={d.serial}>
                      <code>{d.serial}</code> -- {d.status}
                    </li>
                  ))}
                  {!devices.length && <li>No devices listed.</li>}
                </ul>
              </>
            ))}
        </div>
        <div className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm">
          <span className="mr-2 font-semibold">Prerequisites</span> Not verifiable from
          here: Pixel 6 / API 34 / 1080x2400 at 420 dpi, a signed-in Google
          account, and Messages, Gmail and Maps each opened once to clear their
          first-run dialogs. See <code>docs/collection.md</code>.
        </div>
      </Card>
      <Card className="mt-4 border-[var(--primary)] p-4">
        <div className="pb-3">
          <h3>New collection</h3>
        </div>
        <form id="collect-form" onSubmit={submit}>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label htmlFor="collect-name">Dataset name</label>
              <Input
                id="collect-name"
                placeholder="my-app"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <p className="mt-1 text-xs text-[var(--muted)]">
                Captures land in <code>datasets/&lt;name&gt;/</code>.
              </p>
            </div>
            <div>
              <label htmlFor="collect-screens">Screens</label>
              <NativeSelect
                id="collect-screens"
                multiple
                size={6}
                value={selected}
                onChange={(e) =>
                  setSelected(
                    Array.from(e.target.selectedOptions).map((o) => o.value),
                  )
                }
              >
                {screens.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </NativeSelect>
              <p className="mt-1 text-xs text-[var(--muted)]">Select none to capture every screen.</p>
            </div>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                id="collect-dry-run"
                checked={dry}
                onChange={(e) => setDry(e.target.checked)}
              />
              <span>
                Dry run
                <span className="block text-xs text-[var(--muted)]">
                  Validates the run plan without touching the emulator.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                id="collect-rebuild-manifest"
                checked={rebuild}
                onChange={(e) => setRebuild(e.target.checked)}
              />
              <span>
                Rebuild manifest only
                <span className="block text-xs text-[var(--muted)]">
                  Recomputes drift from existing captures. Takes no new
                  screenshots.
                </span>
              </span>
            </label>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="submit" disabled={starting}>
              {starting ? "Starting…" : "Start collection"}
            </Button>
          </div>
        </form>
        <div id="collect-error">
          {error && <Alert className="rounded-md border border-[var(--err)]/40 bg-[var(--err)]/10 p-3 text-sm text-[var(--err)]">{error}</Alert>}
        </div>
        <div id="collect-command" />
      </Card>
      <div id="collect-run">
        {run && (
          <RunMonitor
            runId={run.run_id}
            command={run.equivalent_command}
            onFinish={onRunFinished}
          />
        )}
      </div>
    </section>
  );
}
