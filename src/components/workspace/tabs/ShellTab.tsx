import { useEffect, useRef, useState } from 'react';
import { Terminal } from 'lucide-react';
import type { ShellLine } from '@/types/analysis';
import type { AnalysisResultStatus } from '@/types/project';

/** Strip basic ANSI escape codes for display (colors rendered via className). */
function stripAnsi(text: string): string {
  // eslint-disable-next-line no-control-regex
  return text.replace(/\x1b\[[0-9;]*[mGKHF]/g, '');
}

function formatTime(ts: number, startTs: number): string {
  const diff = (ts - startTs) / 1000;
  const m = Math.floor(diff / 60);
  const s = (diff % 60).toFixed(2).padStart(5, '0');
  return `${String(m).padStart(2, '0')}:${s}`;
}

interface ShellLineRowProps {
  line: ShellLine;
  startTs: number;
}

function ShellLineRow({ line, startTs }: ShellLineRowProps) {
  const isStderr = line.stream === 'stderr';
  const display = stripAnsi(line.text);
  const timeStr = formatTime(line.ts, startTs);

  return (
    <div className={`flex gap-2 leading-relaxed font-mono text-xs ${isStderr ? 'text-yellow-400/90' : 'text-green-300/90'}`}>
      <span className="text-gray-500 select-none flex-shrink-0">[{timeStr}]</span>
      <span className="break-all">{display}</span>
    </div>
  );
}

interface ShellTabProps {
  instanceKey: string;
  status: AnalysisResultStatus;
  lines: ShellLine[];
}

export function ShellTab({ instanceKey, status, lines }: ShellTabProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const startTs = lines[0]?.ts ?? Date.now();

  // Auto-scroll to bottom when new lines arrive and user hasn't scrolled up.
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines, autoScroll]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 40;
    setAutoScroll(atBottom);
  };

  const displayLines = lines.length > 5000 ? lines.slice(lines.length - 5000) : lines;
  const truncated = lines.length > 5000;

  return (
    <div className="flex flex-col h-full min-h-0 rounded-lg overflow-hidden border border-border/50">
      {/* Shell header */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-green-400" />
          <span className="font-mono text-xs text-gray-300">
            沙箱: <span className="text-green-400">{instanceKey}</span>
          </span>
        </div>
        {status === 'running' ? (
          <span className="inline-flex items-center gap-1 text-[10px] text-blue-400">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
            </span>
            运行中
          </span>
        ) : (
          <span className="text-[10px] text-gray-500">已完成</span>
        )}
      </div>

      {/* Terminal body */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto bg-gray-950 p-4 font-mono text-xs min-h-0"
        style={{ maxHeight: '400px' }}
      >
        {truncated && (
          <div className="text-yellow-500/70 text-xs mb-2 border-b border-yellow-500/20 pb-2">
            ⚠ 输出过长，仅显示最后 5000 行
          </div>
        )}
        {displayLines.length === 0 ? (
          <span className="text-gray-600 animate-pulse">等待输出…</span>
        ) : (
          displayLines.map((line, i) => (
            <ShellLineRow key={i} line={line} startTs={startTs} />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Auto-scroll indicator */}
      {!autoScroll && (
        <button
          onClick={() => {
            setAutoScroll(true);
            bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
          }}
          className="absolute bottom-4 right-4 bg-gray-800 hover:bg-gray-700 text-gray-300 text-[10px] px-2 py-1 rounded border border-gray-600 transition-colors"
        >
          ↓ 跳到底部
        </button>
      )}
    </div>
  );
}
