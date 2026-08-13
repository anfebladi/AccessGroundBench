import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "../ui/button";

export class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; message: string }
> {
  state = { hasError: false, message: "" };

  static getDerivedStateFromError(error: unknown) {
    return {
      hasError: true,
      message:
        error instanceof Error
          ? error.message
          : "The interface encountered an unexpected error.",
    };
  }

  componentDidCatch(error: unknown, _info: ErrorInfo) {
    console.error("AccessGroundBench UI failed to render", error);
  }

  render() {
    return this.state.hasError ? (
      <main className="mx-auto max-w-[var(--prose-max)] p-[var(--space-6)]" role="alert" aria-live="assertive">
        <h1 className="mb-2 font-display text-[length:var(--text-display)] font-semibold leading-[var(--lh-display)] tracking-[var(--ls-display)]">AccessGroundBench could not render this view</h1>
        <p className="mb-4">
          Refresh the page and try again. If the problem persists, check the
          dataset response and browser console.
        </p>
        {this.state.message && (
          <p className="my-4 max-w-[var(--prose-max)] border-l-[3px] border-[var(--warn)] py-0.5 pl-3 text-sm">{this.state.message}</p>
        )}
        <Button
          type="button"
          variant="secondary"
          onClick={() => window.location.reload()}
        >
          Reload interface
        </Button>
      </main>
    ) : (
      this.props.children
    );
  }
}
