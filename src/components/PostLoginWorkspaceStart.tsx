import { useState, useCallback, useEffect, useRef } from 'react';
import { flushSync } from 'react-dom';
import { useOutletContext } from 'react-router-dom';
import { toast } from 'sonner';
import { TopNavbar } from '@/components/TopNavbar';
import { useLanguage } from '@/contexts/LanguageContext';
import {
  AnalysisInputComposer,
  type EnsureProjectContext,
  type UploadedAttachment,
} from '@/components/AnalysisInputComposer';
import type { WorkspaceOutletContext } from '@/components/AppWorkspaceShell';
import { AUTO_PROJECT_TITLE_MAX_LEN, deriveAutoProjectTitle } from '@/lib/deriveAutoProjectTitle';

export interface PostLoginWorkspaceStartProps {
  onStart: (
    projectName: string,
    input: string,
    attachments: UploadedAttachment[],
    modelId?: string,
    opts?: { existingProjectId?: string },
  ) => boolean | Promise<boolean>;
  ensureProjectForLanding: (title: string) => Promise<string | null>;
  /**
   * Disables the transition composer like a live analysis turn. Parent should pass false: opening this flow
   * from the sidebar while another project is still streaming must not lock the UI.
   */
  isAnalyzing: boolean;
  onAbort?: () => void;
}

function StartComposerColumn({
  composerKey,
  disableComposer,
  submitting,
  onAbort,
  handleComposerSubmit,
  displayTitle,
  createdProjectId,
  ensureProjectId,
}: {
  composerKey: number;
  disableComposer: boolean;
  submitting: boolean;
  onAbort?: () => void;
  displayTitle: string | null;
  createdProjectId: string | null;
  ensureProjectId: (ctx: EnsureProjectContext) => Promise<string | null>;
  handleComposerSubmit: (
    input: string,
    attachments: UploadedAttachment[],
    modelId?: string,
  ) => void;
}) {
  const { t } = useLanguage();

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-auto px-4 py-5 sm:px-5 sm:py-6">
      <div className="mx-auto w-full max-w-3xl space-y-4 sm:space-y-5">
        <div className="space-y-2 text-center">
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">{t.startPage.title}</h2>
          <p className="text-sm text-muted-foreground">{t.startPage.hint}</p>
          {displayTitle && createdProjectId ? (
            <p className="text-sm font-medium text-foreground" title={displayTitle}>
              {t.startPage.activeProjectLabel}: {displayTitle}
            </p>
          ) : null}
        </div>

        <AnalysisInputComposer
          key={composerKey}
          onSubmit={handleComposerSubmit}
          isAnalyzing={disableComposer}
          isSubmitting={submitting}
          onAbort={onAbort}
          uploadSessionId={createdProjectId}
          ensureProjectId={ensureProjectId}
          clearAfterSubmit={false}
          textareaMinHeightClass="min-h-[min(22vh,140px)] sm:min-h-[min(20vh,160px)]"
          textareaMaxHeightClass="max-h-[min(34vh,260px)]"
          wrapperClassName="shadow-sm"
        />
      </div>
    </div>
  );
}

export function PostLoginWorkspaceStart({
  onStart,
  ensureProjectForLanding,
  isAnalyzing,
  onAbort,
}: PostLoginWorkspaceStartProps) {
  const { openMobileSidebar } = useOutletContext<WorkspaceOutletContext>();
  const [autoProjectTitle, setAutoProjectTitle] = useState<string | null>(null);
  const [createdProjectId, setCreatedProjectId] = useState<string | null>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [composerKey, setComposerKey] = useState(0);
  const createdProjectIdRef = useRef<string | null>(null);
  const autoProjectTitleRef = useRef<string | null>(null);
  const createInFlightRef = useRef<Promise<string | null> | null>(null);

  const { t } = useLanguage();

  useEffect(() => {
    createdProjectIdRef.current = createdProjectId;
  }, [createdProjectId]);

  useEffect(() => {
    autoProjectTitleRef.current = autoProjectTitle;
  }, [autoProjectTitle]);

  const ensureProjectId = useCallback(
    async (ctx: EnsureProjectContext): Promise<string | null> => {
      if (createdProjectIdRef.current) return createdProjectIdRef.current;

      if (!createInFlightRef.current) {
        createInFlightRef.current = (async () => {
          setCreatingProject(true);
          try {
            const title = deriveAutoProjectTitle({
              userText: ctx.userText,
              fileNames: ctx.fileNames,
              fallbackLabel: t.sidebar.newConversation,
              maxLen: AUTO_PROJECT_TITLE_MAX_LEN,
            });
            const id = await ensureProjectForLanding(title);
            if (id) {
              flushSync(() => {
                setCreatedProjectId(id);
                setAutoProjectTitle(title);
              });
              createdProjectIdRef.current = id;
              autoProjectTitleRef.current = title;
            }
            return id;
          } finally {
            setCreatingProject(false);
          }
        })().finally(() => {
          createInFlightRef.current = null;
        });
      }
      return createInFlightRef.current;
    },
    [ensureProjectForLanding, t.sidebar.newConversation],
  );

  const handleComposerSubmit = useCallback(
    async (input: string, attachments: UploadedAttachment[], modelId?: string) => {
      const pid = createdProjectIdRef.current;
      const previousTitle = autoProjectTitleRef.current?.trim();
      if (!pid || !previousTitle) {
        toast.error(t.startPage.projectCreateFailed);
        return;
      }
      // Re-derive from submit-time text + files so "upload first, type later" gets a text-based title, not only filenames.
      const refinedName = deriveAutoProjectTitle({
        userText: input.trim(),
        fileNames: attachments.map((a) => a.filename),
        fallbackLabel: previousTitle,
        maxLen: AUTO_PROJECT_TITLE_MAX_LEN,
      });
      setSubmitting(true);
      try {
        const ok = await onStart(
          refinedName,
          input,
          attachments,
          modelId,
          { existingProjectId: pid },
        );
        if (ok) {
          setAutoProjectTitle(null);
          setCreatedProjectId(null);
          createdProjectIdRef.current = null;
          autoProjectTitleRef.current = null;
          setComposerKey((k) => k + 1);
        }
      } finally {
        setSubmitting(false);
      }
    },
    [onStart, t.startPage.projectCreateFailed],
  );

  const disableComposer = submitting || isAnalyzing || creatingProject;

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-sidebar text-foreground">
      <TopNavbar onMobileSidebarOpen={openMobileSidebar} blocksCount={0} />

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-sidebar">
        <StartComposerColumn
          composerKey={composerKey}
          disableComposer={disableComposer}
          submitting={submitting || creatingProject}
          onAbort={onAbort}
          displayTitle={autoProjectTitle}
          createdProjectId={createdProjectId}
          ensureProjectId={ensureProjectId}
          handleComposerSubmit={handleComposerSubmit}
        />
      </div>
    </div>
  );
}
