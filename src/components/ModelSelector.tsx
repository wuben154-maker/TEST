import { useEffect, useState, useMemo } from "react";
import { Loader2, ChevronDown } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { analysisEndpoints } from "@/lib/config";
import { getAuthToken, getClientTimezoneHeaders } from "@/lib/api-client";
import {
  getLastSelectedModelId,
  setLastSelectedModelId,
} from "@/lib/lastSelectedModel";
import { cn } from "@/lib/utils";

export interface ModelOption {
  id: string;
  name: string;
  provider: string;
}

export interface ModelSelectorProps {
  value: string;
  onChange: (modelId: string) => void;
  disabled?: boolean;
  models?: ModelOption[];
  isLoading?: boolean;
  className?: string;
  placeholder?: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Google",
  kimi: "Kimi",
  minimax: "MiniMax",
  glm: "GLM",
  doubao: "Doubao",
  opencode: "OpenCode Zen",
  openrouter: "OpenRouter",
};

function groupByProvider(models: ModelOption[]): Map<string, ModelOption[]> {
  const map = new Map<string, ModelOption[]>();
  for (const m of models) {
    const list = map.get(m.provider) ?? [];
    list.push(m);
    map.set(m.provider, list);
  }
  return map;
}

export function ModelSelector({
  value,
  onChange,
  disabled = false,
  models: modelsProp,
  isLoading: isLoadingProp,
  className,
  placeholder = "Model",
}: ModelSelectorProps) {
  const [models, setModels] = useState<ModelOption[]>(modelsProp ?? []);
  const [isLoading, setIsLoading] = useState(!modelsProp && !isLoadingProp);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (modelsProp !== undefined) {
      setModels(modelsProp);
      return;
    }
    if (isLoadingProp) {
      setIsLoading(true);
      return;
    }
    const controller = new AbortController();
    const fetchModels = async () => {
      setIsLoading(true);
      try {
        const headers: Record<string, string> = {
          ...getClientTimezoneHeaders(),
          "Content-Type": "application/json",
        };
        const token = getAuthToken();
        if (token) headers["Authorization"] = `Bearer ${token}`;
        const res = await fetch(analysisEndpoints.models, {
          headers,
          signal: controller.signal,
        });
        if (res.ok) {
          const data = await res.json();
          setModels(data.models ?? []);
        } else {
          setModels([]);
        }
      } catch {
        setModels([]);
      } finally {
        setIsLoading(false);
      }
    };
    fetchModels();
    return () => controller.abort();
  }, [modelsProp, isLoadingProp]);

  useEffect(() => {
    if (models.length === 0 || value) return;
    const initial = getInitialModelId(models);
    if (initial) onChange(initial);
  }, [models, value, onChange]);

  const handleSelect = (modelId: string) => {
    onChange(modelId);
    setLastSelectedModelId(modelId);
    setOpen(false);
  };

  const grouped = useMemo(() => groupByProvider(models), [models]);
  const selectedName = models.find((m) => m.id === value)?.name ?? (value || placeholder);

  const isEmpty = models.length === 0;
  const triggerDisabled = disabled || isLoading || isEmpty;

  // Compact trigger - no error display, truncate long names
  const triggerContent = (
    <button
      type="button"
      disabled={triggerDisabled}
      className={cn(
        "flex h-8 min-w-0 max-w-[140px] items-center gap-1 rounded-md border border-input bg-background px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed",
        className
      )}
    >
      {isLoading ? (
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
      ) : (
        <>
          <span className="truncate">{selectedName}</span>
          {!isEmpty && <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50" />}
        </>
      )}
    </button>
  );

  // Empty: compact trigger only, no popover, no error text
  if (isEmpty) {
    return triggerContent;
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {triggerContent}
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Search models..." className="h-9" />
          <CommandList>
            <CommandEmpty>No model found.</CommandEmpty>
            {Array.from(grouped.entries()).map(([provider, items]) => (
              <CommandGroup
                key={provider}
                heading={PROVIDER_LABELS[provider] ?? provider}
              >
                {items.map((m) => (
                  <CommandItem
                    key={m.id}
                    value={`${m.name} ${m.provider} ${m.id}`}
                    onSelect={() => handleSelect(m.id)}
                    className="flex items-center justify-between gap-2"
                  >
                    <span className="truncate">{m.name}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export function getInitialModelId(models: ModelOption[]): string {
  const stored = getLastSelectedModelId();
  if (stored && models.some((m) => m.id === stored)) return stored;
  return models[0]?.id ?? "";
}
