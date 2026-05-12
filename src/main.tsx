import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { applyDevAuthHashBootstrap } from "./lib/devAuthHashBootstrap";
import { logger } from "./lib/logger";
import { createRemoteSink } from "./lib/loggerRemoteSink";

if (!import.meta.env.DEV) {
  logger.addSink(createRemoteSink());
}

if (!applyDevAuthHashBootstrap()) {
  createRoot(document.getElementById("root")!).render(
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>,
  );
}
