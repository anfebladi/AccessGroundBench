import { describe, expect, it } from "vitest";
import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Badge } from "../../src/components/ui/badge";
import { Button } from "../../src/components/ui/button";
import { Card, CardTitle } from "../../src/components/ui/card";
import { Input } from "../../src/components/ui/input";
import { Progress } from "../../src/components/ui/progress";
import { Separator } from "../../src/components/ui/separator";
import { Skeleton } from "../../src/components/ui/skeleton";
import {
  SegmentedButton,
  SegmentedGroup,
} from "../../src/components/ui/segmented";
import { Table, TableCell, TableRow } from "../../src/components/ui/table";

describe("shadcn primitives", () => {
  it("forwards button props, variants, and asChild semantics", () => {
    render(
      <>
        <Button variant="destructive" size="sm" disabled aria-label="delete">Delete</Button>
        <Button asChild variant="outline"><a href="/next">Next</a></Button>
      </>,
    );
    const deleteButton = screen.getByRole("button", { name: "delete" });
    expect((deleteButton as HTMLButtonElement).disabled).toBe(true);
    expect(deleteButton.className).toContain("bg-[var(--danger)]");
    expect(deleteButton.className).toContain("text-xs");
    const link = screen.getByRole("link", { name: "Next" });
    expect(link.getAttribute("href")).toBe("/next");
    expect(link.className).toContain("border");
  });

  it("forwards attributes and composes classes on common primitives", () => {
    const { container } = render(
      <Card data-testid="card" className="custom-card"><CardTitle>Title</CardTitle></Card>
    );
    expect(screen.getByTestId("card").className).toContain("custom-card");
    expect(screen.getByRole("heading", { name: "Title" })).toBeTruthy();
    render(<><Badge data-testid="badge">New</Badge><Input aria-label="query" placeholder="Search" /><Skeleton data-testid="skeleton" /></>);
    expect(screen.getByTestId("badge").textContent).toContain("New");
    expect(screen.getByRole("textbox").getAttribute("placeholder")).toBe("Search");
    expect(screen.getByTestId("skeleton").className).toContain("animate-pulse");
    expect(container).toBeTruthy();
  });

  it("renders progress, separator, and table with essential attributes", () => {
    render(
      <>
        <Progress data-testid="progress" value={60} aria-label="completion" />
        <Separator data-testid="separator" orientation="vertical" />
        <Table aria-label="results"><tbody><TableRow><TableCell>One</TableCell></TableRow></tbody></Table>
      </>,
    );
    expect((screen.getByRole("progressbar").firstElementChild as HTMLElement).style.transform).toContain("-40%");
    expect(screen.getByTestId("separator").getAttribute("data-orientation")).toBe("vertical");
    expect(screen.getByRole("table", { name: "results" }).textContent).toContain("One");
  });

  it("shows exactly one pressed chip in a segmented group and moves it on click", async () => {
    const user = userEvent.setup();
    function Group() {
      const [value, setValue] = useState("fit");
      return (
        <SegmentedGroup aria-label="Zoom">
          {["fit", "1:1"].map((option) => (
            <SegmentedButton
              key={option}
              data-option={option}
              pressed={value === option}
              onClick={() => setValue(option)}
            >
              {option}
            </SegmentedButton>
          ))}
        </SegmentedGroup>
      );
    }
    render(<Group />);
    const pressed = () =>
      screen
        .getAllByRole("button")
        .filter((node) => node.getAttribute("aria-pressed") === "true");

    expect(pressed().map((node) => node.textContent)).toEqual(["fit"]);
    // The pressed chip must be visually distinct, not just announced.
    expect(pressed()[0].className).toContain("bg-[var(--primary)]");
    expect(screen.getByRole("button", { name: "1:1" }).className).toContain(
      "bg-transparent",
    );
    // Contract hooks survive the primitive.
    expect(pressed()[0].getAttribute("data-option")).toBe("fit");

    await user.click(screen.getByRole("button", { name: "1:1" }));
    expect(pressed().map((node) => node.textContent)).toEqual(["1:1"]);
  });
});
