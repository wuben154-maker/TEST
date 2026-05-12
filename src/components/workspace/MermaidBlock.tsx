import { useEffect, useId, useRef, useState } from 'react';

function resolveMermaidTheme(): 'dark' | 'default' {
  if (typeof document === 'undefined') return 'dark';
  const root = document.documentElement;
  if (root.classList.contains('dark')) return 'dark';
  if (root.classList.contains('light')) return 'default';
  return 'dark';
}

export interface MermaidBlockProps {
  code: string;
}

/**
 * Client-side Mermaid render for fenced ```mermaid blocks inside workspace markdown.
 */
export function MermaidBlock({ code }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const reactId = useId().replace(/[^a-zA-Z0-9_-]/g, '_');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const el = containerRef.current;
    const definition = code.trim();
    if (!el || !definition) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setError(null);
    setLoading(true);

    const run = async () => {
      try {
        const m = await import('mermaid');
        const theme = resolveMermaidTheme();
        m.default.initialize({
          startOnLoad: false,
          theme,
          securityLevel: 'strict',
          fontFamily: 'inherit',
        });
        const uid = `sm-m-${reactId}-${Math.random().toString(36).slice(2, 10)}`;
        const { svg } = await m.default.render(uid, definition);
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = svg;
        setError(null);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();

    return () => {
      cancelled = true;
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [code, reactId]);

  if (!code.trim()) return null;

  if (error) {
    return (
      <div
        className="not-prose my-4 rounded-lg border border-destructive/40 bg-muted/50 p-4 text-sm"
        data-testid="mermaid-error"
      >
        <p className="mb-2 font-medium text-destructive">Mermaid 渲染失败</p>
        <pre className="overflow-x-auto whitespace-pre-wrap text-muted-foreground">{code}</pre>
        <p className="mt-2 text-xs text-muted-foreground">{error}</p>
      </div>
    );
  }

  return (
    <div
      className="not-prose my-4 overflow-x-auto rounded-lg border border-border bg-card/40 p-4"
      data-testid="mermaid-block"
    >
      {loading ? (
        <div className="text-xs text-muted-foreground" data-testid="mermaid-loading">
          正在渲染图表…
        </div>
      ) : null}
      <div ref={containerRef} className="[&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full" />
    </div>
  );
}
