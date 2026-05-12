import { useState, useRef, useEffect, useCallback, ChangeEvent } from 'react';
import { Send, Paperclip, Square, X, Loader2 } from 'lucide-react';
import { useVoiceInput } from '@/hooks/useVoiceInput';
import { VoiceMicButton } from './VoiceMicButton';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/contexts/LanguageContext';
import { ModelSelector } from './ModelSelector';
import { ContextUsageBadge } from './ContextUsageBadge';
import { useModelLimits } from '@/hooks/useModelLimits';
import type { ContextUsageState } from '@/types/analysis';
import { getMainUsageSnapshot } from '@/lib/contextUsage';
import { analysisEndpoints, maxUploadBytesPerFile, maxUploadFilesPerBatch } from '@/lib/config';
import { getAuthToken, getClientTimezoneHeaders } from '@/lib/api-client';

export interface UploadedAttachment {
  filename: string;
  content_type: string;
  content?: string;
  size: number;
  hash_sha256?: string;
  file_path?: string;
  workspace_path?: string;
  display_path?: string;
  sha256?: string;
}

/** Context for auto-creating a project before the first upload or send (transition page). */
export type EnsureProjectContext = {
  userText: string;
  fileNames: string[];
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export interface AnalysisInputComposerProps {
  onSubmit: (input: string, attachments: UploadedAttachment[], modelId?: string) => void;
  isAnalyzing: boolean;
  /** True while parent is preparing the request (e.g. creating a project); disables input without showing Stop. */
  isSubmitting?: boolean;
  onAbort?: () => void;
  uploadSessionId?: string | null;
  /**
   * When set and `uploadSessionId` is empty, called before upload or send so the parent
   * can create a project (e.g. auto title from text/files) and return the new project id.
   */
  ensureProjectId?: (ctx: EnsureProjectContext) => Promise<string | null>;
  /** Tailwind classes for textarea vertical sizing */
  textareaMinHeightClass?: string;
  textareaMaxHeightClass?: string;
  placeholder?: string;
  /** Extra class on outer glow wrapper */
  wrapperClassName?: string;
  /** When false, parent handles follow-up (e.g. dialog); input is not cleared after onSubmit. Default true. */
  clearAfterSubmit?: boolean;
  /** Realtime context-usage aggregate from `useStreamingAnalysis*`. Shows a badge beside the Model selector. */
  contextUsage?: ContextUsageState;
  /**
   * Marketing homepage visitor: disables attachments/drag-drop; submit skips `ensureProjectId` gate.
   * Parent should navigate to `/auth` inside `onSubmit`.
   */
  marketingGuest?: boolean;
}

export function AnalysisInputComposer({
  onSubmit,
  isAnalyzing,
  isSubmitting = false,
  onAbort,
  uploadSessionId = null,
  ensureProjectId,
  textareaMinHeightClass = 'min-h-[100px]',
  textareaMaxHeightClass = 'max-h-[200px]',
  placeholder: placeholderProp,
  wrapperClassName = '',
  clearAfterSubmit = true,
  contextUsage,
  marketingGuest = false,
}: AnalysisInputComposerProps) {
  const [input, setInput] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedAttachment[]>([]);
  const [selectedModelId, setSelectedModelId] = useState('');
  const { getLimit } = useModelLimits();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { language, t } = useLanguage();
  const placeholder = placeholderProp ?? t.command.placeholder;

  const {
    isSupported: voiceSupported,
    isListening,
    transcript,
    startListening,
    stopListening,
    resetTranscript,
  } = useVoiceInput(language);

  useEffect(() => {
    if (transcript) {
      setInput((prev) => prev + (prev ? ' ' : '') + transcript);
      resetTranscript();
    }
  }, [transcript, resetTranscript]);

  const handleFileUpload = async (files: FileList) => {
    if (marketingGuest) return;

    const list = Array.from(files);
    if (list.length === 0) return;

    if (uploadedFiles.length + list.length > maxUploadFilesPerBatch) {
      toast.error(`最多上传 ${maxUploadFilesPerBatch} 个文件`);
      return;
    }

    for (const file of list) {
      if (file.size > maxUploadBytesPerFile) {
        toast.error(
          `${file.name} 超过单文件限制（${Math.round(maxUploadBytesPerFile / (1024 * 1024))}MB）`,
        );
        return;
      }
    }

    let sid = (uploadSessionId && uploadSessionId.trim()) || '';
    let ensuredProject = false;
    if (!sid && ensureProjectId) {
      const fileNames = list.map((f) => f.name);
      const id = await ensureProjectId({ userText: input.trim(), fileNames });
      if (!id) return;
      sid = id;
      ensuredProject = true;
    }
    if (!sid) {
      sid =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? crypto.randomUUID()
          : `browser-${Date.now()}`;
    }

    const formData = new FormData();
    formData.append('session_id', sid);
    // When authenticated, also bind uploads to the active project so the agent's
    // owner-scoped workspace (u_<uid>/p_<pid>/) can resolve them on read_file.
    const scopePid = (uploadSessionId && uploadSessionId.trim()) || (ensuredProject ? sid : '');
    if (scopePid) {
      formData.append('project_id', scopePid);
    }
    for (const file of list) {
      formData.append('files', file);
    }

    try {
      const headers: Record<string, string> = { ...getClientTimezoneHeaders() };
      const token = getAuthToken();
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(analysisEndpoints.uploads, {
        method: 'POST',
        body: formData,
        headers,
      });

      if (!res.ok) {
        const errBody = (await res.json().catch(() => ({}))) as { detail?: string | unknown };
        const d = errBody.detail;
        const msg =
          typeof d === 'string' ? d : Array.isArray(d) ? JSON.stringify(d) : res.statusText;
        toast.error(msg || 'Upload failed');
        return;
      }

      const data = (await res.json()) as {
        files: Array<{
          filename: string;
          content_type: string;
          size_bytes: number;
          virtual_path: string;
          workspace_path?: string;
          display_path?: string;
          sha256: string;
        }>;
      };

      for (const f of data.files) {
        const att: UploadedAttachment = {
          filename: f.filename,
          content_type: f.content_type,
          size: f.size_bytes,
          file_path: f.virtual_path,
          workspace_path: f.workspace_path,
          display_path: f.display_path,
          hash_sha256: f.sha256,
          sha256: f.sha256,
        };
        setUploadedFiles((prev) => {
          if (prev.some((p) => p.file_path === att.file_path)) return prev;
          return [...prev, att];
        });
      }
      toast.success(
        data.files.length > 1
          ? `${t.command.fileAdded}: ${data.files.length} files`
          : `${t.command.fileAdded}: ${data.files[0]?.filename ?? ''}`,
      );
    } catch {
      toast.error(t.command.readFailed);
    }
  };

  const handleFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      void handleFileUpload(e.target.files);
      e.target.value = '';
    }
  };

  const triggerFileInput = () => {
    if (isAnalyzing || isSubmitting) return;
    fileInputRef.current?.click();
  };

  const removeUploadedFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = useCallback(async () => {
    const hasPayload = Boolean(input.trim() || uploadedFiles.length > 0);
    console.log('[INPUT-COMPOSER] submit click', {
      hasPayload,
      isAnalyzing,
      isSubmitting,
      uploadedFiles: uploadedFiles.length,
      inputLength: input.trim().length,
    });
    if (hasPayload && !isAnalyzing && !isSubmitting) {
      if (
        !marketingGuest &&
        ensureProjectId &&
        !(uploadSessionId && uploadSessionId.trim())
      ) {
        const id = await ensureProjectId({
          userText: input.trim(),
          fileNames: uploadedFiles.map((a) => a.filename),
        });
        if (!id) return;
      }
      onSubmit(input.trim(), uploadedFiles, selectedModelId || undefined);
      if (clearAfterSubmit) {
        setInput('');
        setUploadedFiles([]);
      }
    } else {
      const reason = !hasPayload
        ? 'empty-payload'
        : isAnalyzing
          ? 'already-analyzing'
          : isSubmitting
            ? 'is-submitting'
            : 'unknown';
      if (reason === 'empty-payload') {
        toast.warning(t.command.placeholder);
      } else if (reason === 'already-analyzing') {
        toast.info(t.command.analyzing);
      } else if (reason === 'is-submitting') {
        toast.info(t.common.loading);
      }
      console.warn('[INPUT-COMPOSER] submit ignored', {
        reason,
      });
    }
  }, [
    input,
    uploadedFiles,
    isAnalyzing,
    isSubmitting,
    onSubmit,
    selectedModelId,
    clearAfterSubmit,
    t.command.placeholder,
    t.command.analyzing,
    t.common.loading,
    ensureProjectId,
    uploadSessionId,
    marketingGuest,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isSubmitting) void handleSubmit();
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!marketingGuest) setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (marketingGuest) return;
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      void handleFileUpload(files);
    }
  };

  return (
    <div
      className={`relative rounded-xl transition-all duration-200 input-glow border border-border bg-input ${wrapperClassName} ${
        isDragging ? 'border-2 border-dashed border-primary bg-primary/5' : ''
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className={`w-full ${textareaMinHeightClass} ${textareaMaxHeightClass} p-3 sm:p-4 bg-transparent text-foreground text-sm sm:text-base resize-none focus:outline-none placeholder:text-muted-foreground`}
        disabled={isAnalyzing || isSubmitting}
        data-testid="analysis-input-textarea"
      />

      {uploadedFiles.length > 0 && (
        <div className="px-3 pb-2">
          <div className="mb-1 text-xs text-muted-foreground">
            {uploadedFiles.length} {t.command.files}
          </div>
          <div className="flex flex-wrap gap-2 max-h-24 overflow-y-auto pr-1">
            {uploadedFiles.map((file, index) => (
              <div
                key={`${file.filename}-${index}`}
                className="inline-flex max-w-full items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
                title={file.filename}
              >
                <span className="truncate max-w-[180px]">{file.filename}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {formatFileSize(file.size)}
                </span>
                <button
                  type="button"
                  onClick={() => removeUploadedFile(index)}
                  className="ml-1 text-muted-foreground hover:text-foreground"
                  aria-label={`Remove ${file.filename}`}
                  disabled={isAnalyzing || isSubmitting}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {isDragging && (
        <div className="absolute inset-0 flex items-center justify-center bg-primary/5 rounded-xl">
          <div className="flex items-center gap-2 text-primary">
            <Paperclip className="w-5 h-5" />
            <span className="font-medium text-sm">{t.command.dropToUpload}</span>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-4 px-4 py-2.5 border-t border-border/50">
        <div className="flex items-center gap-1 min-w-0">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="*/*"
            onChange={handleFileInputChange}
            className="hidden"
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
            onClick={triggerFileInput}
            disabled={marketingGuest || isAnalyzing || isSubmitting}
            title={marketingGuest ? t.marketing.guestAttachTooltip : undefined}
          >
            <Paperclip className="w-3.5 h-3.5" />
          </Button>
          <VoiceMicButton
            isSupported={voiceSupported}
            isListening={isListening}
            disabled={isAnalyzing || isSubmitting}
            onToggle={() => (isListening ? stopListening() : startListening())}
          />
          <div className="h-4 w-px shrink-0 bg-border/60" aria-hidden />
          <ModelSelector
            value={selectedModelId}
            onChange={setSelectedModelId}
            disabled={isAnalyzing || isSubmitting}
            placeholder="Model"
            className="h-7 shrink-0 text-xs px-1.5 max-w-[120px] sm:max-w-[160px]"
          />
          {/* Only render the badge + its separator once we actually have
              usage data — the badge itself returns null when idle, so keeping
              the separator conditional on `latest` avoids a dangling divider. */}
          {getMainUsageSnapshot(contextUsage) ? (
            <>
              <div className="h-4 w-px shrink-0 bg-border/60" aria-hidden />
              <ContextUsageBadge
                state={contextUsage}
                contextWindow={
                  getLimit(selectedModelId)?.contextWindow ?? 200_000
                }
                modelDisplayName={getLimit(selectedModelId)?.name}
              />
            </>
          ) : null}
        </div>
        <div className="flex items-center shrink-0">
          {isAnalyzing ? (
            <Button
              onClick={onAbort}
              disabled={!onAbort}
              variant="destructive"
              size="icon"
              className="h-8 w-8 rounded-lg"
              title={t.command.stop}
            >
              <Square className="w-4 h-4" />
            </Button>
          ) : isSubmitting ? (
            <Button
              type="button"
              variant="secondary"
              size="icon"
              className="h-8 w-8 rounded-lg"
              disabled
              title={t.common.loading}
            >
              <Loader2 className="w-4 h-4 animate-spin" />
            </Button>
          ) : (
            <Button
              onClick={() => void handleSubmit()}
              disabled={!input.trim() && uploadedFiles.length === 0}
              size="icon"
              className="h-8 w-8 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-all"
              title={t.command.send}
              data-testid="analysis-input-send"
            >
              <Send className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
