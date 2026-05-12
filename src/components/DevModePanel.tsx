import { memo, useState, useEffect } from 'react';
import { Bug, X, Trash2, ChevronDown, ChevronUp, ChevronRight, Copy, Check, RefreshCw, Server, Brain, Target, Tag } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import type { SSEEventLog, AnalysisMode } from '@/types/analysis';
import { backendApi, BackendHealthInfo } from '@/lib/api-client';
import { InputUnderstanding } from '@/types/analysis';
import { useLanguage } from '@/contexts/LanguageContext';

interface DevModePanelProps {
  isOpen: boolean;
  onToggle: () => void;
  sseEventLogs: SSEEventLog[];
  onClearLogs: () => void;
  analysisMode: AnalysisMode;
  understanding?: InputUnderstanding | null;
}

const toRecord = (value: unknown): Record<string, unknown> | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
};

interface TaskPlanViewItem {
  id: string;
  title: string;
  skillName: string;
  status: string;
  mergeStrategy: string;
  sourceTaskIds: string;
  files: string[];
}

const extractTaskPlanItems = (rawData: Record<string, unknown> | undefined): TaskPlanViewItem[] => {
  if (!rawData) return [];
  const plan = toRecord(rawData.plan);
  if (!plan || !Array.isArray(plan.tasks)) return [];

  return plan.tasks
    .map((task) => toRecord(task))
    .filter((task): task is Record<string, unknown> => !!task)
    .map((task) => {
      const context = toRecord(task.context);
      const files = Array.isArray(context?.files)
        ? context.files
            .map((f) => toRecord(f))
            .filter((f): f is Record<string, unknown> => !!f)
            .map((f) => String(f.filename ?? 'unknown'))
        : [];

      const sourceIds = Array.isArray(context?.sourceTaskIds)
        ? context.sourceTaskIds.map((id) => String(id)).join(', ')
        : '-';

      return {
        id: String(task.id ?? '-'),
        title: String(task.title ?? 'Untitled Task'),
        skillName: String(task.skillName ?? '-'),
        status: String(task.status ?? '-'),
        mergeStrategy: String(context?.mergeStrategy ?? '-'),
        sourceTaskIds: sourceIds,
        files,
      };
    });
};

// Event type color mapping.
const eventTypeColors: Record<string, string> = {
  // Core events
  step: 'bg-blue-500/20 text-blue-400',
  reasoning: 'bg-purple-500/20 text-purple-400',
  understanding: 'bg-cyan-500/20 text-cyan-400',
  conclusion: 'bg-lime-500/20 text-lime-400',
  error: 'bg-red-500/20 text-red-400',
  done: 'bg-gray-500/20 text-gray-400',
  
  // Debug events (developer-facing only)
  debug: 'bg-rose-600/30 text-rose-300 border border-rose-500/50',
  internal: 'bg-yellow-600/20 text-yellow-400',
  
  // Tool invocation events
  tool_call: 'bg-amber-500/20 text-amber-400',
  tool_result: 'bg-green-500/20 text-green-400',
  
  // Task planning events
  task_plan: 'bg-pink-500/20 text-pink-400',
  task_start: 'bg-indigo-500/20 text-indigo-400',
  task_step: 'bg-violet-500/20 text-violet-400',
  task_complete: 'bg-emerald-500/20 text-emerald-400',
  task_summary: 'bg-teal-500/20 text-teal-400',
  next_actions: 'bg-orange-500/20 text-orange-400',
  
  // Workflow step events
  workflow_step: 'bg-sky-500/20 text-sky-400',
  
  // Skill subagent events
  skill_start: 'bg-fuchsia-500/20 text-fuchsia-400',
  skill_complete: 'bg-emerald-500/20 text-emerald-400',
  skill_reasoning: 'bg-violet-500/20 text-violet-400',
  skill_error: 'bg-rose-500/20 text-rose-400',
  
  // Subagent events
  subagent_start: 'bg-indigo-500/20 text-indigo-400',
  subagent_complete: 'bg-teal-500/20 text-teal-400',
};

