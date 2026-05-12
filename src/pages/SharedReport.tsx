import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { WorkspaceBlock } from "@/types/analysis";
import { Shield, Loader2 } from "lucide-react";
import { config } from "@/lib/config";
import { getClientTimezoneHeaders } from "@/lib/api-client";
import { logger } from "@/lib/logger";
import { normalizeReportDocument } from "@/lib/reportDocument";
import { ReportRenderer } from "@/components/workspace/ReportRenderer";
import { useLanguage } from "@/contexts/LanguageContext";

export default function SharedReport() {
  const { token } = useParams<{ token: string }>();
  const { t } = useLanguage();
  const [report, setReport] = useState<{ title: string; blocks: WorkspaceBlock[]; created_at: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchReport() {
      if (!token) {
        setError("Invalid share link");
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${config.pythonBackendUrl}/shared-reports/by-token/${token}`, {
          headers: { ...getClientTimezoneHeaders() },
        });
        if (!response.ok) {
          setError("Report not found or has expired");
          setLoading(false);
          return;
        }

        const data = await response.json();
        setReport({
          title: data.title,
          blocks: data.blocks as WorkspaceBlock[],
          created_at: data.created_at,
        });
        setLoading(false);
      } catch (e) {
        logger.error("shared_report_fetch_failed", { error: String(e) });
        setError("Report not found or has expired");
        setLoading(false);
      }
    }

    fetchReport();
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4">
        <Shield className="w-16 h-16 text-muted-foreground" />
        <h1 className="text-xl font-medium text-foreground">Report Not Found</h1>
        <p className="text-muted-foreground">{error || 'This report may have expired or been deleted.'}</p>
      </div>
    );
  }

  const reportDocument = normalizeReportDocument({
    id: token || 'shared-report',
    title: report.title,
    blocks: report.blocks,
    generatedAt: report.created_at,
    copy: t.workspace.reportTemplates
      ? {
          templates: t.workspace.reportTemplates,
          risk: t.workspace.taskPanel.risk,
          sources: t.workspace.taskPanel.sourceCount,
          severityLabels: t.workspace.taskPanel.severityLabels,
        }
      : undefined,
  });

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <Shield className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="font-semibold text-foreground">SecManus</h1>
            <p className="text-xs text-muted-foreground">
              {t.workspace.title}
            </p>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto p-6">
        <header className="mb-8">
          <h1 className="text-2xl font-semibold text-foreground break-words">
            {report.title}
          </h1>
          <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{t.workspace.generatedAt}</span>
            <time dateTime={report.created_at}>{report.created_at}</time>
          </p>
        </header>
        <ReportRenderer document={reportDocument} />
      </main>

      {/* Footer */}
      <footer className="border-t border-border bg-card/30 px-6 py-4 mt-8">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-xs text-muted-foreground">
            <span className="text-primary font-medium">SecManus</span>
            <span className="mx-1.5">·</span>
            AI Security Workspace
          </p>
        </div>
      </footer>
    </div>
  );
}
