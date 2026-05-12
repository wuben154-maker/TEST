import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { StreamingStateProvider } from "@/contexts/StreamingStateContext";
import Index from "./pages/Index";
import OfficialSite from "./pages/OfficialSite";
import OfficialPricing from "./pages/OfficialPricing";
import Auth from "./pages/Auth";
import Billing from "./pages/Billing";
import Usage from "./pages/Usage";
import AccountOverview from "./pages/AccountOverview";
import AccountSettings from "./pages/AccountSettings";
import SubagentCatalog from "./pages/SubagentCatalog";
import SkillCatalog from "./pages/SkillCatalog";
import KnowledgeBase from "./pages/KnowledgeBase";
import SharedReport from "./pages/SharedReport";
import NotFound from "./pages/NotFound";
import MarketingSolutionPage from "./pages/marketing/MarketingSolutionPage";
import MarketingBlogPage from "./pages/marketing/MarketingBlogPage";
import MarketingHelpPage from "./pages/marketing/MarketingHelpPage";
import MarketingProductLogPage from "./pages/marketing/MarketingProductLogPage";
import { AppWorkspaceShell } from "@/components/AppWorkspaceShell";
import { WorkspaceProjectsProvider } from "@/contexts/WorkspaceProjectsContext";

const queryClient = new QueryClient();

// App component with language and auth providers
const App = () => (
  <QueryClientProvider client={queryClient}>
    <LanguageProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <AuthProvider>
            <StreamingStateProvider>
              <WorkspaceProjectsProvider>
                <Routes>
                  <Route path="/" element={<OfficialSite />} />
                  <Route path="/pricing" element={<OfficialPricing />} />
                  <Route path="/blog" element={<MarketingBlogPage />} />
                  <Route path="/help" element={<MarketingHelpPage />} />
                  <Route path="/product-log" element={<MarketingProductLogPage />} />
                  <Route path="/solutions/:slug" element={<MarketingSolutionPage />} />
                  <Route path="/auth" element={<Auth />} />
                  <Route path="/share/:token" element={<SharedReport />} />
                  <Route element={<AppWorkspaceShell />}>
                    <Route path="/start" element={<Index />} />
                    <Route path="/billing" element={<Billing />} />
                    <Route path="/usage" element={<Usage />} />
                    <Route path="/account/overview" element={<AccountOverview />} />
                    <Route path="/account/settings" element={<AccountSettings />} />
                    <Route path="/catalog/subagents" element={<SubagentCatalog />} />
                    <Route path="/catalog/skills" element={<SkillCatalog />} />
                    <Route path="/knowledge" element={<KnowledgeBase />} />
                  </Route>
                  {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </WorkspaceProjectsProvider>
            </StreamingStateProvider>
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </LanguageProvider>
  </QueryClientProvider>
);

export default App;
