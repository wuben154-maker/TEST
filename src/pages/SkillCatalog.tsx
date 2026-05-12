import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "@/contexts/LanguageContext";
import { registryApi, type RegistryCatalogSkill } from "@/lib/api-client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2 } from "lucide-react";

export default function SkillCatalog() {
  const { t } = useLanguage();
  const [items, setItems] = useState<RegistryCatalogSkill[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await registryApi.getGlobalSkills();
        if (!cancelled) {
          setItems(data.skills ?? []);
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

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6 md:p-10">
      <div className="mx-auto max-w-6xl space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t.registryCatalog.skillsTitle}</h1>
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
          <p className="text-sm text-muted-foreground">{t.registryCatalog.emptySkills}</p>
        ) : null}

        {items && items.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {items.map((s) => (
              <Card key={s.directory_name} className="border-border/80 bg-card/50">
                <CardHeader className="space-y-1">
                  <CardTitle className="text-lg leading-snug">{s.name}</CardTitle>
                  <CardDescription className="text-base leading-relaxed text-foreground/90">
                    {s.description}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-xs text-muted-foreground">
                  <div className="font-mono text-[10px] text-muted-foreground/80">
                    {t.registryCatalog.packageId}: {s.directory_name}
                  </div>
                  <div>
                    {t.registryCatalog.mainAgentVisible}:{" "}
                    {s.enabled_for_main_agent
                      ? t.registryCatalog.mainAgentYes
                      : t.registryCatalog.mainAgentNo}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
