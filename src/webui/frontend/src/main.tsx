import { createRoot } from "react-dom/client";
import "./style.css";
import { App } from "./app/App";
import { ErrorBoundary } from "./components/shell/ErrorBoundary";
export { App } from "./app/App";
export { ErrorBoundary as AppErrorBoundary } from "./components/shell/ErrorBoundary";
export { api, isTerminalRunStatus } from "./lib/api";
export { normalizeTab, TABS } from "./app/navigation";
export type { Tab } from "./app/navigation";

createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
