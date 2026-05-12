import { useState, useCallback, useEffect } from 'react';
import { Project, ConversationMessage, AnalysisResult, type KnowledgeArchiveNotice } from '@/types/project';
import type { AnalysisTimelineEntry, InputUnderstanding, WorkspaceBlock } from '@/types/analysis';
import { AgentTask, DecisionRequest } from '@/types/analysis';
import {
  extractLatestTaskPlanFromTimeline,
  extractSubagentTaskPlansFromTimeline,
  extractUnderstandingFromTimeline,
  extractTaskSummaryFromTimeline,
  extractWorkspaceTitleFromTimeline,
  estimateThinkingDurationFromTimeline,
} from '@/lib/timelineDisplay';
import { projectsApi, messagesApi } from '@/lib/api-client';
import { parseKnowledgeArchiveFromRow } from '@/lib/knowledgeArchive';
import { collapseSyntheticConclusionMirrorBlock } from '@/lib/collapseSyntheticConclusionMirrorBlock';
import { inferUseWorkspaceTaskPanelFromMessage } from '@/lib/analysisWorkspaceChrome';
import {
  assistantMessageYieldsAnalysisTab,
  buildAnalysisResultFromAssistantMessage,
} from '@/lib/buildAnalysisResultFromAssistantMessage';
import { useAuth } from '@/hooks/useAuth';
import { useLanguage } from '@/contexts/LanguageContext';
import { detectBrowserLanguage, getTranslations } from '@/i18n';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';

/** Optional diagnostics for `reloadProjectMessages` (who triggered the full chat refetch). */
export type ReloadProjectMessagesMeta = {
  reason?: 'progress_restore_finish' | 'unknown';
  /** Present when reason === progress_restore_finish */
  finish_source?: 'poll' | 'bootstrap';
};

/** Use environment (browser) language for project titles - auto-detect user's locale */
const getEnvNewConversationLabel = () =>
  getTranslations(detectBrowserLanguage()).sidebar?.newConversation || 'New Conversation';

const generateId = () => crypto.randomUUID();

function parseMessageBlocks(msg: { blocks?: unknown }): WorkspaceBlock[] | undefined {
  const rawBlocks = msg.blocks;
  if (Array.isArray(rawBlocks)) return rawBlocks as WorkspaceBlock[];
  if (typeof rawBlocks === 'string' && rawBlocks.trim()) {
    try {
      const parsed = JSON.parse(rawBlocks);
      return Array.isArray(parsed) ? parsed : undefined;
    } catch {
      return undefined;
    }
  }
  return undefined;
}

/** Map API message row to conversation message (timeline is canonical; no thinking_steps/__extended). */
function rowToConversation(msg: Record<string, unknown>): ConversationMessage {
  let blocks = parseMessageBlocks(msg);
  const timeline = Array.isArray(msg.timeline) ? (msg.timeline as AnalysisTimelineEntry[]) : [];
  const taskPlan = extractLatestTaskPlanFromTimeline(timeline);
  const understanding =
    extractUnderstandingFromTimeline(timeline) ??
    (msg.understanding && typeof msg.understanding === 'object'
      ? (msg.understanding as InputUnderstanding)
      : null);

  const content = typeof msg.content === 'string' ? msg.content : '';
  if (
    (!blocks || blocks.length === 0) &&
    msg.type === 'assistant' &&
    content.trim().length > 0 &&
    timeline.length === 0
  ) {
    blocks = [
      {
        type: 'analysis',
        id: `legacy-analysis-${msg.id}`,
        content,
        title: '🔍 Analysis Report',
      } as WorkspaceBlock,
    ];
  }

  const taskPlansSubagent = extractSubagentTaskPlansFromTimeline(timeline);
  const thinkingDuration = estimateThinkingDurationFromTimeline(timeline);

  const reqId = msg.request_id;
  const statsRaw = msg.stats && typeof msg.stats === 'object' ? (msg.stats as Record<string, unknown>) : undefined;
  const wtabsRaw = Array.isArray(msg.workspace_tabs) ? (msg.workspace_tabs as any[]) : undefined;
  const kaRaw = (msg as Record<string, unknown>).knowledge_archive;
  const knowledgeArchive = parseKnowledgeArchiveFromRow(kaRaw);

  return collapseSyntheticConclusionMirrorBlock({
    id: String(msg.id),
    type: msg.type as 'user' | 'assistant',
    content,
    reasoning: typeof msg.reasoning === 'string' ? msg.reasoning : undefined,
    blocks,
    timestamp: new Date(String(msg.created_at)),
    thinkingDuration: thinkingDuration > 0 ? thinkingDuration : undefined,
    taskPlan: taskPlan ?? undefined,
    taskPlansSubagent: Object.keys(taskPlansSubagent).length > 0 ? taskPlansSubagent : undefined,
    understanding: understanding ?? undefined,
    taskSummary: extractTaskSummaryFromTimeline(timeline) || undefined,
    timeline,
    requestId: typeof reqId === 'string' && reqId.trim() ? reqId.trim() : undefined,
    stats: statsRaw as ConversationMessage['stats'],
    workspaceTabs: wtabsRaw as ConversationMessage['workspaceTabs'],
    ...(knowledgeArchive ? { knowledgeArchive } : {}),
  });
}

