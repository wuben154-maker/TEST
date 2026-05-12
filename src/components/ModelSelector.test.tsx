import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ModelSelector, getInitialModelId } from './ModelSelector';
import { LAST_SELECTED_MODEL_STORAGE_KEY } from '@/lib/lastSelectedModel';

class ResizeObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

describe('ModelSelector', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('groups OpenRouter models separately from OpenCode models', async () => {
    render(
      <ModelSelector
        value=""
        onChange={vi.fn()}
        models={[
          {
            id: 'openrouter/anthropic/claude-opus-4.7',
            name: 'Claude Opus 4.7 (OpenRouter)',
            provider: 'openrouter',
          },
          {
            id: 'opencode/gpt-5.5',
            name: 'GPT 5.5 (Zen)',
            provider: 'opencode',
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole('button'));

    expect(await screen.findByText('OpenRouter')).toBeTruthy();
    expect(screen.getByText('OpenCode Zen')).toBeTruthy();
  }, 10000);

  it('selects an OpenRouter gateway id unchanged', async () => {
    const onChange = vi.fn();
    render(
      <ModelSelector
        value="openrouter/anthropic/claude-opus-4.7"
        onChange={onChange}
        models={[
          {
            id: 'openrouter/anthropic/claude-opus-4.7',
            name: 'Claude Opus 4.7 (OpenRouter)',
            provider: 'openrouter',
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole('button'));
    fireEvent.click(await screen.findByRole('option', { name: 'Claude Opus 4.7 (OpenRouter)' }));

    expect(onChange).toHaveBeenCalledWith('openrouter/anthropic/claude-opus-4.7');
  });

  it('falls back when a stored OpenCode selection is no longer available', () => {
    localStorage.setItem(LAST_SELECTED_MODEL_STORAGE_KEY, 'opencode/gpt-5.5');

    const initial = getInitialModelId([
      {
        id: 'openrouter/anthropic/claude-sonnet-4.6',
        name: 'Claude Sonnet 4.6 (OpenRouter)',
        provider: 'openrouter',
      },
    ]);

    expect(initial).toBe('openrouter/anthropic/claude-sonnet-4.6');
  });
});
