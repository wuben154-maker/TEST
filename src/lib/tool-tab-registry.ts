/**
 * ToolTabRegistry — loads workspace_tab config from the backend and resolves
 * merge decisions for each tool_call SSE event.
 *
 * Merge strategies:
 *   by_arg  — merge when the value of merge_key tool argument matches an existing tab
 *   always  — always merge all calls into one tab of this type per result
 *   never   — always create a new tab (or absent merge_key value → treat as never)
 */

import { activeApiBaseUrl } from '@/lib/config';
import type { WorkspaceTabConfig, WorkspaceTabInstance, WorkspaceTabData } from '@/types/analysis';

export type TabResolveAction =
  | { action: 'create'; tabConfig: Omit<WorkspaceTabInstance, 'data'> & { initialData: WorkspaceTabData } }
  | { action: 'append'; tabId: string };

/** Raw response from GET /tool-tab-config */
interface ToolTabConfigResponse {
  tools: Record<string, { workspace_tab: WorkspaceTabConfig }>;
}

let _configCache: Record<string, WorkspaceTabConfig> | null = null;

/** Fetch and cache the workspace_tab config from the backend (once per session). */
export async function loadToolTabConfig(): Promise<Record<string, WorkspaceTabConfig>> {
  if (_configCache !== null) return _configCache;
  try {
    const res = await fetch(`${activeApiBaseUrl}/tool-tab-config`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body: ToolTabConfigResponse = await res.json();
    const map: Record<string, WorkspaceTabConfig> = {};
    for (const [toolName, entry] of Object.entries(body.tools ?? {})) {
      if (entry?.workspace_tab) {
        map[toolName] = entry.workspace_tab;
      }
    }
    _configCache = map;
    return map;
  } catch {
    _configCache = {};
    return {};
  }
}

/** Force a reload on next access (e.g. after YAML hot-reload). */
export function clearToolTabConfigCache(): void {
  _configCache = null;
}

let _uuid = 0;
function nextUuid(): string {
  return `tab-${Date.now()}-${++_uuid}`;
}

function buildInitialData(type: string): WorkspaceTabData {
  if (type === 'shell') return { kind: 'shell', lines: [] };
  if (type === 'ioc_table') return { kind: 'ioc_table', raw: '' };
  return { kind: 'placeholder', message: '即将推出' };
}

/**
 * Resolve what should happen when a tool_call arrives.
 *
 * @param toolName   - SSE toolName field
 * @param toolArgs   - SSE toolInput / args (may be undefined)
 * @param existingTabs - current workspaceTabs array for this AnalysisResult
 * @param config     - loaded config map (from loadToolTabConfig())
 * @returns TabResolveAction | null — null means this tool has no workspace tab declaration
 */
export function resolveTabAction(
  toolName: string,
  toolArgs: Record<string, unknown> | undefined,
  existingTabs: WorkspaceTabInstance[],
  config: Record<string, WorkspaceTabConfig>,
): TabResolveAction | null {
  const wt = config[toolName];
  if (!wt) return null;

  const strategy = wt.merge_strategy ?? 'never';

  if (strategy === 'always') {
    const existing = existingTabs.find((t) => t.type === wt.type);
    if (existing) {
      return { action: 'append', tabId: existing.id };
    }
    const instanceKey = wt.type;
    const id = `${wt.type}-${instanceKey}`;
    return {
      action: 'create',
      tabConfig: {
        id,
        type: wt.type,
        label: wt.label,
        icon: wt.icon,
        instanceKey,
        initialData: buildInitialData(wt.type),
      },
    };
  }

  if (strategy === 'by_arg') {
    const argValue = wt.merge_key ? (toolArgs?.[wt.merge_key] as string | undefined) : undefined;
    const instanceKey = argValue ?? nextUuid();
    const id = `${wt.type}-${instanceKey}`;

    if (argValue) {
      const existing = existingTabs.find((t) => t.type === wt.type && t.instanceKey === instanceKey);
      if (existing) {
        return { action: 'append', tabId: existing.id };
      }
    }

    const label = argValue ? `${wt.label} [${instanceKey}]` : wt.label;
    return {
      action: 'create',
      tabConfig: {
        id,
        type: wt.type,
        label,
        icon: wt.icon,
        instanceKey,
        initialData: buildInitialData(wt.type),
      },
    };
  }

  // strategy === 'never' — always create
  const instanceKey = nextUuid();
  const id = `${wt.type}-${instanceKey}`;
  return {
    action: 'create',
    tabConfig: {
      id,
      type: wt.type,
      label: wt.label,
      icon: wt.icon,
      instanceKey,
      initialData: buildInitialData(wt.type),
    },
  };
}
