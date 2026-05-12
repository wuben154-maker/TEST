import { Children, isValidElement, type ReactElement, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';
import { MermaidBlock } from './MermaidBlock';
import { normalizeMarkdownForWorkspace } from '@/lib/normalizeMarkdownTables';

interface MarkdownRendererProps {
  markdown: string;
  className?: string;
}

function flattenCodeChildren(node: ReactNode): string {
  if (node == null) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(flattenCodeChildren).join('');
  if (isValidElement(node)) {
    const el = node as ReactElement<{ children?: ReactNode }>;
    return flattenCodeChildren(el.props.children);
  }
  return '';
}

export function MarkdownRenderer({ markdown, className }: MarkdownRendererProps) {
  const safeMd = normalizeMarkdownForWorkspace(markdown);
  return (
    <div
      className={cn(
        'prose prose-sm dark:prose-invert max-w-none',
        'prose-headings:text-foreground prose-headings:font-semibold prose-headings:tracking-tight',
        'prose-h1:text-2xl prose-h1:mb-4 prose-h1:mt-6',
        'prose-h2:text-xl prose-h2:mb-3 prose-h2:mt-7',
        'prose-h3:text-base prose-h3:mb-2 prose-h3:mt-5',
        'prose-p:text-foreground/85 prose-p:leading-7 prose-p:my-3',
        'prose-strong:text-foreground prose-strong:font-semibold',
        'prose-ul:my-3 prose-ol:my-3 prose-li:text-foreground/85 prose-li:my-1',
        'prose-blockquote:border-l-primary/50 prose-blockquote:text-muted-foreground prose-blockquote:not-italic',
        // Inline `code` only: fenced blocks are `pre > code` — neutral chip (not primary) so tables stay calm.
        'prose-code:text-foreground/90 prose-code:bg-muted/55 prose-code:border prose-code:border-border/60 prose-code:px-1.5 prose-code:py-px prose-code:rounded prose-code:font-medium prose-code:shadow-none prose-code:before:content-none prose-code:after:content-none',
        'prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-pre:rounded-lg prose-pre:p-4 prose-pre:overflow-x-auto prose-pre:text-foreground/90',
        '[&_pre>code]:bg-transparent [&_pre>code]:p-0 [&_pre>code]:text-inherit [&_pre>code]:rounded-none [&_pre>code]:font-normal [&_pre>code]:before:!content-none [&_pre>code]:after:!content-none',
        'prose-table:w-full prose-table:border-collapse prose-table:text-sm prose-table:my-4',
        'prose-th:border prose-th:border-border prose-th:bg-muted/60 prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:text-foreground',
        'prose-td:border prose-td:border-border prose-td:px-3 prose-td:py-2 prose-td:text-foreground/90',
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="break-words text-foreground/88 underline decoration-muted-foreground/45 underline-offset-[3px] transition-colors hover:text-foreground hover:decoration-muted-foreground/75 visited:text-foreground/82 visited:decoration-border/55"
            >
              {children}
            </a>
          ),
          pre: ({ children, ...props }) => {
            const arr = Children.toArray(children);
            const only = arr.length === 1 ? arr[0] : null;
            if (
              isValidElement(only) &&
              typeof only.props.className === 'string' &&
              only.props.className.split(/\s+/).some((c: string) => c === 'language-mermaid')
            ) {
              const text = flattenCodeChildren(only.props.children);
              return <MermaidBlock code={text.replace(/\n$/, '')} />;
            }
            return (
              <pre {...props} className={cn(props.className)}>
                {children}
              </pre>
            );
          },
        }}
      >
        {safeMd}
      </ReactMarkdown>
    </div>
  );
}