const createEmptyProject = (title: string, id?: string): Project => ({
  id: id || generateId(),
  title,
  messages: [],
  blocks: [],
  analysisResults: [],
  activeResultId: undefined,
  tasks: [],
  decisions: [],
  resolvedDecisions: {},
  createdAt: new Date(),
  updatedAt: new Date(),
});

export function useProjects() {
  const { user } = useAuth();
  const { t } = useLanguage();
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const currentProject =
    projects.find(p => p.id === currentProjectId) ||
    (projects.length > 0 ? projects[0] : createEmptyProject(getEnvNewConversationLabel()));

  // Load projects from database
  // Use user.id as dependency to prevent unnecessary reloads when user object reference changes
  const userId = user?.id;
  
  const loadProjects = useCallback(async () => {
    if (!userId) {
      setProjects([]);
      setCurrentProjectId(null);
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      
      // Fetch projects using API client
      const { data: projectsData, error: projectsError } = await projectsApi.list();

      if (projectsError) throw projectsError;

      if (!projectsData || projectsData.length === 0) {
        setProjects([]);
        setCurrentProjectId(null);
      } else {
        // Fetch messages for all projects
        const messagesByProject: Record<string, ConversationMessage[]> = {};
        const rawMessagesByProject: Record<string, any[]> = {};
        
        for (const p of projectsData) {
          const { data: messagesData } = await messagesApi.listByProject(p.id);
          
          if (messagesData) {
            rawMessagesByProject[p.id] = messagesData;
            messagesByProject[p.id] = messagesData.map((msg: Record<string, unknown>) =>
              rowToConversation(msg),
            );
          }
        }

        // Build projects with messages
        const loadedProjects: Project[] = projectsData.map((p: any) => ({
          id: p.id,
          title: p.title,
          messages: messagesByProject[p.id] || [],
          blocks: [],
          analysisResults: [],
          activeResultId: undefined,
          tasks: [],
          decisions: [],
          resolvedDecisions: {},
          createdAt: new Date(p.created_at),
          updatedAt: new Date(p.updated_at),
        }));

        // Build analysis results from all assistant messages with blocks
        loadedProjects.forEach(p => {
          const assistantMsgsWithBlocks = p.messages.filter(m =>
            m.type === 'assistant' && Array.isArray(m.blocks) && m.blocks.length > 0
          );
          const analysisResults: AnalysisResult[] = assistantMsgsWithBlocks.map((msg, idx) => {
            const msgIndex = p.messages.indexOf(msg);
            const userMsg = msgIndex > 0 ? p.messages.slice(0, msgIndex).reverse().find(m => m.type === 'user') : undefined;
            const rawMsgs = rawMessagesByProject[p.id] || [];
            const rawMsg = rawMsgs.find((m: any) => m.id === msg.id);
            const dbTitle =
              rawMsg?.workspace_title ||
              extractWorkspaceTitleFromTimeline(msg.timeline ?? []);
            const title = dbTitle
              || (userMsg?.content
                  ? userMsg.content.slice(0, 20) + (userMsg.content.length > 20 ? '...' : '')
                  : `${t.projects.analysisTitlePrefix} ${idx + 1}`);
            return {
              id: msg.id,
              title,
              userInput: userMsg?.content || '',
              blocks: msg.blocks!,
              timestamp: msg.timestamp,
              requestId: msg.requestId,
              useWorkspaceTaskPanel: inferUseWorkspaceTaskPanelFromMessage(msg),
              status: 'done' as const,
              stats: msg.stats ?? {},
              workspaceTabs: msg.workspaceTabs ?? [],
            };
          });
          p.analysisResults = analysisResults;
          // Set the last analysis result as active
          if (analysisResults.length > 0) {
            p.activeResultId = analysisResults[analysisResults.length - 1].id;
            p.blocks = analysisResults[analysisResults.length - 1].blocks;
          }
        });

        setProjects(loadedProjects);
        setCurrentProjectId((prev) => {
          if (prev && loadedProjects.some(p => p.id === prev)) return prev;
          return loadedProjects[0]?.id || null;
        });
      }
    } catch (error: unknown) {
      logger.error('projects_load_failed', { error: String(error) });
      const msg = error instanceof Error ? error.message : '';
      const hint =
        msg.includes('Authorization') || msg.includes('401')
          ? ' (请重新登录)'
          : msg.includes('Failed to fetch') || msg.includes('NetworkError')
            ? ' (请检查后端是否运行、endpoints.ts 中 localApiUrl 是否为 http://localhost:8000)'
            : msg.includes('SERVICE_ROLE') || msg.includes('permission')
              ? ' (后端需配置 SUPABASE_SERVICE_ROLE_KEY)'
              : msg
                ? ` (${msg})`
                : '';
      toast.error(t.projects.loadHistoryFailed + hint);
      // Keep prior projects if any; do not inject a local placeholder (would skip post-login landing and break API-bound flows).
      setProjects((prev) => (prev.length > 0 ? prev : []));
    } finally {
      setIsLoading(false);
    }
  }, [userId, t.projects.analysisTitlePrefix, t.projects.loadHistoryFailed]);

  // Load projects on mount and user change
  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const PROJECT_TITLE_MAX_LENGTH = 50;

  const createProject = useCallback(async (title?: string) => {
    if (!user) return null;

    try {
      const finalTitle = title !== undefined && title.trim()
        ? title.trim().slice(0, PROJECT_TITLE_MAX_LENGTH)
        : getEnvNewConversationLabel();
      const { data, error } = await projectsApi.create(finalTitle);

      if (error) throw error;

      const createdProject: Project = {
        ...createEmptyProject(finalTitle),
        id: data.id,
        title: data.title,
        createdAt: new Date(data.created_at),
        updatedAt: new Date(data.updated_at),
      };

      setProjects(prev => [createdProject, ...prev]);
      setCurrentProjectId(createdProject.id);
      return createdProject;
    } catch (error: unknown) {
      logger.error('project_create_failed', { error: String(error) });
      const msg = error instanceof Error ? error.message : String(error);
      const hint =
        msg.includes('Authorization') || msg.includes('401')
          ? ' (请重新登录)'
          : msg.includes('Failed to fetch') || msg.includes('NetworkError')
            ? ' (请检查后端是否运行、VITE_API_MODE 与 endpoints.ts 配置)'
            : msg.includes('SERVICE_ROLE') || msg.includes('permission') || msg.includes('RLS')
              ? ' (后端需配置 SUPABASE_SERVICE_ROLE_KEY)'
              : msg
                ? ` (${msg})`
                : '';
      toast.error(t.projects.createConversationFailed + hint);
      return null;
    }
  }, [user, t.projects.createConversationFailed]);

  const selectProject = useCallback((projectId: string) => {
    setCurrentProjectId(projectId);
  }, []);

  const deleteProject = useCallback(async (projectId: string) => {
    if (!user) return;

    try {
      const { error } = await projectsApi.delete(projectId);

      if (error) throw error;

      setProjects(prev => {
        const filtered = prev.filter(p => p.id !== projectId);
        if (filtered.length === 0) {
          setCurrentProjectId(null);
          return filtered;
        }
        if (currentProjectId === projectId) {
          setCurrentProjectId(filtered[0].id);
        }
        return filtered;
      });
    } catch (error) {
      logger.error('project_delete_failed', { error: String(error) });
      toast.error(t.projects.deleteConversationFailed);
    }
  }, [user, currentProjectId, t.projects.deleteConversationFailed]);

  const updateProjectTitle = useCallback(async (projectId: string, title: string) => {
    if (!user) return;

    try {
      const { error } = await projectsApi.update(projectId, { title });

      if (error) throw error;

      setProjects(prev => prev.map(p => 
        p.id === projectId 
          ? { ...p, title, updatedAt: new Date() }
          : p
      ));
    } catch (error) {
      logger.error('project_title_update_failed', { error: String(error) });
    }
  }, [user]);

  type AddMessageOptions = {
    updateLocal?: boolean;
  };

  const addMessage = useCallback(async (
    projectId: string,
    message: Omit<ConversationMessage, 'id'>,
    options: AddMessageOptions = {}
  ) => {
    if (!user) return null;

    const messageId = generateId();
    const newMessage: ConversationMessage = {
      ...message,
      id: messageId,
    };

    const shouldUpdateLocal = options.updateLocal !== false;

    try {
      const { error } = await messagesApi.create({
        project_id: projectId,
        type: message.type,
        content: message.content,
        reasoning: message.reasoning || undefined,
        blocks: message.blocks,
        timeline: message.timeline,
        stats: message.stats as Record<string, unknown> | undefined,
        workspace_tabs: message.workspaceTabs as any[] | undefined,
      });

      if (error) throw error;

      // Auto-update title from first user message
      const project = projects.find(p => p.id === projectId);
      if (project && project.messages.length === 0 && message.type === 'user') {
        const newTitle = message.content.slice(0, 30) + (message.content.length > 30 ? '...' : '');
        await updateProjectTitle(projectId, newTitle);
      }

      if (shouldUpdateLocal) {
        setProjects(prev => prev.map(p => 
          p.id === projectId 
            ? { 
                ...p, 
                messages: [...p.messages, newMessage],
                updatedAt: new Date(),
              }
            : p
        ));
      }

      return newMessage;
    } catch (error: unknown) {
      logger.error('project_message_add_failed', { error: String(error) });
      const msg = error instanceof Error ? error.message : '';
      toast.error(msg.includes('SERVICE_ROLE') ? msg : t.projects.saveMessageFailed);
      return null;
    }
  }, [user, projects, updateProjectTitle, t.projects.saveMessageFailed]);

  const updateLastMessage = useCallback((projectId: string, updates: Partial<ConversationMessage>) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId || p.messages.length === 0) return p;
      const messages = [...p.messages];
      const lastIndex = messages.length - 1;
      messages[lastIndex] = { ...messages[lastIndex], ...updates };
      return { ...p, messages, updatedAt: new Date() };
    }));
  }, []);

  const updateProjectBlocks = useCallback((projectId: string, blocks: WorkspaceBlock[]) => {
    setProjects(prev => prev.map(p => 
      p.id === projectId 
        ? { ...p, blocks, updatedAt: new Date() }
        : p
    ));
  }, []);

  const updateProjectTasks = useCallback((projectId: string, tasks: AgentTask[]) => {
    setProjects(prev => prev.map(p => 
      p.id === projectId 
        ? { ...p, tasks, updatedAt: new Date() }
        : p
    ));
  }, []);

  const updateProjectDecisions = useCallback((
    projectId: string, 
    decisions: DecisionRequest[], 
    resolvedDecisions: Record<string, string[]>
  ) => {
    setProjects(prev => prev.map(p => 
      p.id === projectId 
        ? { ...p, decisions, resolvedDecisions, updatedAt: new Date() }
        : p
    ));
  }, []);

  const reloadProjectMessages = useCallback(async (
    projectId: string,
    meta?: ReloadProjectMessagesMeta,
  ) => {
    if (!userId) return;
    const t0 = Date.now();
    const reason = meta?.reason ?? 'unknown';
    logger.info('reload_project_messages_begin', {
      project_id: projectId,
      reason,
      finish_source: meta?.finish_source,
    });
    try {
      const { data: messagesData } = await messagesApi.listByProject(projectId);
      if (!messagesData) {
        logger.info('reload_project_messages_empty_response', {
          project_id: projectId,
          reason,
          duration_ms: Date.now() - t0,
        });
        return;
      }
      const loaded: ConversationMessage[] = messagesData.map((msg: Record<string, unknown>) =>
        rowToConversation(msg),
      );

      setProjects(prev => prev.map(p => {
        if (p.id !== projectId) return p;
        const assistantMsgsWithBlocks = loaded.filter(m =>
          m.type === 'assistant' && Array.isArray(m.blocks) && m.blocks.length > 0
        );
        const analysisResults: AnalysisResult[] = assistantMsgsWithBlocks.map((msg, idx) => {
          const msgIndex = loaded.indexOf(msg);
          const userMsg = msgIndex > 0 ? loaded.slice(0, msgIndex).reverse().find(m => m.type === 'user') : undefined;
          const rawMsg = messagesData?.find((m: any) => m.id === msg.id);
          const dbTitle =
            rawMsg?.workspace_title ||
            extractWorkspaceTitleFromTimeline(msg.timeline ?? []);
          const title = dbTitle
            || (userMsg?.content
                ? userMsg.content.slice(0, 20) + (userMsg.content.length > 20 ? '...' : '')
                : `${t.projects.analysisTitlePrefix} ${idx + 1}`);
          return {
            id: msg.id,
            title,
            userInput: userMsg?.content || '',
            blocks: msg.blocks!,
            timestamp: msg.timestamp,
            requestId: msg.requestId,
            useWorkspaceTaskPanel: inferUseWorkspaceTaskPanelFromMessage(msg),
            status: 'done' as const,
            stats: msg.stats ?? {},
            workspaceTabs: msg.workspaceTabs ?? [],
          };
        });
        return {
          ...p,
          messages: loaded,
          analysisResults,
          activeResultId: analysisResults.length > 0 ? analysisResults[analysisResults.length - 1].id : p.activeResultId,
          blocks: analysisResults.length > 0 ? analysisResults[analysisResults.length - 1].blocks : p.blocks,
          updatedAt: new Date(),
        };
      }));
      logger.info('reload_project_messages_applied', {
        project_id: projectId,
        reason,
        finish_source: meta?.finish_source,
        message_count: loaded.length,
        duration_ms: Date.now() - t0,
      });
    } catch (error) {
      logger.error('project_messages_reload_failed', {
        error: String(error),
        project_id: projectId,
        reason,
        duration_ms: Date.now() - t0,
      });
    }
  }, [userId, t.projects.analysisTitlePrefix]);

  const appendToConversation = useCallback(
    (projectId: string, messages: ConversationMessage[]) => {
      setProjects((prev) =>
        prev.map((p) => {
          if (p.id !== projectId) return p;
          const combined = [...p.messages, ...messages];
          let nextResults = p.analysisResults;
          let activeResultId = p.activeResultId;
          let blocks = p.blocks;

          for (const msg of messages) {
            if (!assistantMessageYieldsAnalysisTab(msg)) {
              continue;
            }
            if (nextResults.some((r) => r.id === msg.id)) continue;

            const result = buildAnalysisResultFromAssistantMessage(
              msg,
              combined,
              t.projects.analysisTitlePrefix,
              nextResults.length,
            );
            nextResults = [...nextResults, result];
            activeResultId = msg.id;
            blocks = msg.blocks;
          }

          return {
            ...p,
            messages: combined,
            analysisResults: nextResults,
            activeResultId,
            blocks,
            updatedAt: new Date(),
          };
        }),
      );
    },
    [t.projects.analysisTitlePrefix],
  );

  // Add a new analysis result to the project
  const addAnalysisResult = useCallback((projectId: string, result: AnalysisResult) => {
    setProjects(prev => prev.map(p => 
      p.id === projectId 
        ? { 
            ...p, 
            analysisResults: [...p.analysisResults, result],
            activeResultId: result.id,
            blocks: result.blocks,
            updatedAt: new Date(),
          }
        : p
    ));
  }, []);

  // Set active analysis result tab
  const setActiveResultId = useCallback((projectId: string, resultId: string) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      const result = p.analysisResults.find(r => r.id === resultId);
      return { 
        ...p, 
        activeResultId: resultId,
        blocks: result?.blocks || [],
        updatedAt: new Date(),
      };
    }));
  }, []);

  // Remove an analysis result from the project
  const removeAnalysisResult = useCallback((projectId: string, resultId: string) => {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId) return p;
      const newResults = p.analysisResults.filter(r => r.id !== resultId);
      let newActiveId = p.activeResultId;
      let newBlocks = p.blocks;
      if (p.activeResultId === resultId) {
        const lastResult = newResults[newResults.length - 1];
        newActiveId = lastResult?.id;
        newBlocks = lastResult?.blocks || [];
      }
      return { 
        ...p, 
        analysisResults: newResults,
        activeResultId: newActiveId,
        blocks: newBlocks,
        updatedAt: new Date(),
      };
    }));
  }, []);

  const updateAnalysisResultTitle = useCallback(async (projectId: string, resultId: string, newTitle: string) => {
    setProjects(prev => prev.map(p =>
      p.id !== projectId ? p : {
        ...p,
        analysisResults: p.analysisResults.map(r =>
          r.id === resultId ? { ...r, title: newTitle } : r
        ),
        updatedAt: new Date(),
      }
    ));
    try {
      await messagesApi.updateTitle(resultId, newTitle);
    } catch (e) {
      logger.error('project_tab_title_persist_failed', { error: String(e) });
    }
  }, []);

  /** Attach knowledge-base deep-link metadata to the assistant turn for ``requestId`` (``null`` clears). */
  const setAssistantKnowledgeArchive = useCallback(
    (projectId: string, requestId: string, archive: KnowledgeArchiveNotice | null) => {
      const rid = (requestId || '').trim();
      if (!rid) return;
      setProjects((prev) =>
        prev.map((p) => {
          if (p.id !== projectId) return p;
          const messages = p.messages.map((m) => {
            if (m.type !== 'assistant') return m;
            if ((m.requestId || '').trim() !== rid) return m;
            return { ...m, knowledgeArchive: archive === null ? undefined : archive };
          });
          return { ...p, messages, updatedAt: new Date() };
        }),
      );
    },
    [],
  );

  return {
    projects,
    currentProject,
    currentProjectId,
    isLoading,
    createProject,
    selectProject,
    deleteProject,
    updateProjectTitle,
    addMessage,
    updateLastMessage,
    updateProjectBlocks,
    updateProjectTasks,
    updateProjectDecisions,
    appendToConversation,
    addAnalysisResult,
    setActiveResultId,
    removeAnalysisResult,
    updateAnalysisResultTitle,
    reloadProjects: loadProjects,
    reloadProjectMessages,
    setAssistantKnowledgeArchive,
  };
}
