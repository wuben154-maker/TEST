import { useState, useMemo } from 'react';
import { ChevronDown, ChevronUp, Lightbulb, Paperclip } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/lib/utils';
import { parseUserMessageAttachments } from '@/lib/formatUserMessageDisplay';
import { formatThoughtDuration } from '@/lib/thinkingDurationLabel';

interface ChatMessageProps {
  type: 'user' | 'assistant';
  content: string;
  timestamp?: Date;
  thinkingDuration?: number; // in seconds
  isThinking?: boolean;
}

// Filter out raw JSON responses and internal system messages from LLM
function cleanRawLLMResponse(text: string): string {
  if (!text) return text;
  
  let cleaned = text;
  
  // Pattern 1: Remove template phrases with placeholders followed by JSON
  // e.g., "I will conduct deep research on [topic]. { ... }"
  const templateWithJsonPattern = /我将帮你展开关于\[.*?\]的深度研究分析[。.]\s*\{[\s\S]*\}/gi;
  cleaned = cleaned.replace(templateWithJsonPattern, '').trim();
  
  // Pattern 2: Remove standalone JSON objects that look like internal system output
  // Match JSON objects containing task_category, input_type, etc.
  const intentJsonPattern = /\{\s*["']?task_category["']?\s*:\s*["'][^"']*["'][\s\S]*?\}/gi;
  cleaned = cleaned.replace(intentJsonPattern, '').trim();
  
  // Pattern 3: Remove template phrases with placeholders (without JSON)
  const templatePatterns = [
    /我将帮你展开关于\[.*?\]的深度研究分析[。.]?/gi,
    /我将为你分析\[.*?\][。.]?/gi,
    /让我来分析\[.*?\][。.]?/gi,
  ];
  for (const pattern of templatePatterns) {
    cleaned = cleaned.replace(pattern, '').trim();
  }
  
  // Pattern 4: Raw LLM JSON responses with extras/signature
  const rawJsonPattern = /\[?\{['"]type['"]:\s*['"]text['"],\s*['"]text['"]:\s*['"][\s\S]*?['"]extras['"]:\s*\{['"]signature['"]:[^}]+\}\}\]?/g;
  cleaned = cleaned.replace(rawJsonPattern, '').trim();
  
  // Pattern 5: Signature patterns
  const signaturePattern = /,\s*['"]extras['"]:\s*\{['"]signature['"]:\s*['"][^'"]+['"]\}\}/g;
  cleaned = cleaned.replace(signaturePattern, '').trim();
  
  // Pattern 6: Internal status messages in Chinese/English
  const statusPatterns = [
    /Deep\s*Agent\s*就绪[^。\n]*[。]?/gi,
    /DeepAgent\s*就绪[^。\n]*[。]?/gi,
    /初始化.*?分析引擎[^。\n]*[。]?/gi,
    /✅\s*DeepAgent\s*就绪[^。\n]*[。]?/gi,
    /分析引擎就绪[^。\n]*[。]?/gi,
    /DeepAgent\s*ready[^.\n]*[.]?/gi,
    /Initializing.*?analysis\s*engine[^.\n]*[.]?/gi,
  ];
  for (const pattern of statusPatterns) {
    cleaned = cleaned.replace(pattern, '').trim();
  }
  
  // Pattern 7: Topic placeholder pattern  
  cleaned = cleaned.replace(/\[话题\]/g, '').trim();
  
  // Extract actual text from JSON if present
  const jsonMatch = text.match(/\[?\{['"]type['"]:\s*['"]text['"],\s*['"]text['"]:\s*['"]([\s\S]*?)['"]\s*,\s*['"]extras['"]/);
  if (jsonMatch && jsonMatch[1]) {
    const extractedText = jsonMatch[1]
      .replace(/\\n/g, '\n')
      .replace(/\\'/g, "'")
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, '\\');
    
    if (extractedText && extractedText.length > cleaned.length) {
      cleaned = extractedText;
    }
  }
  
  // Extract and handle JSON envelopes — both standalone and prefix patterns
  // e.g. '{"need_clarification":false,...}' or '{"need_clarification":false,...}trailing text'
  const trimmedCleaned = cleaned.trim();
  if (trimmedCleaned.startsWith('{')) {
    const braceEnd = trimmedCleaned.indexOf('}');
    // Find the matching closing brace by trying increasingly longer substrings
    let jsonCandidate: string | null = null;
    let parsed: Record<string, unknown> | null = null;
    if (braceEnd >= 0) {
      let searchFrom = braceEnd;
      while (searchFrom < trimmedCleaned.length) {
        const idx = trimmedCleaned.indexOf('}', searchFrom);
        if (idx < 0) break;
        const candidate = trimmedCleaned.slice(0, idx + 1);
        try {
          const obj = JSON.parse(candidate);
          if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
            jsonCandidate = candidate;
            parsed = obj as Record<string, unknown>;
            break;
          }
        } catch { /* try next brace */ }
        searchFrom = idx + 1;
      }
    }
    if (parsed) {
      if (parsed.task_category !== undefined || 
          parsed.input_type !== undefined || 
          parsed.needs_more_context !== undefined ||
          parsed.context_reasoning !== undefined) {
        const tail = trimmedCleaned.slice(jsonCandidate!.length).trim();
        return tail;
      }
      if ('need_clarification' in parsed) {
        const visible = parsed.need_clarification
          ? String(parsed.question ?? '').trim()
          : String(parsed.verification ?? '').trim();
        return visible;
      }
    }
  }
  
  // Final cleanup: remove multiple consecutive newlines
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n').trim();
  
  return cleaned;
}

export function ChatMessage({ 
  type, 
  content, 
  timestamp, 
  thinkingDuration,
  isThinking,
  conversationColumn,
}: ChatMessageProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const cleanedContent = useMemo(() => cleanRawLLMResponse(content), [content]);

  const userParsed = useMemo(
    () => (type === 'user' ? parseUserMessageAttachments(cleanedContent) : null),
    [type, cleanedContent],
  );

  const isLongContent =
    type === 'user' && userParsed && userParsed.files.length > 0
      ? userParsed.body.length > 500
      : cleanedContent.length > 500;
  const displayContent = isLongContent && !isExpanded
    ? (type === 'user' && userParsed && userParsed.files.length > 0
        ? userParsed.body.slice(0, 500) + '...'
        : cleanedContent.slice(0, 500) + '...')
    : cleanedContent;

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: false 
    });
  };

  if (type === 'user') {
    const hasStructuredAttachments = !!userParsed && userParsed.files.length > 0;
    const bodyForDisplay =
      hasStructuredAttachments && isLongContent && !isExpanded
        ? userParsed!.body.slice(0, 500) + '...'
        : hasStructuredAttachments
          ? userParsed!.body
          : displayContent;

    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[85%]">
          {timestamp && (
            <div className="text-[11px] text-muted-foreground/60 text-right mb-1">
              {formatTime(timestamp)}
            </div>
          )}

          <div className="trace-interactive-surface overflow-hidden rounded-xl rounded-tr-sm border-primary/20 bg-primary/10 p-4 shadow-sm">
            {hasStructuredAttachments ? (
              <>
                {userParsed!.body ? (
                  <p className="text-[15px] text-foreground leading-relaxed whitespace-pre-wrap break-all overflow-wrap-anywhere">
                    {bodyForDisplay}
                  </p>
                ) : null}
                <ul
                  className={cn(
                    'space-y-2',
                    userParsed!.body ? 'mt-3 pt-3 border-t border-border/40' : '',
                  )}
                  aria-label="Attachments"
                >
                  {userParsed!.files.map((name, i) => (
                    <li
                      key={`${name}-${i}`}
                      className="flex items-start gap-2 text-[15px] text-foreground leading-snug"
                    >
                      <Paperclip
                        className="mt-0.5 h-4 w-4 shrink-0 text-primary/85"
                        strokeWidth={2}
                        aria-hidden
                      />
                      <span className="break-all overflow-wrap-anywhere">{name}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="text-[15px] text-foreground leading-relaxed whitespace-pre-wrap break-all overflow-wrap-anywhere">
                {displayContent}
              </p>
            )}

            {isLongContent && (
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="flex items-center gap-1 mt-2 text-xs text-primary hover:text-primary/80 transition-colors"
              >
                {isExpanded ? (
                  <>
                    <ChevronUp className="w-3 h-3" />
                    Show less
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-3 h-3" />
                    Show more
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Assistant message with Markdown rendering
  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[90%]">
        {/* Thinking indicator - Lovable style */}
        {isThinking && !content && (
          <div className="flex items-center gap-2 py-1">
            <Lightbulb className="w-4 h-4 text-muted-foreground/70 animate-pulse" />
            <span className="text-sm text-muted-foreground">Thinking</span>
            <span className="inline-flex gap-0.5">
              <span className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          </div>
        )}
        
        {/* Thought duration */}
        {!isThinking && thinkingDuration !== undefined && thinkingDuration > 0 && (
          <div className="flex items-center gap-2 mb-2">
            <div className="relative w-4 h-4 flex items-center justify-center">
              <div className="absolute inset-0 rounded-full bg-gradient-to-r from-violet-500/20 to-pink-500/20" />
              <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50" />
            </div>
            <span className="text-xs text-muted-foreground font-medium" lang="en">
              {formatThoughtDuration(thinkingDuration)}
            </span>
          </div>
        )}
        
        {/* Assistant content with Markdown */}
        {content && (
          <div className="space-y-1 overflow-hidden">
            <div className={cn(
              "prose prose-sm dark:prose-invert max-w-none",
              "prose-headings:text-foreground prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2",
              "prose-h1:text-lg prose-h2:text-base prose-h3:text-sm",
              "prose-p:text-foreground/90 prose-p:leading-relaxed prose-p:my-2",
              "prose-strong:text-foreground prose-strong:font-semibold",
              "prose-ul:my-2 prose-ol:my-2 prose-li:text-foreground/90 prose-li:my-0.5",
              "prose-code:text-primary prose-code:bg-primary/10 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none",
              "prose-pre:bg-muted prose-pre:p-3 prose-pre:rounded-lg",
              "prose-a:text-primary prose-a:no-underline hover:prose-a:underline",
              isThinking && "inline"
            )}>
              <ReactMarkdown>
                {displayContent}
              </ReactMarkdown>
              {isThinking && (
                <span className="inline-block w-[2px] h-4 bg-foreground/60 ml-1 animate-pulse align-text-bottom rounded-full" />
              )}
            </div>
            
            {isLongContent && (
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="flex items-center gap-1 mt-2 text-xs text-primary hover:text-primary/80 transition-colors"
              >
                {isExpanded ? (
                  <>
                    <ChevronUp className="w-3 h-3" />
                    Show less
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-3 h-3" />
                    Show more
                  </>
                )}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
