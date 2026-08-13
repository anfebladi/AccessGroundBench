import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "../../src/components/ui/badge";
import { Button } from "../../src/components/ui/button";
import { Card, CardTitle } from "../../src/components/ui/card";
import { Input } from "../../src/components/ui/input";
import { Progress } from "../../src/components/ui/progress";
import { Separator } from "../../src/components/ui/separator";
import { Skeleton } from "../../src/components/ui/skeleton";
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
});