const EventLogItem = memo(function EventLogItem({ log }: { log: SSEEventLog }) {
  const { t } = useLanguage();
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  
  const colorClass = eventTypeColors[log.type] || 'bg-gray-500/20 text-gray-400';
  const date = new Date(log.timestamp);
  const timeStr = `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}:${date.getSeconds().toString().padStart(2, '0')}.${date.getMilliseconds().toString().padStart(3, '0')}`;
  
  const hasRawData = log.rawData && Object.keys(log.rawData).length > 0;
  const jsonString = hasRawData ? JSON.stringify(log.rawData, null, 2) : '';
  const taskPlanItems = log.type === 'task_plan'
    ? extractTaskPlanItems(log.rawData)
    : [];
  
  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (jsonString) {
      await navigator.clipboard.writeText(jsonString);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };
  
  return (
    <div className="border-b border-border/20 last:border-b-0">
      {/* Main row - click to expand */}
      <button
        onClick={() => hasRawData && setIsExpanded(!isExpanded)}
        className={cn(
          "w-full flex items-center gap-2 py-1.5 px-2 text-left text-xs font-mono transition-colors",
          hasRawData && "hover:bg-muted/30 cursor-pointer",
          isExpanded && "bg-muted/20"
        )}
      >
        {/* Expand arrow */}
        <span className={cn(
          "flex-shrink-0 w-4 transition-transform duration-200",
          isExpanded && "rotate-90",
          !hasRawData && "opacity-0"
        )}>
          <ChevronRight className="w-3 h-3 text-muted-foreground/50" />
        </span>
        
        {/* Timestamp */}
        <span className="text-muted-foreground/50 flex-shrink-0 w-20">
          {timeStr}
        </span>
        
        {/* Event type */}
        <span className={cn(
          "px-1.5 py-0.5 rounded text-[10px] font-medium flex-shrink-0 min-w-[80px] text-center",
          colorClass
        )}>
          {log.type}
        </span>
        
        {/* Event ID */}
        <span className="text-foreground/70 flex-shrink-0 w-28 truncate" title={log.id}>
          {log.id}
        </span>
        
        {/* Preview */}
        {log.preview && (
          <span className="text-muted-foreground/60 truncate flex-1" title={log.preview}>
            {log.preview}
          </span>
        )}
      </button>
      
      {/* Expanded JSON details */}
      {isExpanded && hasRawData && (
        <div className="relative bg-muted/10 border-t border-border/20">
          {/* Copy button */}
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-1 right-1 h-6 w-6 z-10"
            onClick={handleCopy}
            title={t.devMode.copyJson}
          >
            {copied ? (
              <Check className="w-3 h-3 text-emerald-500" />
            ) : (
              <Copy className="w-3 h-3 text-muted-foreground" />
            )}
          </Button>
          
          {/* Parsed task plan view */}
          {log.type === 'task_plan' && taskPlanItems.length > 0 && (
            <div className="px-2 pt-2 space-y-2">
              {taskPlanItems.map((task) => (
                <div key={task.id} className="rounded border border-border/40 bg-background/30 px-2 py-1.5">
                  <div className="text-[10px] font-medium text-foreground/90 truncate">{task.title}</div>
                  <div className="text-[10px] text-muted-foreground/70 font-mono">
                    {task.id} · {task.skillName} · {task.status}
                  </div>
                  <div className="text-[10px] text-muted-foreground/70 mt-1">
                    merge: {task.mergeStrategy} | source: {task.sourceTaskIds}
                  </div>
                  <div className="text-[10px] text-muted-foreground/70 truncate mt-1">
                    files: {task.files.length > 0 ? task.files.join(', ') : '-'}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* JSON content */}
          <pre className="p-2 pr-8 text-[10px] leading-relaxed text-foreground/80 overflow-x-auto max-h-[200px] overflow-y-auto">
            {jsonString}
          </pre>
        </div>
      )}
    </div>
  );
});

// Mode indicator config (currently DeepAgent only).
const modeConfig: Record<AnalysisMode, { label: string; color: string; bgColor: string }> = {
  'unknown': { label: '', color: 'text-gray-400', bgColor: 'bg-gray-500/20' },
  'deepagent': { label: 'DeepAgent', color: 'text-emerald-400', bgColor: 'bg-emerald-500/20' },
};

export const DevModePanel = memo(function DevModePanel({ 
  isOpen, 
  onToggle, 
  sseEventLogs,
  onClearLogs,
  analysisMode,
  understanding,
}: DevModePanelProps) {
  const { t } = useLanguage();
  const [isExpanded, setIsExpanded] = useState(true);
  const [showBackendInfo, setShowBackendInfo] = useState(false);
  const [showUnderstanding, setShowUnderstanding] = useState(false);
  const [backendHealth, setBackendHealth] = useState<BackendHealthInfo | null>(null);
  const [backendLoading, setBackendLoading] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);
  
  const fetchBackendHealth = async () => {
    setBackendLoading(true);
    setBackendError(null);
    const { data, error } = await backendApi.getHealth();
    setBackendLoading(false);
    if (error) {
      setBackendError(error.message);
    } else {
      setBackendHealth(data);
    }
  };
  
  useEffect(() => {
    if (showBackendInfo && !backendHealth && !backendLoading) {
      fetchBackendHealth();
    }
  }, [showBackendInfo]);
  
  if (!isOpen) {
    return (
      <Button
        variant="ghost"
        size="icon"
        className="fixed bottom-4 right-4 z-50 h-10 w-10 rounded-full bg-muted/80 backdrop-blur-sm border border-border/50 shadow-lg hover:bg-muted"
        onClick={onToggle}
        title={t.devMode.open}
      >
        <Bug className="w-4 h-4 text-amber-500" />
      </Button>
    );
  }
  
  return (
    <div className="fixed bottom-4 right-4 z-50 w-[560px] max-w-[90vw] bg-popover/95 backdrop-blur-md border border-border rounded-lg shadow-xl animate-in slide-in-from-bottom-2">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/50">
        <div className="flex items-center gap-2">
          <Bug className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-medium">{t.devMode.title}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
            {sseEventLogs.length} {t.devMode.events}
          </span>
          {/* Mode indicator */}
          <span className={cn(
            "text-[10px] px-2 py-0.5 rounded-full font-medium",
            modeConfig[analysisMode].bgColor,
            modeConfig[analysisMode].color
          )}>
            {analysisMode === 'unknown' ? t.devMode.detecting : modeConfig[analysisMode].label}
          </span>
        </div>
        
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className={cn("h-7 w-7", showUnderstanding && "bg-muted", understanding && "text-cyan-400")}
            onClick={() => setShowUnderstanding(!showUnderstanding)}
            title={t.devMode.intentDetails}
          >
            <Brain className="w-3.5 h-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className={cn("h-7 w-7", showBackendInfo && "bg-muted")}
            onClick={() => setShowBackendInfo(!showBackendInfo)}
            title={t.devMode.backendInfo}
          >
            <Server className="w-3.5 h-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setIsExpanded(!isExpanded)}
            title={isExpanded ? t.devMode.collapse : t.devMode.expand}
          >
            {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-destructive"
            onClick={onClearLogs}
            title={t.devMode.clearLogs}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={onToggle}
            title={t.devMode.close}
          >
            <X className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>
      
      {/* Understanding Info Panel */}
      {showUnderstanding && (
        <div className="px-3 py-2 border-b border-border/50 bg-cyan-500/5">
          <div className="flex items-center gap-2 mb-2">
            <Brain className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-xs font-medium text-foreground/80">{t.devMode.intentDetails}</span>
            {understanding && (
              <span className={cn(
                "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                understanding.confidence >= 0.8 
                  ? "bg-emerald-500/20 text-emerald-400"
                  : understanding.confidence >= 0.6
                    ? "bg-amber-500/20 text-amber-400"
                    : "bg-gray-500/20 text-gray-400"
              )}>
                {Math.round(understanding.confidence * 100)}% {t.devMode.confidence}
              </span>
            )}
          </div>
          
          {!understanding ? (
            <div className="text-xs text-muted-foreground/60">{t.devMode.noIntentData}</div>
          ) : (
            <div className="space-y-2">
              {/* Summary */}
              {understanding.summary && (
                <div className="text-xs text-foreground/80 leading-relaxed">
                  {understanding.summary}
                </div>
              )}
              
              {/* Analysis Goals */}
              {understanding.analysisGoals && understanding.analysisGoals.length > 0 && (
                <div>
                  <div className="flex items-center gap-1.5 mb-1">
                    <Target className="w-3 h-3 text-muted-foreground/60" />
                    <span className="text-[10px] text-muted-foreground">{t.devMode.analysisGoals}</span>
                  </div>
                  <div className="flex flex-wrap gap-1 pl-4">
                    {understanding.analysisGoals.map((goal, idx) => {
                      const goalText = typeof goal === 'string' 
                        ? goal 
                        : (goal as { text?: string })?.text ?? JSON.stringify(goal);
                      return (
                        <span 
                          key={idx}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary/80"
                        >
                          {goalText}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
              
              {/* Key Entities */}
              {understanding.keyEntities && understanding.keyEntities.length > 0 && (
                <div>
                  <div className="flex items-center gap-1.5 mb-1">
                    <Tag className="w-3 h-3 text-muted-foreground/60" />
                    <span className="text-[10px] text-muted-foreground">
                      {t.devMode.identifiedEntities} ({understanding.keyEntities.length})
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1 pl-4">
                    {understanding.keyEntities.slice(0, 8).map((entity, idx) => {
                      const entityText = typeof entity === 'string'
                        ? entity
                        : (entity as { text?: string })?.text ?? JSON.stringify(entity);
                      return (
                        <span 
                          key={idx}
                          className="text-[9px] px-1.5 py-0.5 rounded bg-muted/40 text-foreground/60 font-mono"
                        >
                          {entityText}
                        </span>
                      );
                    })}
                    {understanding.keyEntities.length > 8 && (
                      <span className="text-[9px] text-muted-foreground/50">
                        +{understanding.keyEntities.length - 8}
                      </span>
                    )}
                  </div>
                </div>
              )}
              
              {/* Suggested Approach */}
              {understanding.suggestedApproach && (
                <div className="text-[10px] text-muted-foreground/60 italic mt-1">
                  💡 {understanding.suggestedApproach}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      
      {/* Backend Info Panel */}
      {showBackendInfo && (
        <div className="px-3 py-2 border-b border-border/50 bg-muted/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-foreground/80">{t.devMode.backendStatus}</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={fetchBackendHealth}
              disabled={backendLoading}
              title={t.devMode.refresh}
            >
              <RefreshCw className={cn("w-3 h-3", backendLoading && "animate-spin")} />
            </Button>
          </div>
          
          {backendLoading && (
            <div className="text-xs text-muted-foreground">{t.devMode.checkingBackend}</div>
          )}
          
          {backendError && (
            <div className="text-xs text-destructive">
              {t.devMode.connectionFailed}: {backendError}
            </div>
          )}
          
          {backendHealth && (
            <div className="space-y-2">
              {/* Version & Status */}
              <div className="flex flex-wrap gap-2">
                <span className={cn(
                  "px-2 py-0.5 rounded text-[10px] font-medium",
                  backendHealth.status === 'healthy' 
                    ? "bg-emerald-500/20 text-emerald-400" 
                    : "bg-red-500/20 text-red-400"
                )}>
                  {backendHealth.status}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-500/20 text-blue-400">
                  v{backendHealth.version}
                </span>
                {backendHealth.build_date && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-purple-500/20 text-purple-400">
                    {backendHealth.build_date}
                  </span>
                )}
                <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-cyan-500/20 text-cyan-400">
                  {backendHealth.framework}
                </span>
              </div>
              
              {/* Feature Flags */}
              {backendHealth.feature_flags && (
                <div className="mt-2">
                  <span className="text-[10px] text-muted-foreground mb-1 block">
                    {t.devMode.featureFlags}:
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(backendHealth.feature_flags).map(([key, enabled]) => (
                      <span 
                        key={key}
                        className={cn(
                          "px-1.5 py-0.5 rounded text-[9px] font-mono",
                          enabled 
                            ? "bg-emerald-500/20 text-emerald-400" 
                            : "bg-gray-500/20 text-gray-400 line-through"
                        )}
                      >
                        {key}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Workflow-enabled Skills */}
              {backendHealth.workflow_enabled_skills && backendHealth.workflow_enabled_skills.length > 0 && (
                <div className="mt-2">
                  <span className="text-[10px] text-muted-foreground mb-1 block">
                    {t.devMode.workflowSkills} ({backendHealth.workflow_enabled_skills.length}):
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {backendHealth.workflow_enabled_skills.map((skill) => (
                      <span 
                        key={skill.name}
                        className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-sky-500/20 text-sky-400"
                        title={`${t.devMode.steps}: ${skill.steps.join(' -> ')}`}
                      >
                        {skill.name} ({skill.steps_count})
                      </span>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Skills Summary */}
              {backendHealth.skills && (
                <div className="text-[10px] text-muted-foreground mt-1">
                  {t.devMode.loadedSkills.replace('{count}', String(backendHealth.skills.count))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      
      {/* Event List */}
      {isExpanded && (
        <div className="max-h-[400px] overflow-y-auto">
          {sseEventLogs.length > 0 && (
            <>
              <p className="px-2 py-1 text-[10px] text-muted-foreground/60 border-b border-border/30" title={t.devMode.eventOrderHint}>
                {t.devMode.eventOrderHint}
              </p>
              <p className="px-2 py-1 text-[10px] text-amber-600/80 dark:text-amber-400/90 border-b border-border/30">
                {t.devMode.debugOnlyEventsNote}
              </p>
            </>
          )}
          {sseEventLogs.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground/50">
              {t.devMode.noSseEvents}
            </div>
          ) : (
            <div>
              {sseEventLogs.map((log, idx) => (
                <EventLogItem key={`${log.timestamp}-${idx}`} log={log} />
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* Legend & Tips */}
      {isExpanded && (
        <div className="px-3 py-2 border-t border-border/50 bg-muted/30">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] text-muted-foreground/60">{t.devMode.expandJsonHint}</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(eventTypeColors).slice(0, 10).map(([type, colorClass]) => (
              <span key={type} className={cn(
                "px-1.5 py-0.5 rounded text-[9px] font-medium",
                colorClass
              )}>
                {type}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});

export default DevModePanel;
