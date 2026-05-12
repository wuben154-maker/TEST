import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  registryApi,
  type RegistryCatalogSubagent,
} from "@/lib/api-client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2 } from "lucide-react";

export default function SubagentCatalog() {
  const { t } = useLanguage();
  const [items, setItems] = useState<RegistryCatalogSubagent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await registryApi.getSubagents();
        if (!cancelled) {
          setItems(data.subagents ?? []);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setItems(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return load();
  }, [load]);

  const sharedLabel = (row: RegistryCatalogSubagent) => {
    if (row.include_shared_skills) return t.registryCatalog.includeSharedAll;
    if (row.extra_skill_package_ids.length > 0) return t.registryCatalog.includeSharedSubset;
    return t.registryCatalog.includeSharedNone;
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6 md:p-10">
      <div className="mx-auto max-w-6xl space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {t.registryCatalog.subagentsTitle}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            <Link to="/start" className="underline-offset-4 hover:underline">
              {t.account.backToWorkspace}
            </Link>
          </p>
        </div>

        {error ? (
          <div className="text-sm text-destructive">
            <p>{t.registryCatalog.loadError}</p>
            <p className="mt-1 font-mono text-xs opacity-90">{error}</p>
          </div>
        ) : null}

        {items === null && !error ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
            <span>{t.common.loading}</span>
          </div>
        ) : null}

        {items && items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t.registryCatalog.emptySubagents}</p>
        ) : null}

        {items && items.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            {items.map((row) => (
              <Card key={row.id} className="border-border/80 bg-card/50">
                <CardHeader className="space-y-1">
                  <CardTitle className="font-mono text-lg tracking-tight">{row.id}</CardTitle>
                  <CardDescription className="text-base leading-relaxed text-foreground/90">
                    {row.purpose}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 text-sm">
                  <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <span className="rounded-md border border-border/60 bg-muted/40 px-2 py-0.5">
                      {t.registryCatalog.runtime}: {row.runtime}
                    </span>
                    <span className="rounded-md border border-border/60 bg-muted/40 px-2 py-0.5">
                      {t.registryCatalog.toolProfile}: {row.tool_profile}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    <span className="font-medium text-foreground/80">
                      {t.registryCatalog.includeSharedLabel}:{" "}
                    </span>
                    {sharedLabel(row)}
                  </p>

                  {row.bundle_skills.length > 0 ? (
                    <div className="space-y-2">
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        {t.registryCatalog.bundleSkillsTitle}
                      </h3>
                      <ul className="space-y-2">
                        {row.bundle_skills.map((s) => (
                          <li
                            key={`${row.id}-b-${s.directory_name}`}
                            className="rounded-lg border border-border/50 bg-muted/20 p-3"
                          >
                            <div className="font-medium text-foreground">{s.name}</div>
                            <div className="mt-1 text-xs text-muted-foreground">{s.description}</div>
                            <div className="mt-1 font-mono text-[10px] text-muted-foreground/80">
                              {t.registryCatalog.packageId}: {s.directory_name}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {row.attached_global_skills.length > 0 ? (
                    <div className="space-y-2">
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        {t.registryCatalog.attachedSkillsTitle}
                      </h3>
                      <ul className="space-y-2">
                        {row.attached_global_skills.map((s) => (
                          <li
                            key={`${row.id}-g-${s.directory_name}`}
                            className="rounded-lg border border-border/50 bg-muted/20 p-3"
                          >
                            <div className="flex flex-wrap items-baseline justify-between gap-2">
                              <span className="font-medium text-foreground">{s.name}</span>
                              <span className="text-[10px] text-muted-foreground">
                                {t.registryCatalog.mainAgentVisible}:{" "}
                                {s.enabled_for_main_agent
                                  ? t.registryCatalog.mainAgentYes
                                  : t.registryCatalog.mainAgentNo}
                              </span>
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">{s.description}</div>
                            <div className="mt-1 font-mono text-[10px] text-muted-foreground/80">
                              {t.registryCatalog.packageId}: {s.directory_name}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
