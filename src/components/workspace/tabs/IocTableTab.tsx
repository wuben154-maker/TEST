import { Shield } from 'lucide-react';

interface IocTableTabProps {
  raw: string;
}

export function IocTableTab({ raw }: IocTableTabProps) {
  if (!raw) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
        <Shield className="w-8 h-8 text-muted-foreground/40" />
        <p className="text-sm">暂无 IOC 数据</p>
      </div>
    );
  }

  return (
    <div className="py-4">
      <pre className="text-xs font-mono bg-muted/30 rounded-lg p-4 overflow-auto whitespace-pre-wrap break-all">
        {raw}
      </pre>
    </div>
  );
}
