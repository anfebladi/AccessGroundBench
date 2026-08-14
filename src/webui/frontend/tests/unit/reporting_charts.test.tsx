import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@nivo/bar", () => ({
  Bar: (props: any) => {
    const bars = (props.data ?? []).map((row: any, index: number) => ({
      data: { indexValue: row[props.indexBy ?? "label"] }, y: index * 40, height: 20,
    }));
    const scale = (value: number | string) => typeof value === "number" ? value * 100 : 0;
    const layers = (props.layers ?? []).filter((layer: any) => typeof layer === "function");
    return <svg role={props.role} aria-label={props.ariaLabel} data-height={props.height}
      data-rows={JSON.stringify((props.data ?? []).map((row: any) => ({ id: row.id, label: row.label })))}
      data-index-by={props.indexBy}
      data-ticks={JSON.stringify(props.axisBottom?.tickValues)}
      data-theme-text={props.theme?.text?.fill}>
      {layers.map((layer: any, i: number) => <g key={i}>{layer({ bars, xScale: scale, yScale: scale })}</g>)}
    </svg>;
  },
}));
vi.mock("@nivo/scatterplot", () => ({
  ScatterPlot: (props: any) => {
    const layers = (props.layers ?? []).filter((layer: any) => typeof layer === "function");
    const scale = (value: number | string) => typeof value === "number" ? value * 100 : 0;
    return <svg role={props.role} aria-label={props.ariaLabel} data-height={props.height}
      data-rows={JSON.stringify((props.data?.[0]?.data ?? []).map((row: any) => ({ id: row.id, label: row.y })))}
      data-x-scale={JSON.stringify(props.xScale)}
      data-ticks={JSON.stringify(props.axisBottom?.tickValues)}
      data-theme-text={props.theme?.text?.fill}>
      {layers.map((layer: any, i: number) => <g key={i}>{layer({ xScale: scale, yScale: scale })}</g>)}</svg>;
  },
}));
vi.mock("../../src/lib/export", () => ({ exportSvgAsPng: vi.fn() }));

import { AccuracyChart, DirectionChart, DiscordantChart, DumbbellChart, PairedAccuracyChart, ReachabilityChart } from "../../src/features/shared/reporting/charts";
import { ExportButton } from "../../src/features/shared/reporting/components/ExportButton";
import { exportSvgAsPng } from "../../src/lib/export";
import { CompareView } from "../../src/features/compare/CompareView";

