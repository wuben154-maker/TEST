import React from "react";
import { Button } from "@/components/ui/button";
import { detectBrowserLanguage, getTranslations } from "@/i18n";
import { logger } from "@/lib/logger";

type State = {
  hasError: boolean;
  error?: Error;
  componentStack?: string;
};

export class AppErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { hasError: false };

  private onUnhandledRejection = (ev: PromiseRejectionEvent) => {
    try {
      const err = ev.reason instanceof Error ? ev.reason : new Error(String(ev.reason));
      logger.error("global_unhandled_rejection", { message: err.message, stack: err.stack });
      if (this.state.hasError) return;
      this.setState({ hasError: true, error: err });
    } catch {
      // ignore
    }
  };

  private onWindowError = (ev: ErrorEvent) => {
    try {
      const err = ev.error instanceof Error ? ev.error : new Error(ev.message || "Unknown error");
      logger.error("global_window_error", { message: err.message, stack: err.stack });
      if (this.state.hasError) return;
      this.setState({ hasError: true, error: err });
    } catch {
      // ignore
    }
  };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    logger.error("react_error_boundary_caught", {
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
    });
    this.setState({ componentStack: errorInfo.componentStack });
  }

  componentDidMount() {
    window.addEventListener("unhandledrejection", this.onUnhandledRejection);
    window.addEventListener("error", this.onWindowError);
  }

  componentWillUnmount() {
    window.removeEventListener("unhandledrejection", this.onUnhandledRejection);
    window.removeEventListener("error", this.onWindowError);
  }

  private buildDebugText() {
    const { error, componentStack } = this.state;
    return [
      `message: ${error?.message ?? "(no message)"}`,
      error?.stack ? `\nstack:\n${error.stack}` : "",
      componentStack ? `\ncomponentStack:\n${componentStack}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }

  private copy = async () => {
    const text = this.buildDebugText();
    try {
      await navigator.clipboard.writeText(text);
      logger.debug("error_boundary_clipboard_copy_success");
    } catch {
      // Fallback for older browsers
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  };

  private reload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const debugText = this.buildDebugText();
    const text = getTranslations(detectBrowserLanguage()).errorBoundary;

    return (
      <main className="min-h-screen bg-background text-foreground">
        <div className="mx-auto w-full max-w-3xl p-6 space-y-4">
          <header className="space-y-1">
            <h1 className="text-xl font-semibold">{text.title}</h1>
            <p className="text-sm text-muted-foreground">
              {text.description}
            </p>
          </header>

          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <div className="flex flex-wrap gap-2">
              <Button variant="default" onClick={this.reload}>
                {text.refreshPage}
              </Button>
              <Button variant="secondary" onClick={this.copy}>
                {text.copyErrorInfo}
              </Button>
            </div>

            <pre className="max-h-[50vh] overflow-auto rounded-md bg-muted p-3 text-xs text-foreground whitespace-pre-wrap">
              {debugText || "(no debug text)"}
            </pre>
          </section>
        </div>
      </main>
    );
  }
}
