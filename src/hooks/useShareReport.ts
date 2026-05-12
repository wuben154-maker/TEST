import { useState } from "react";
import { WorkspaceBlock } from "@/types/analysis";
import { toast } from "sonner";
import { getAuthToken, getClientTimezoneHeaders } from "@/lib/api-client";
import { logger } from "@/lib/logger";
import { activeApiBaseUrl } from "@/lib/config";

export function useShareReport() {
  const [isSharing, setIsSharing] = useState(false);

  const shareAsLink = async (
    blocks: WorkspaceBlock[],
    title: string = "Security Analysis Report",
  ) => {
    setIsSharing(true);
    try {
      const token = getAuthToken();
      const headers: Record<string, string> = {
        ...getClientTimezoneHeaders(),
        "Content-Type": "application/json",
      };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch(`${activeApiBaseUrl}/shared-reports`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          title,
          // Ensure we send plain JSON without circular refs
          blocks: JSON.parse(JSON.stringify(blocks)),
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      const shareUrl = `${window.location.origin}/share/${data.share_token}`;
      await navigator.clipboard.writeText(shareUrl);
      toast.success("Link copied to clipboard!", {
        description: "Share this link with others. Expires in 7 days.",
      });
      return shareUrl;
    } catch (error) {
      logger.error("share_report_failed", { error: String(error) });
      toast.error("Failed to create share link");
      return null;
    } finally {
      setIsSharing(false);
    }
  };

  return {
    shareAsLink,
    isSharing,
  };
}