describe("reporting charts", () => {
  beforeEach(() => { document.body.innerHTML = ""; vi.clearAllMocks(); });

  it("handles empty and invalid rows, while sizing single and many-row charts", () => {
    const { rerender } = render(<AccuracyChart rows={[{ label: "" }, { label: "", value: 1 }]} />);
    expect(screen.getByText("No valid data available.")).toBeTruthy();
    rerender(<AccuracyChart rows={[{ label: "Model", value: 1 }]} />);
    expect(document.querySelector("svg[data-height='240']")).toBeTruthy();
    rerender(<AccuracyChart rows={Array.from({ length: 10 }, (_, i) => ({ label: `M${i}`, value: 0.5 }))} />);
    expect(document.querySelector("svg[data-height='476']")).toBeTruthy();
    expect(document.querySelector(".max-h-\\[560px\\]")).toBeTruthy();
  });

  it("clamps accuracy/reachability values and confidence intervals", () => {
    const { container } = render(<ReachabilityChart rows={[{ label: "A", value: 0.8, lo: -2, hi: 8 }]} />);
    expect(container.querySelector("svg")).toBeTruthy();
    const ci = container.querySelector(".chart-ci");
    expect(ci).toBeTruthy();
    expect(ci?.querySelectorAll("line").length).toBe(3);
    render(<AccuracyChart rows={[{ label: "A", value: Number.NaN }, { label: "B", value: -2 }]} />);
    expect(screen.getByText("No valid data available.")).toBeTruthy();
  });

  it("keeps duplicate model observations distinct and excludes invalid accuracy values", () => {
    const { container } = render(<AccuracyChart rows={[
      { id: "vision-a", label: "same-model", value: 0 },
      { id: "vision-b", label: "same-model", value: 1 },
      { id: "bad-null", label: "null", value: null as unknown as number },
      { id: "bad-nan", label: "nan", value: Number.NaN },
      { id: "bad-infinity", label: "infinity", value: Number.POSITIVE_INFINITY },
    ]} />);
    const chart = container.querySelector("svg");
    expect(JSON.parse(chart?.getAttribute("data-rows") || "[]")).toEqual([
      { id: "vision-a", label: "same-model" },
      { id: "vision-b", label: "same-model" },
    ]);
  });

  it("keeps duplicate labels distinct in discordant and direction charts", () => {
    const rows = [
      { id: "vision-run", label: "same-model", left: 1, right: 2, down: 1, tied: 0, up: 1 },
      { id: "tree-run", label: "same-model", left: 3, right: 4, down: 0, tied: 1, up: 2 },
    ];
    const { container, rerender } = render(<DiscordantChart rows={rows} />);
    const expected = [{ id: "vision-run" }, { id: "tree-run" }];
    const discordant = container.querySelector("svg");
    expect(discordant?.getAttribute("data-index-by")).toBe("id");
    expect(JSON.parse(discordant?.getAttribute("data-rows") || "[]")).toEqual(expected);
    rerender(<DirectionChart rows={rows} />);
    const direction = container.querySelector("svg");
    expect(direction?.getAttribute("data-index-by")).toBe("id");
    expect(JSON.parse(direction?.getAttribute("data-rows") || "[]")).toEqual(expected);
  });

  it("uses exact probability ticks and light/dark chart themes", () => {
    const { container, rerender } = render(<AccuracyChart rows={[{ label: "A", value: 0.5 }]} />);
    const chart = () => container.querySelector("svg") as SVGElement;
    expect(JSON.parse(chart().getAttribute("data-ticks") || "[]")).toEqual([0, 0.25, 0.5, 0.75, 1]);
    expect(chart().getAttribute("data-theme-text")).toBe("var(--text-2)");
    rerender(<AccuracyChart tone="dark" rows={[{ label: "A", value: 0.5 }]} />);
    expect(chart().getAttribute("data-theme-text")).toBe("var(--on-dark-muted)");
  });

  it("keeps Compare charts in the dark card treatment", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/results")) return new Response(JSON.stringify([{filename: "r.csv", model: "model-a", prompt_mode: "vision", row_count: 1, statuses: {HIT: 1}, hits: 1, co_present_count: 1, accuracy: 1, baseline_accuracy: 1}]), {headers: {"Content-Type": "application/json"}});
      if (path.includes("/results/compare?")) return new Response(JSON.stringify({model: "model-a", mode: "vision", models_in_family: ["model-a"], profiles: [{profile: "high_contrast", baseline_accuracy: 50, profile_accuracy: 25, delta: 25, b: 1, c: 0, reachability: .8, significance_state: "significant"}]}), {headers: {"Content-Type": "application/json"}});
      return new Response(JSON.stringify([]), {headers: {"Content-Type": "application/json"}});
    }));
    render(<CompareView dataset="demo" />);
    const charts = await screen.findAllByRole("img", { name: /Paired baseline and profile accuracies/ });
    const chart = charts.find((element) => element.tagName.toLowerCase() === "svg") ?? charts[0];
    const frame = chart.closest("[id='compare-model-a-vision']");
    expect(frame?.className).toContain("bg-[var(--panel-dark)]");
    expect(frame?.querySelector('[data-chart-tone="dark"]')).toBeTruthy();
  });

  it("renders dumbbell connectors, deltas, and underpowered markers", () => {
    const { container } = render(<DumbbellChart rows={[{ id: "run-1", label: "Model", from: 0.2, to: 0.7, underpowered: true, annotation: "reserved" }]} />);
    expect(container.querySelector(".chart-dumbbell-connector")).toBeTruthy();
    expect(container.querySelector(".chart-underpowered")).toBeTruthy();
    expect(container.querySelector(".chart-dumbbell-label")?.textContent).toContain("+50.0 pp † underpowered");
    expect(container.querySelector(".chart-dumbbell-label")?.textContent).not.toContain("reserved");
    expect(container.querySelector(".chart-dumbbell-label")?.getAttribute("text-decoration")).not.toBe("line-through");
  });

  it("renders paired endpoints/connectors on a zoomed scale with fixed annotations", () => {
    const { container } = render(<PairedAccuracyChart rows={[
      { id: "positive", label: "Improved", from: 0.5, to: 0.75 },
      { id: "negative", label: "Declined", from: 0.8, to: 0.65, underpowered: true },
      { id: "zero", label: "Unchanged", from: 0.7, to: 0.7, underpowered: true },
    ]} />);
    const chart = container.querySelector("svg");
    expect(chart?.getAttribute("aria-label")).toContain("zoomed accuracy scale");
    expect(container.querySelector("[data-chart-label]")?.getAttribute("aria-label")).toContain(
      "† Underpowered: too few informative paired comparisons to detect or rule out a real difference; ‘No change’ is inconclusive.",
    );
    const domain = JSON.parse(chart?.getAttribute("data-x-scale") || "{}");
    expect(domain.min).toBeCloseTo(0.44, 6);
    expect(domain.max).toBeCloseTo(0.86, 6);
    expect(container.querySelectorAll(".chart-paired-accuracy-connector")).toHaveLength(3);
    expect(container.querySelectorAll(".chart-paired-accuracy-baseline")).toHaveLength(3);
    expect(container.querySelectorAll(".chart-paired-accuracy-profile")).toHaveLength(3);
    const labels = container.querySelectorAll(".chart-paired-accuracy-label");
    expect(labels).toHaveLength(3);
    expect(labels[0].textContent).toContain("50.0% → 75.0% (+25.0 pp)");
    expect(labels[1].textContent).toContain("80.0% → 65.0% (-15.0 pp) † underpowered");
    expect(labels[2].textContent).toBe("No change † underpowered");
    expect(labels[0].getAttribute("x")).toBe(labels[1].getAttribute("x"));
    expect(labels[1].getAttribute("x")).toBe(labels[2].getAttribute("x"));
    expect(Number(labels[0].getAttribute("x"))).toBeGreaterThan(80);
    expect(container.querySelectorAll(".chart-underpowered")).toHaveLength(2);
    expect(container.querySelector(".chart-paired-accuracy-baseline")?.getAttribute("style")).toContain("fill: #2a78d6");
    expect(container.querySelector(".chart-paired-accuracy-profile")?.getAttribute("style")).toContain("fill: #eb6834");
    expect(container.querySelector(".chart-scale-note")?.textContent).toBe("Zoomed accuracy scale");
  });

  it("renders discordant significance annotations and direction labels/p values", () => {
    const { container } = render(<DiscordantChart rows={[{ label: "Profile", left: 2, right: 3, significant: true, annotation: "p<0.05" }]} />);
    expect(container.querySelectorAll(".chart-direct-label").length).toBe(2);
    expect(container.querySelector(".chart-significance")?.textContent).toContain("* p<0.05");
    const { container: direction } = render(<DirectionChart rows={[{ label: "Profile", down: 2, tied: 0, up: 3, p: "0.01" }]} />);
    expect(direction.querySelectorAll(".chart-direct-label").length).toBe(2);
    expect(direction.querySelector(".chart-significance")?.textContent).toContain("p 0.01");
  });

  it("disables Nivo animation when prefers-reduced-motion is enabled", () => {
    const matchMedia = vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true, media: "(prefers-reduced-motion: reduce)", addEventListener: vi.fn(), removeEventListener: vi.fn() } as any);
    render(<AccuracyChart rows={[{ label: "A", value: 0.5 }]} />);
    expect(matchMedia).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)");
  });
});

describe("ExportButton", () => {
  it("selects the required target SVG and dispatches a stable filename", () => {
    render(<><div id="chart"><svg /></div><ExportButton name="accuracy" targetId="chart" /></>);
    screen.getByRole("button", { name: "Export chart as PNG" }).click();
    expect(exportSvgAsPng).toHaveBeenCalledWith(expect.any(SVGSVGElement), "accuracy.png");
  });

  it("does not export when target id is missing or has no SVG", () => {
    document.body.innerHTML = "";
    const { rerender } = render(<ExportButton name="missing" targetId="absent" />);
    screen.getByRole("button", { name: "Export chart as PNG" }).click();
    expect(exportSvgAsPng).not.toHaveBeenCalled();
    rerender(<><div id="empty" /><ExportButton name="empty" targetId="empty" /></>);
    screen.getByRole("button", { name: "Export chart as PNG" }).click();
    expect(exportSvgAsPng).not.toHaveBeenCalled();
  });
});
