import { useState, useEffect, useCallback, useMemo } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import { 
  Download, 
  FileText, 
  Sparkles, 
  Loader2, 
  X,
  RefreshCw,
  Maximize2,
  ChevronDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { WorkspaceBlock } from '@/types/analysis';
import { AnalysisResult } from '@/types/project';
import { useLanguage } from '@/contexts/LanguageContext';
import { logger } from '@/lib/logger';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { EditorToolbar } from './EditorToolbar';
import { exportToDocx } from '@/lib/docx-export';
import { exportHtmlFragmentToPdf } from '@/lib/reportPdf';
import { parseMarkdownToHtml } from '@/lib/documentWorkspaceMarkdown';
import { toast } from 'sonner';

interface DocumentWorkspaceProps {
  blocks: WorkspaceBlock[];
  analysisResults?: AnalysisResult[];
  activeResultId?: string;
  onSelectResult?: (resultId: string) => void;
  onRemoveResult?: (resultId: string) => void;
  onRenameResult?: (resultId: string, newTitle: string) => void;
  hideHeader?: boolean;
}

// Convert blocks to HTML content for the editor
type DocumentLabels = {
  severity: string;
  decodingResult: string;
  ciphertext: string;
  plaintext: string;
  threatIntel: string;
  indicator: string;
  threatScore: string;
  location: string;
};

function blocksToHtml(blocks: WorkspaceBlock[], labels: DocumentLabels): string {
  if (blocks.length === 0) return '';
  
  let html = '';
  
  blocks.forEach(block => {
    switch (block.type) {
      case 'text':
        if (block.variant === 'heading') {
          html += `<h1>${block.content}</h1>`;
        } else if (block.variant === 'bullet') {
          html += `<ul><li>${block.content}</li></ul>`;
        } else {
          html += `<p>${block.content}</p>`;
        }
        break;
      case 'summary':
        html += `<h2>${block.title}</h2>`;
        html += `<p><strong>${labels.severity}:</strong> ${block.severity}</p>`;
        html += `<p>${block.description}</p>`;
        break;
      case 'log':
        html += `<pre><code>${block.content}</code></pre>`;
        break;
      case 'decoder':
        html += `<h3>${labels.decodingResult} (${block.algorithm})</h3>`;
        html += `<p><strong>${labels.ciphertext}:</strong></p>`;
        html += `<pre><code>${block.encoded}</code></pre>`;
        html += `<p><strong>${labels.plaintext}:</strong></p>`;
        html += `<pre><code>${block.decoded}</code></pre>`;
        break;
      case 'intel':
        html += `<h3>${labels.threatIntel}</h3>`;
        html += `<p><strong>${labels.indicator}:</strong> ${block.indicator}</p>`;
        html += `<p><strong>${labels.threatScore}:</strong> ${block.threatScore}</p>`;
        if (block.location) html += `<p><strong>${labels.location}:</strong> ${block.location}</p>`;
        if (block.asn) html += `<p><strong>ASN:</strong> ${block.asn}</p>`;
        break;
      case 'analysis':
        if (block.title) html += `<h2>${block.title}</h2>`;
        // Parse markdown content properly
        html += parseMarkdownToHtml(block.content);
        break;
    }
  });
  
  return html;
}

export function DocumentWorkspace({ 
  blocks, 
  analysisResults = [], 
  activeResultId,
  onSelectResult,
  onRemoveResult,
  onRenameResult,
  hideHeader = false,
}: DocumentWorkspaceProps) {
  const { t } = useLanguage();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isExportingDocx, setIsExportingDocx] = useState(false);
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [editingTabId, setEditingTabId] = useState<string | null>(null);

  const docLabels = useMemo<DocumentLabels>(() => ({
    severity: t.document.severity,
    decodingResult: t.document.decodingResult,
    ciphertext: t.workspace.ciphertext,
    plaintext: t.workspace.plaintext,
    threatIntel: t.document.threatIntel,
    indicator: t.workspace.indicator,
    threatScore: t.document.threatScore,
    location: t.workspace.location,
  }), [t]);

  // Convert blocks to initial HTML
  const initialContent = useMemo(
    () => blocksToHtml(blocks, docLabels),
    [blocks, docLabels]
  );

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3],
        },
      }),
      Placeholder.configure({
        placeholder: t.document.startEditing,
      }),
      Underline,
      TextAlign.configure({
        types: ['heading', 'paragraph'],
      }),
    ],
    content: initialContent,
    editorProps: {
      attributes: {
        class: 'focus:outline-none min-h-[400px]',
      },
    },
  });

  // Update editor content when blocks change
  useEffect(() => {
    if (editor && blocks.length > 0) {
      const newContent = blocksToHtml(blocks, docLabels);
      if (newContent !== editor.getHTML()) {
        editor.commands.setContent(newContent);
      }
    }
  }, [blocks, editor, docLabels]);

  const handleExportDocx = useCallback(async () => {
    if (!editor) return;
    
    setIsExportingDocx(true);
    try {
      await exportToDocx(editor.getHTML(), `secmanus-report-${Date.now()}`);
      toast.success(t.document.wordExportSuccess);
    } catch (error) {
      logger.error('document_word_export_failed', { error: String(error) });
      toast.error(t.document.exportFailedRetry);
    } finally {
      setIsExportingDocx(false);
    }
  }, [editor, t.document.exportFailedRetry, t.document.wordExportSuccess]);

  const handleExportMarkdown = useCallback(() => {
    if (!editor) return;
    
    let markdown = `# SecManus ${t.workspace.title}\n\n`;
    markdown += `${t.workspace.generatedAt}: ${new Date().toLocaleString()}\n\n---\n\n`;
    
    // Convert HTML to markdown (simplified)
    const html = editor.getHTML();
    const text = html
      .replace(/<h1[^>]*>(.*?)<\/h1>/g, '# $1\n\n')
      .replace(/<h2[^>]*>(.*?)<\/h2>/g, '## $1\n\n')
      .replace(/<h3[^>]*>(.*?)<\/h3>/g, '### $1\n\n')
      .replace(/<p[^>]*>(.*?)<\/p>/g, '$1\n\n')
      .replace(/<strong>(.*?)<\/strong>/g, '**$1**')
      .replace(/<em>(.*?)<\/em>/g, '*$1*')
      .replace(/<pre><code>(.*?)<\/code><\/pre>/gs, '```\n$1\n```\n\n')
      .replace(/<[^>]+>/g, '');
    
    markdown += text;
    markdown += `\n---\n*${t.workspace.generatedBy}*`;

    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `secmanus-report-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [editor, t]);

  const handleExportPdf = useCallback(async () => {
    if (!editor) return;

    setIsExportingPdf(true);
    try {
      await exportHtmlFragmentToPdf(editor.getHTML(), `secmanus-report-${Date.now()}`);
      toast.success(t.document.pdfExportSuccess);
    } catch (error) {
      logger.error('document_pdf_export_failed', { error: String(error) });
      toast.error(t.document.pdfExportFailedRetry);
    } finally {
      setIsExportingPdf(false);
    }
  }, [editor, t.document.pdfExportFailedRetry, t.document.pdfExportSuccess]);

  const handleRefresh = useCallback(() => {
    if (editor && blocks.length > 0) {
      editor.commands.setContent(blocksToHtml(blocks, docLabels));
      toast.success(t.document.documentRefreshed);
    }
  }, [editor, blocks, docLabels, t.document.documentRefreshed]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev);
  }, []);

  const hasResults = analysisResults.length > 0;
  const currentActiveId = activeResultId || (hasResults ? analysisResults[analysisResults.length - 1].id : undefined);
  const activeResult = analysisResults.find(r => r.id === currentActiveId);

  const containerClass = isFullscreen 
    ? "fixed inset-0 z-50 bg-background" 
    : "flex flex-col h-full w-full bg-background overflow-hidden";

  return (
    <div className={containerClass}>
      {/* Tabs for results - NOW AT TOP */}
      {hasResults && (
        <div className="flex-shrink-0 px-4 border-b border-border bg-muted/20">
          <ScrollArea className="w-full whitespace-nowrap">
            <div className="flex gap-1 py-2">
              {analysisResults.map((result, index) => (
                <div
                  key={result.id}
                  className={`
                    inline-flex items-center gap-1 pl-3 pr-1 py-1.5 rounded-md text-sm font-medium transition-colors group
                    ${result.id === currentActiveId 
                      ? 'bg-primary text-primary-foreground' 
                      : 'bg-muted hover:bg-muted/80 text-foreground/70 hover:text-foreground'
                    }
                  `}
                >
                  {editingTabId === result.id ? (
                    <input
                      autoFocus
                      className="max-w-[140px] bg-transparent border-b border-current outline-none text-sm"
                      defaultValue={result.title || `${t.projects.analysisTitlePrefix} ${index + 1}`}
                      onBlur={(e) => {
                        const val = e.target.value.trim();
                        if (val && val !== result.title) onRenameResult?.(result.id, val);
                        setEditingTabId(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') e.currentTarget.blur();
                        if (e.key === 'Escape') setEditingTabId(null);
                      }}
                    />
                  ) : (
                    <button
                      onClick={() => onSelectResult?.(result.id)}
                      onDoubleClick={() => setEditingTabId(result.id)}
                      className="max-w-[140px] truncate"
                      title={result.userInput}
                    >
                      {result.title || `${t.projects.analysisTitlePrefix} ${index + 1}`}
                    </button>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemoveResult?.(result.id);
                    }}
                    className={`
                      p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity
                      ${result.id === currentActiveId 
                        ? 'hover:bg-primary-foreground/20' 
                        : 'hover:bg-foreground/10'
                      }
                    `}
                    title={t.document.closeTab}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </div>
      )}

      {/* Document Header - AFTER TABS */}
      {!hideHeader && (
        <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b border-border bg-background">
          {/* Left side - Document title */}
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" className="h-8 w-8 text-foreground">
              <FileText className="h-4 w-4" />
            </Button>
            <span className="font-medium text-foreground truncate max-w-[200px] sm:max-w-[300px]">
              {activeResult?.title || t.workspace.title}
              {blocks.length > 0 && (
                <span className="ml-2 text-xs text-muted-foreground">
                  {t.document.editableVersion}
                </span>
              )}
            </span>
          </div>

          {/* Right side - Actions */}
          <div className="flex items-center gap-1">
            {/* Version dropdown - only show if multiple results */}
            {analysisResults.length > 1 && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="h-8 gap-1">
                    {t.document.latestVersion}
                    <ChevronDown className="h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {analysisResults.map((result, index) => (
                    <DropdownMenuItem 
                      key={result.id}
                      onClick={() => onSelectResult?.(result.id)}
                    >
                      {result.title || `${t.document.versionPrefix} ${index + 1}`}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            {/* Refresh */}
            <Button 
              variant="ghost" 
              size="icon"
              className="h-8 w-8 text-foreground"
              onClick={handleRefresh}
              disabled={blocks.length === 0}
              title={t.document.refresh}
            >
              <RefreshCw className="h-4 w-4" />
            </Button>

            {/* Export dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button 
                  variant="ghost" 
                  size="icon"
                  className="h-8 w-8 text-foreground"
                  disabled={blocks.length === 0}
                  title={t.document.download}
                >
                  <Download className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={handleExportPdf} disabled={isExportingPdf}>
                  {isExportingPdf ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <FileText className="w-4 h-4 mr-2" />
                  )}
                  {t.document.pdfDoc}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleExportDocx} disabled={isExportingDocx}>
                  {isExportingDocx ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <FileText className="w-4 h-4 mr-2" />
                  )}
                  {t.document.wordDoc}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleExportMarkdown}>
                  <FileText className="w-4 h-4 mr-2" />
                  Markdown (.md)
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Fullscreen */}
            <Button 
              variant="ghost" 
              size="icon"
              className="h-8 w-8 text-foreground"
              onClick={toggleFullscreen}
              title={t.document.fullscreen}
            >
              <Maximize2 className="h-4 w-4" />
            </Button>

            {/* Close fullscreen */}
            {isFullscreen && (
              <Button 
                variant="ghost" 
                size="icon"
                className="h-8 w-8 text-foreground"
                onClick={toggleFullscreen}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Editor Toolbar */}
      {blocks.length > 0 && <EditorToolbar editor={editor} />}

      {/* Document Content */}
      <div className="flex-1 overflow-auto bg-card/50">
        <div id="document-content" className="min-h-full">
          {blocks.length > 0 ? (
            <div className="max-w-4xl mx-auto bg-card min-h-full document-editor-content">
              <EditorContent editor={editor} />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-muted-foreground">
              <div className="w-20 h-20 rounded-2xl bg-muted/30 flex items-center justify-center mb-6">
                <Sparkles className="w-10 h-10 text-muted-foreground/40" />
              </div>
              <h3 className="text-lg font-medium text-foreground mb-2">{t.workspace.smartCanvas}</h3>
              <p className="text-sm text-center max-w-sm text-muted-foreground">
                {t.workspace.empty}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
