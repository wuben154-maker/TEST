import { useState, useCallback, useEffect, useRef } from 'react';
import { flushSync } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  AnalysisInputComposer,
  type UploadedAttachment,
  type EnsureProjectContext,
} from '@/components/AnalysisInputComposer';
import { useWorkspaceProjects } from '@/contexts/WorkspaceProjectsContext';
import { useAuth } from '@/hooks/useAuth';
import { useLanguage } from '@/contexts/LanguageContext';
import { deriveAutoProjectTitle, AUTO_PROJECT_TITLE_MAX_LEN } from '@/lib/deriveAutoProjectTitle';

export type MarketingLaunchState = {
  projectName: string;
  input: string;
  attachments: UploadedAttachment[];
  modelId?: string;
  existingProjectId: string;
};

/** Marketing hero composer: guests → `/auth`; signed-in → same tooling as `/start` then navigate with launch payload */
export function MarketingHomeComposer({ wrapperClassName }: { wrapperClassName?: string }) {
  const { user } = useAuth();
  return user ? (
    <MarketingHomeComposerAuthenticated wrapperClassName={wrapperClassName} />
  ) : (
    <MarketingHomeComposerGuest wrapperClassName={wrapperClassName} />
  );
}

function MarketingHomeComposerGuest({ wrapperClassName }: { wrapperClassName?: string }) {
  const navigate = useNavigate();
  const { t } = useLanguage();

  const onSubmitGuest = useCallback(
    (input: string, _attachments: UploadedAttachment[], modelId?: string) => {
      const qs = new URLSearchParams();
      if (input.trim()) qs.set('q', input.trim());
      if (modelId?.trim()) qs.set('model', modelId.trim());
      const suffix = qs.toString();
      navigate(suffix ? `/auth?${suffix}` : '/auth');
    },
    [navigate],
  );

  return (
    <AnalysisInputComposer
      marketingGuest
      onSubmit={onSubmitGuest}
      isAnalyzing={false}
      clearAfterSubmit
      textareaMinHeightClass="min-h-[min(22vh,140px)] sm:min-h-[min(20vh,160px)]"
      textareaMaxHeightClass="max-h-[min(34vh,260px)]"
      wrapperClassName={wrapperClassName ?? ''}
      placeholder={t.marketing.heroComposerPlaceholder}
    />
  );
}

function MarketingHomeComposerAuthenticated({ wrapperClassName }: { wrapperClassName?: string }) {
  const navigate = useNavigate();
  const { createProject, selectProject } = useWorkspaceProjects();
  const { t } = useLanguage();

  const [autoProjectTitle, setAutoProjectTitle] = useState<string | null>(null);
  const [createdProjectId, setCreatedProjectId] = useState<string | null>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [composerKey, setComposerKey] = useState(0);
  const createdProjectIdRef = useRef<string | null>(null);
  const autoProjectTitleRef = useRef<string | null>(null);
  const createInFlightRef = useRef<Promise<string | null> | null>(null);

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
            const created = await createProject(title);
            if (!created?.id) return null;
            flushSync(() => {
              setCreatedProjectId(created.id);
              setAutoProjectTitle(title);
              selectProject(created.id);
            });
            createdProjectIdRef.current = created.id;
            autoProjectTitleRef.current = title;
            return created.id;
          } finally {
            setCreatingProject(false);
          }
        })().finally(() => {
          createInFlightRef.current = null;
        });
      }
      return createInFlightRef.current;
    },
    [createProject, selectProject, t.sidebar.newConversation],
  );

  const handleComposerSubmit = useCallback(
    async (input: string, attachments: UploadedAttachment[], modelId?: string) => {
      const pid = createdProjectIdRef.current;
      const previousTitle = autoProjectTitleRef.current?.trim();
      if (!pid || !previousTitle) {
        toast.error(t.startPage.projectCreateFailed);
        return;
      }
      const refinedName = deriveAutoProjectTitle({
        userText: input.trim(),
        fileNames: attachments.map((a) => a.filename),
        fallbackLabel: previousTitle,
        maxLen: AUTO_PROJECT_TITLE_MAX_LEN,
      });

      const payload: MarketingLaunchState = {
        projectName: refinedName,
        input,
        attachments,
        modelId,
        existingProjectId: pid,
      };

      setSubmitting(true);
      try {
        navigate('/start', { state: { marketingLaunch: payload } });
        setAutoProjectTitle(null);
        setCreatedProjectId(null);
        createdProjectIdRef.current = null;
        autoProjectTitleRef.current = null;
        setComposerKey((k) => k + 1);
      } finally {
        setSubmitting(false);
      }
    },
    [navigate, t.startPage.projectCreateFailed],
  );

  return (
    <AnalysisInputComposer
      key={composerKey}
      onSubmit={handleComposerSubmit}
      isAnalyzing={false}
      isSubmitting={submitting || creatingProject}
      ensureProjectId={ensureProjectId}
      uploadSessionId={createdProjectId}
      clearAfterSubmit={false}
      textareaMinHeightClass="min-h-[min(22vh,140px)] sm:min-h-[min(20vh,160px)]"
      textareaMaxHeightClass="max-h-[min(34vh,260px)]"
      wrapperClassName={wrapperClassName ?? ''}
      placeholder={t.marketing.heroComposerPlaceholder}
    />
  );
}
