import { FormEvent, useEffect, useState } from "react";
import { api, CollectPreflight, StartedRun } from "../../lib/api";
import { RunMonitor } from "../shared/run-monitor/RunMonitor";
import type { TabViewProps } from "../../lib/types";
import styles from "./collect.module.css";
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
      className={`tab ${styles.root}`}
      aria-labelledby="head-collect"
      hidden={hidden}
    >
      <div className="view-head">
        <h2 id="head-collect">Collect</h2>
        <p className="lead">
          Capture a new dataset from a live Android emulator. Collection always
          writes to <code>datasets/&lt;name&gt;/</code>, so it can never
          overwrite the shipped dataset or an archived run.
        </p>
      </div>
      <Card className="card">
        <div className="card-head">
          <div>
            <h3>Emulator preflight</h3>
            <p className="card-sub">
              Checks that adb sees an authorized device.
            </p>
          </div>
          <div className="card-head-actions">
            <Button
              type="button"
              className="secondary"
              id="collect-preflight-btn"
              onClick={() => void check()}
              disabled={checking}
            >
              {checking ? "Checking…" : "Check emulator"}
            </Button>
          </div>
        </div>
        <div id="collect-preflight-result">
          {checking && <div aria-label="Checking adb"><Alert className="state-loading">Checking adb...</Alert><Skeleton className="skeleton-row" /></div>}
          {preflight &&
            !checking &&
            (!preflight.adb_available ? (
              <>
                <Badge className="badge err">adb not found</Badge>
                <p className="field-hint">
                  {preflight.error ||
                    "Install the Android platform tools and put adb on PATH."}
                </p>
              </>
            ) : preflight.error ? (
              <>
                <Badge className="badge warn">
                  adb found, but listing devices failed
                </Badge>
                <p className="field-hint">
                  <code>{preflight.adb_path}</code>
                </p>
                <p className="field-hint">{preflight.error}</p>
              </>
            ) : authorized.length ? (
              <>
                <Badge className="badge ok">
                  {authorized.length} authorized device
                  {authorized.length === 1 ? "" : "s"}
                </Badge>
                <ul className="field-hint">
                  {authorized.map((d) => (
                    <li key={d.serial}>
                      <code>{d.serial}</code>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <>
                <Badge className="badge warn">
                  adb is working, but no authorized device
                </Badge>
                <ul className="field-hint">
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
        <div className="note">
          <span className="note-label">Prerequisites</span> Not verifiable from
          here: Pixel 6 / API 34 / 1080x2400 at 420 dpi, a signed-in Google
          account, and Messages, Gmail and Maps each opened once to clear their
          first-run dialogs. See <code>docs/collection.md</code>.
        </div>
      </Card>
      <Card className="card card-primary">
        <div className="card-head">
          <h3>New collection</h3>
        </div>
        <form id="collect-form" onSubmit={submit}>
          <div className="field-grid">
            <div className="field field-wide">
              <label htmlFor="collect-name">Dataset name</label>
              <Input
                id="collect-name"
                placeholder="my-app"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <p className="field-hint">
                Captures land in <code>datasets/&lt;name&gt;/</code>.
              </p>
            </div>
            <div className="field">
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
              <p className="field-hint">Select none to capture every screen.</p>
            </div>
          </div>
          <div className="field-grid" style={{ marginTop: "var(--space-4)" }}>
            <label className="check">
              <input
                type="checkbox"
                id="collect-dry-run"
                checked={dry}
                onChange={(e) => setDry(e.target.checked)}
              />
              <span className="check-body">
                Dry run
                <span className="field-hint">
                  Validates the run plan without touching the emulator.
                </span>
              </span>
            </label>
            <label className="check">
              <input
                type="checkbox"
                id="collect-rebuild-manifest"
                checked={rebuild}
                onChange={(e) => setRebuild(e.target.checked)}
              />
              <span className="check-body">
                Rebuild manifest only
                <span className="field-hint">
                  Recomputes drift from existing captures. Takes no new
                  screenshots.
                </span>
              </span>
            </label>
          </div>
          <div className="form-actions">
            <Button type="submit" disabled={starting}>
              {starting ? "Starting…" : "Start collection"}
            </Button>
          </div>
        </form>
        <div id="collect-error">
          {error && <Alert className="state-error">{error}</Alert>}
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
