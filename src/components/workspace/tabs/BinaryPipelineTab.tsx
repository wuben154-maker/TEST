import { Cpu } from 'lucide-react';

export function BinaryPipelineTab() {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
      <Cpu className="w-8 h-8 text-muted-foreground/40" />
      <p className="text-sm font-medium">二进制分析流水线</p>
      <p className="text-xs text-muted-foreground/60">即将推出</p>
    </div>
  );
}
