import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi, getAuthToken, type LoginHistoryRow } from "@/lib/api-client";
import { isStudentOrAcademicEmail } from "@/lib/studentEmail";
import { Badge } from "@/components/ui/badge";
import { Loader2, UserCircle } from "lucide-react";

export default function AccountSettings() {
  const { t } = useLanguage();
  const { user, refreshUser, loading: authLoading } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [logins, setLogins] = useState<LoginHistoryRow[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [saving, setSaving] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    setHistoryError(null);
    try {
      const { data } = await authApi.getLoginHistory(10);
      setLogins(data ?? []);
    } catch (e) {
      setLogins([]);
      setHistoryError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading || !getAuthToken() || !user?.id) return;
    void loadHistory();
  }, [authLoading, user?.id, loadHistory]);

  useEffect(() => {
    const u = user?.username;
    const fallback = user?.email?.split("@")[0] ?? "";
    setDisplayName(typeof u === "string" && u.trim() ? u : fallback);
  }, [user?.username, user?.email]);

  const email = user?.email ?? "";
  const academic = isStudentOrAcademicEmail(email);

  const formatLoginCountry = (raw: string | null | undefined) => {
    if (raw == null || raw === "") return "—";
    if (raw === "Local") return t.account.loginGeoLocal;
    return raw;
  };

  const onSave = async () => {
    const name = displayName.trim();
    if (!name) {
      toast.error(t.common.error);
      return;
    }
    setSaving(true);
    try {
      await authApi.patchProfile(name);
      await refreshUser();
      toast.success(t.account.saveSuccess);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
      <div className="min-h-0 flex-1 overflow-y-auto p-6 md:p-10">
        <div className="mx-auto max-w-5xl space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{t.account.settingsTitle}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                <Link to="/start" className="underline-offset-4 hover:underline">
                  {t.account.backToWorkspace}
                </Link>
                {" · "}
                <Link to="/account/overview" className="underline-offset-4 hover:underline">
                  {t.account.navOverview}
                </Link>
              </p>
            </div>
          </div>

          <p className="text-sm text-muted-foreground">{t.account.settingsIntro}</p>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <UserCircle className="h-5 w-5 text-primary" />
                <CardTitle>{t.nav.profile}</CardTitle>
              </div>
              <CardDescription>{t.account.displayNameHint}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2 max-w-md">
                <Label htmlFor="display-name">{t.account.displayName}</Label>
                <Input
                  id="display-name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  autoComplete="name"
                />
              </div>
              <div className="space-y-2 max-w-md">
                <Label>{t.account.emailLabel}</Label>
                <Input value={email} disabled readOnly className="bg-muted/50" />
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button type="button" size="sm" disabled={saving} onClick={() => void onSave()}>
                  {saving ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      {t.account.saving}
                    </>
                  ) : (
                    t.account.saveProfile
                  )}
                </Button>
                <Badge variant={academic ? "default" : "secondary"}>
                  {academic ? t.account.studentVerified : t.account.studentUnverified}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground max-w-xl">{t.account.studentNote}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t.account.loginSection}</CardTitle>
              <CardDescription>{t.account.noLogins}</CardDescription>
            </CardHeader>
            <CardContent>
              {historyError ? (
                <p className="text-sm text-destructive">{historyError}</p>
              ) : loadingHistory ? (
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              ) : logins.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t.account.noLogins}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">{t.account.loginTime}</th>
                        <th className="py-2 pr-4 font-medium">{t.account.loginIp}</th>
                        <th className="py-2 pr-4 font-medium">{t.account.loginCountry}</th>
                        <th className="py-2 font-medium">{t.account.loginUa}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logins.map((row) => (
                        <tr key={row.id} className="border-b border-border/60">
                          <td className="py-2 pr-4 align-top text-xs text-muted-foreground">
                            {row.logged_in_at || "—"}
                          </td>
                          <td className="py-2 pr-4 align-top font-mono text-xs">
                            {row.ip_address ?? "—"}
                          </td>
                          <td className="py-2 pr-4 align-top text-xs">
                            {formatLoginCountry(row.ip_country)}
                          </td>
                          <td className="py-2 align-top text-xs break-all max-w-[240px]">
                            {row.user_agent ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
  );
}
