import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useLanguage } from "@/contexts/LanguageContext";
import { useWorkspaceProjects } from "@/contexts/WorkspaceProjectsContext";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  knowledgeApi,
  type KnowledgeItem,
  getAuthToken,
} from "@/lib/api-client";
import {
  Loader2,
  Download,
  BookOpen,
  RefreshCw,
  FileText,
  File,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

function formatBytes(n: number, locale: string): string {
  if (n < 1024) return `${n} B`;
  const u = ["KB", "MB", "GB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${u[i]}`;
}

function extFromFilename(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i + 1).toLowerCase() : "";
}

function formatUpdatedRel(iso: string, locale: string, justNow: string): string {
  const t = new Date(iso).getTime();
  const diffSec = Math.round((Date.now() - t) / 1000);
  if (!Number.isFinite(diffSec) || diffSec < 45) return justNow;

  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  let d = diffSec;
  if (d < 3600) {
    return rtf.format(-Math.floor(d / 60), "minute");
  }
  if (d < 86400) {
    return rtf.format(-Math.floor(d / 3600), "hour");
  }
  if (d < 86400 * 30) {
    return rtf.format(-Math.floor(d / 86400), "day");
  }
  if (d < 86400 * 365) {
    return rtf.format(-Math.floor(d / (86400 * 30)), "month");
  }
  return rtf.format(-Math.floor(d / (86400 * 365)), "year");
}

export default function KnowledgeBase() {
  const { t, language } = useLanguage();
  const kt = t.knowledgeBase;
  const navigate = useNavigate();
  const { selectProject } = useWorkspaceProjects();
  const [searchParams] = useSearchParams();
  const highlightName = (searchParams.get("highlight") || "").trim();
  const highlightRowRef = useRef<HTMLDivElement | null>(null);
  const { user, loading: authLoading } = useAuth();
  const locale =
    language === "zh"
      ? "zh-CN"
      : language === "ja"
        ? "ja-JP"
        : language === "ko"
          ? "ko-KR"
          : "en-US";

  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const [downloading, setDownloading] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!getAuthToken() || !user?.id) {
      setItems([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await knowledgeApi.list();
      setItems(res.items ?? []);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setItems([]);
      toast.error(kt.loadError, { description: msg });
    } finally {
      setLoading(false);
    }
  }, [user?.id, kt.loadError]);

  useEffect(() => {
    if (authLoading) return;
    void refresh();
  }, [authLoading, refresh]);

  const sorted = useMemo(
    () => [...items].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1)),
    [items],
  );

  const stats = useMemo(() => {
    let totalBytes = 0;
    let latest = "";
    for (const row of sorted) {
      totalBytes += row.size_bytes;
      if (!latest || row.updated_at > latest) latest = row.updated_at;
    }
    return {
      count: sorted.length,
      totalBytes,
      latestIso: latest,
    };
  }, [sorted]);

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter((row) => {
      const blob = [
        row.display_name,
        row.display_path,
        row.filename,
        row.project_id ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(q);
    });
  }, [sorted, searchQuery]);

  useEffect(() => {
    if (!highlightName) return;
    highlightRowRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [highlightName, filtered]);

  const onDownload = async (filename: string) => {
    setDownloading(filename);
    try {
      const blob = await knowledgeApi.downloadBlob(filename);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(kt.downloadSuccess, { description: filename });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(kt.loadError, { description: msg });
    } finally {
      setDownloading(null);
    }
  };

  const openLinkedProject = (projectId: string | null | undefined) => {
    const id = typeof projectId === "string" ? projectId.trim() : "";
    if (!id) {
      toast.info(kt.noProjectLinkedHint);
      return;
    }
    selectProject(id);
    navigate("/start");
  };

  const needsAuth = !authLoading && (!getAuthToken() || !user?.id);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-background px-4 py-10 text-foreground">
      <div className="mx-auto w-full max-w-4xl space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-xl border border-border bg-muted/30 p-2.5 shadow-sm">
              <BookOpen className="h-7 w-7 text-muted-foreground" aria-hidden />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{kt.pageTitle}</h1>
              <p className="mt-1 max-w-prose text-sm leading-relaxed text-muted-foreground">
                {kt.pageSubtitle}
              </p>
            </div>
          </div>
          {!needsAuth && sorted.length > 0 ? (
            <div className="flex shrink-0 flex-wrap gap-2 sm:justify-end">
              <div className="rounded-lg border border-border bg-card/60 px-3 py-2 text-xs text-muted-foreground shadow-sm">
                <span className="font-medium text-foreground">
                  {kt.statsItems.replace("{count}", String(stats.count))}
                </span>
                <span className="mx-1.5 text-border">·</span>
                {kt.statsTotalSize.replace("{size}", formatBytes(stats.totalBytes, locale))}
              </div>
              {stats.latestIso ? (
                <div className="rounded-lg border border-border bg-card/60 px-3 py-2 text-xs text-muted-foreground shadow-sm">
                  {kt.statsLatest.replace(
                    "{date}",
                    formatUpdatedRel(stats.latestIso, locale, kt.justUpdated),
                  )}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        {needsAuth ? (
          <p className="text-sm text-muted-foreground">{t.auth.title}</p>
        ) : null}

        {!needsAuth ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              data-testid="kb-search"
              className="sm:max-w-sm"
              placeholder={kt.searchPlaceholder}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label={kt.searchPlaceholder}
              disabled={loading || !!error}
            />
            <Button
              data-testid="kb-refresh"
              type="button"
              variant="outline"
              size="sm"
              className="h-10 gap-2 sm:w-auto"
              onClick={() => void refresh()}
              disabled={loading}
              aria-label={kt.refreshLabel}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <RefreshCw className="h-4 w-4" aria-hidden />
              )}
              <span className="sm:inline">{kt.refreshLabel}</span>
            </Button>
          </div>
        ) : null}

        {!needsAuth && loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            {t.common.loading}
          </div>
        ) : null}

        {!needsAuth && !loading && error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : null}

        {!needsAuth && !loading && !error && sorted.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-muted/10 px-6 py-12 text-center">
            <p className="text-sm text-muted-foreground">{kt.emptyHint}</p>
            <Button
              data-testid="kb-empty-cta"
              type="button"
              className="mt-6"
              onClick={() => navigate("/start")}
            >
              {kt.goWorkspace}
            </Button>
          </div>
        ) : null}

        {!needsAuth && !loading && !error && sorted.length > 0 && filtered.length === 0 ? (
          <p className="rounded-lg border border-border bg-muted/20 px-4 py-8 text-center text-sm text-muted-foreground">
            {kt.noMatches}
          </p>
        ) : null}

        {!needsAuth && filtered.length > 0 ? (
          <ul className="space-y-3" role="list" aria-busy={loading}>
            {filtered.map((row) => {
              const title = row.display_name || row.display_path || row.filename;
              const ext = extFromFilename(row.filename);
              const isHighlight = highlightName !== "" && row.filename === highlightName;
              const FileIcon = ext === "docx" || ext === "md" || ext === "txt" ? FileText : File;

              return (
                <li key={row.filename} role="listitem">
                  <div
                    ref={isHighlight ? highlightRowRef : undefined}
                    className={cn(
                      "flex flex-col gap-4 rounded-xl border border-border bg-card/40 p-4 shadow-sm transition-colors sm:flex-row sm:items-center sm:gap-4",
                      "hover:bg-muted/20",
                      isHighlight &&
                        "border-primary/40 bg-primary/5 ring-2 ring-primary/30 ring-offset-2 ring-offset-background",
                    )}
                  >
                    <div className="flex min-w-0 flex-1 gap-3">
                      <div
                        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-border bg-muted/40 text-muted-foreground"
                        aria-hidden
                      >
                        <FileIcon className="h-5 w-5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <button
                          type="button"
                          className={cn(
                            "block w-full truncate text-left text-base font-medium underline-offset-4",
                            row.project_id?.trim()
                              ? "text-foreground hover:underline"
                              : "cursor-not-allowed text-muted-foreground no-underline hover:no-underline",
                          )}
                          onClick={() => openLinkedProject(row.project_id)}
                          title={
                            row.project_id?.trim()
                              ? kt.openProjectTooltip
                              : kt.noProjectLinkedHint
                          }
                        >
                          {title}
                        </button>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {formatBytes(row.size_bytes, locale)}
                          <span className="mx-1.5 text-border">·</span>
                          {formatUpdatedRel(row.updated_at, locale, kt.justUpdated)}
                          <span className="mx-1.5 text-border">·</span>
                          {row.project_id?.trim()
                            ? kt.linkedProjectHint
                            : kt.notLinkedShort}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2 sm:justify-end">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-9 gap-1.5"
                        onClick={() => void onDownload(row.filename)}
                        disabled={downloading === row.filename}
                        aria-label={kt.downloadLabel}
                      >
                        {downloading === row.filename ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Download className="h-3.5 w-3.5" />
                        )}
                        {kt.downloadLabel}
                      </Button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
