import { describe, it, expect, beforeEach } from 'vitest';
import { resolveTabAction, clearToolTabConfigCache } from './tool-tab-registry';
import type { WorkspaceTabConfig, WorkspaceTabInstance } from '@/types/analysis';

const SHELL_CONFIG: WorkspaceTabConfig = {
  type: 'shell',
  label: 'Shell',
  icon: 'terminal',
  merge_strategy: 'by_arg',
  merge_key: 'sandbox_id',
};

const IOC_CONFIG: WorkspaceTabConfig = {
  type: 'ioc_table',
  label: 'IOC 提取',
  icon: 'shield',
  merge_strategy: 'always',
};

const NEVER_CONFIG: WorkspaceTabConfig = {
  type: 'placeholder',
  label: 'Test',
  icon: 'file-text',
  merge_strategy: 'never',
};

const CONFIG_MAP: Record<string, WorkspaceTabConfig> = {
  sandbox_run: SHELL_CONFIG,
  extract_iocs: IOC_CONFIG,
  one_shot_tool: NEVER_CONFIG,
};

const EMPTY_TABS: WorkspaceTabInstance[] = [];

function makeShellTab(instanceKey: string): WorkspaceTabInstance {
  return {
    id: `shell-${instanceKey}`,
    type: 'shell',
    label: `Shell [${instanceKey}]`,
    icon: 'terminal',
    instanceKey,
    data: { kind: 'shell', lines: [] },
  };
}

function makeIocTab(): WorkspaceTabInstance {
  return {
    id: 'ioc_table-ioc_table',
    type: 'ioc_table',
    label: 'IOC 提取',
    icon: 'shield',
    instanceKey: 'ioc_table',
    data: { kind: 'ioc_table', raw: '' },
  };
}

describe('resolveTabAction', () => {
  beforeEach(() => {
    clearToolTabConfigCache();
  });

  describe('unknown tool', () => {
    it('returns null for tools not in config', () => {
      const result = resolveTabAction('unknown_tool', {}, EMPTY_TABS, CONFIG_MAP);
      expect(result).toBeNull();
    });
  });

  describe('merge_strategy: by_arg', () => {
    it('creates a new tab when no existing tabs', () => {
      const result = resolveTabAction('sandbox_run', { sandbox_id: 'sb-abc' }, EMPTY_TABS, CONFIG_MAP);
      expect(result).not.toBeNull();
      expect(result?.action).toBe('create');
      if (result?.action === 'create') {
        expect(result.tabConfig.type).toBe('shell');
        expect(result.tabConfig.instanceKey).toBe('sb-abc');
        expect(result.tabConfig.label).toBe('Shell [sb-abc]');
      }
    });

    it('appends to existing tab when sandbox_id matches', () => {
      const existing = [makeShellTab('sb-abc')];
      const result = resolveTabAction('sandbox_run', { sandbox_id: 'sb-abc' }, existing, CONFIG_MAP);
      expect(result?.action).toBe('append');
      if (result?.action === 'append') {
        expect(result.tabId).toBe('shell-sb-abc');
      }
    });

    it('creates a new tab when sandbox_id differs', () => {
      const existing = [makeShellTab('sb-abc')];
      const result = resolveTabAction('sandbox_run', { sandbox_id: 'sb-xyz' }, existing, CONFIG_MAP);
      expect(result?.action).toBe('create');
      if (result?.action === 'create') {
        expect(result.tabConfig.instanceKey).toBe('sb-xyz');
        expect(result.tabConfig.label).toBe('Shell [sb-xyz]');
      }
    });

    it('creates a new tab when sandbox_id is absent (one-shot mode)', () => {
      const result = resolveTabAction('sandbox_run', {}, EMPTY_TABS, CONFIG_MAP);
      expect(result?.action).toBe('create');
      if (result?.action === 'create') {
        // instanceKey is a generated uuid, label uses base label
        expect(result.tabConfig.type).toBe('shell');
      }
    });

    it('always creates new tab when sandbox_id absent even if shell tab exists', () => {
      const existing = [makeShellTab('sb-abc')];
      const result = resolveTabAction('sandbox_run', {}, existing, CONFIG_MAP);
      expect(result?.action).toBe('create');
    });
  });

  describe('merge_strategy: always', () => {
    it('creates first ioc_table tab when none exists', () => {
      const result = resolveTabAction('extract_iocs', {}, EMPTY_TABS, CONFIG_MAP);
      expect(result?.action).toBe('create');
      if (result?.action === 'create') {
        expect(result.tabConfig.type).toBe('ioc_table');
      }
    });

    it('appends to existing ioc_table tab on second call', () => {
      const existing = [makeIocTab()];
      const result = resolveTabAction('extract_iocs', {}, existing, CONFIG_MAP);
      expect(result?.action).toBe('append');
    });
  });

  describe('merge_strategy: never', () => {
    it('always creates a new tab', () => {
      const existing: WorkspaceTabInstance[] = [
        {
          id: 'placeholder-x',
          type: 'placeholder',
          label: 'Test',
          icon: 'file-text',
          instanceKey: 'x',
          data: { kind: 'placeholder', message: '' },
        },
      ];
      const result = resolveTabAction('one_shot_tool', {}, existing, CONFIG_MAP);
      expect(result?.action).toBe('create');
    });
  });
});
