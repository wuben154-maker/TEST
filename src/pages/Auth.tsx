import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "@/lib/api-client";
import { markPostLoginLandingSession } from "@/lib/postLoginLanding";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/hooks/use-toast";
import { Shield, Globe } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/hooks/useAuth";
import { languages, Language } from "@/i18n";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const Auth = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPasswordField, setShowPasswordField] = useState(false);
  const navigate = useNavigate();
  const { language, setLanguage, t } = useLanguage();
  const { refreshUser } = useAuth();

  useEffect(() => {
    let cancelled = false;
    authApi.getSession().then(async ({ data }) => {
      if (cancelled || !data.user) return;
      await refreshUser();
      markPostLoginLandingSession();
      navigate("/start");
    });
    return () => {
      cancelled = true;
    };
  }, [navigate, refreshUser]);

  const handleEmailContinue = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!email) {
      toast({
        title: t.auth.emailPlaceholder,
        variant: "destructive",
      });
      return;
    }

    if (!showPasswordField) {
      setShowPasswordField(true);
      return;
    }

    if (!password || password.length < 6) {
      toast({
        title: t.auth.passwordPlaceholder,
        variant: "destructive",
      });
      return;
    }

    setLoading(true);

    try {
      if (isLogin) {
        const { data } = await authApi.login(email, password);
        if (!data?.access_token) {
          throw new Error("Invalid login response");
        }
        toast({
          title: t.common.success,
          description: t.auth.success.welcomeBack,
        });
      } else {
        const { data } = await authApi.register(email, password);
        if (!data?.access_token) {
          throw new Error("Registration failed");
        }
        toast({
          title: t.common.success,
          description: t.auth.success.welcomeBack,
        });
      }
      await refreshUser();
      markPostLoginLandingSession();
      navigate("/start");
    } catch (error: any) {
      let message = t.auth.errors.genericError;
      const errMsg = error?.message ?? "";
      if (errMsg.includes("Email already registered") || errMsg.includes("already registered")) {
        message = t.auth.errors.userNotFound ?? "Email already registered";
      } else if (errMsg.includes("Invalid email or password") || errMsg.includes("invalid")) {
        message = t.auth.errors.invalidCredentials;
      } else if (errMsg.includes("Database unavailable") || errMsg.includes("not initialized")) {
        message = errMsg; // Show actionable backend hint
      } else if (errMsg && errMsg !== "Registration failed" && errMsg !== "Request failed") {
        message = errMsg; // Show API detail when available
      }
      toast({
        title: t.common.error,
        description: message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleOAuthLogin = async (provider: 'google' | 'github') => {
    // OAuth is currently not wired to backend; keep UI but show a friendly message.
    toast({
      title: t.common.info ?? "Info",
      description: t.auth?.errors?.genericError ?? "OAuth login is not available yet.",
    });
  };

  const toggleMode = () => {
    setIsLogin(!isLogin);
    setShowPasswordField(false);
    setPassword("");
  };

  return (
    <div className="min-h-screen flex">
      {/* Left side - Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8 bg-background relative">
        {/* Language Switcher */}
        <div className="absolute top-6 right-6">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-2">
                <Globe className="w-4 h-4" />
                {languages[language].nativeName}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {(Object.keys(languages) as Language[]).map((lang) => (
                <DropdownMenuItem
                  key={lang}
                  onClick={() => setLanguage(lang)}
                  className={language === lang ? "bg-accent" : ""}
                >
                  {languages[lang].nativeName}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="w-full max-w-[400px] space-y-8">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center">
              <Shield className="w-6 h-6 text-primary-foreground" />
            </div>
          </div>

          {/* Title */}
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold text-foreground">
              {t.auth.title}
            </h1>
            <p className="text-muted-foreground">{t.auth.subtitle}</p>
          </div>

          {/* OAuth Buttons */}
          <div className="space-y-3">
            <Button
              variant="outline"
              className="w-full h-11 justify-center gap-3 font-normal"
              onClick={() => handleOAuthLogin('google')}
              disabled={loading}
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="currentColor"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="currentColor"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="currentColor"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="currentColor"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              {t.auth.continueWithGoogle}
            </Button>

            <Button
              variant="outline"
              className="w-full h-11 justify-center gap-3 font-normal"
              onClick={() => handleOAuthLogin('github')}
              disabled={loading}
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              {t.auth.continueWithGithub}
            </Button>
          </div>

          {/* Divider */}
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-4 text-muted-foreground">{t.auth.orContinueWith}</span>
            </div>
          </div>

          {/* Email Form */}
          <form onSubmit={handleEmailContinue} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-medium text-foreground">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder={t.auth.emailPlaceholder}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="h-11"
                disabled={loading}
              />
            </div>

            {showPasswordField && (
              <div className="space-y-2 animate-fade-in">
                <Label htmlFor="password" className="text-sm font-medium text-foreground">
                  Password
                </Label>
                <Input
                  id="password"
                  type="password"
                  placeholder={t.auth.passwordPlaceholder}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-11"
                  disabled={loading}
                />
              </div>
            )}

            <Button
              type="submit"
              className="w-full h-11 bg-foreground text-background hover:bg-foreground/90"
              disabled={loading}
            >
              {loading 
                ? (isLogin ? t.auth.signingIn : t.auth.creatingAccount)
                : (showPasswordField 
                    ? (isLogin ? t.auth.signIn : t.auth.signUp)
                    : t.auth.continueWithEmail)
              }
            </Button>

            {/* Toggle between login and signup */}
            <p className="text-center text-sm text-muted-foreground">
              {isLogin ? t.auth.noAccount : t.auth.hasAccount}{' '}
              <button
                type="button"
                onClick={toggleMode}
                className="text-primary hover:underline font-medium"
              >
                {isLogin ? t.auth.signUp : t.auth.signIn}
              </button>
            </p>
          </form>
        </div>
      </div>

      {/* Right side - Gradient Background */}
      <div className="hidden lg:block lg:w-1/2 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-orange-100 via-blue-200 to-pink-300" />
        
        {/* Floating prompt card */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px]">
          <div className="bg-white/90 backdrop-blur-sm rounded-2xl px-6 py-4 shadow-xl flex items-center gap-4">
            <span className="text-gray-700 flex-1">{t.auth.subtitle}</span>
            <div className="w-10 h-10 rounded-full bg-gray-900 flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Auth;
