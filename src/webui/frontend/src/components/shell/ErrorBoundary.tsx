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
      <main className="app-error" role="alert" aria-live="assertive">
        <h1>AccessGroundBench could not render this view</h1>
        <p>
          Refresh the page and try again. If the problem persists, check the
          dataset response and browser console.
        </p>
        {this.state.message && (
          <p className="note note-warn">{this.state.message}</p>
        )}
        <Button
          type="button"
          className="secondary"
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
