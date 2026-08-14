import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocDialog } from "../../src/components/ui/doc-dialog";

const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => cleanup());

describe("DocDialog", () => {
  it("fetches and renders markdown content only after the trigger is opened", async () => {
    const fetchMock = vi.fn(async () =>
      json({ name: "collection.md", content: "# Guide\n\n- step one" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(
      <DocDialog doc="collection.md" trigger={<button>docs/collection.md</button>} />,
    );

    expect(fetchMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "docs/collection.md" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/docs/collection.md",
      expect.anything(),
    );
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Guide" })).toBeTruthy(),
    );
    expect(screen.getByText("step one")).toBeTruthy();
  });

  it("shows an error message when the doc fails to load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ detail: "Unknown doc: nope.md" }, 404)),
    );
    const user = userEvent.setup();

    render(<DocDialog doc="nope.md" trigger={<button>open</button>} />);
    await user.click(screen.getByRole("button", { name: "open" }));

    await waitFor(() =>
      expect(screen.getByText("Unknown doc: nope.md")).toBeTruthy(),
    );
  });
});
