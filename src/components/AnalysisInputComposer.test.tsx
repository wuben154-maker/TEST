import type { ReactElement } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/contexts/LanguageContext';
import { AnalysisInputComposer } from '@/components/AnalysisInputComposer';

vi.mock('@/hooks/useVoiceInput', () => ({
  useVoiceInput: () => ({
    isSupported: false,
    isListening: false,
    transcript: '',
    startListening: vi.fn(),
    stopListening: vi.fn(),
    resetTranscript: vi.fn(),
  }),
}));

vi.mock('@/components/ModelSelector', () => ({
  ModelSelector: () => <div data-testid="model-selector-mock" />,
}));

function renderWithLang(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>{ui}</LanguageProvider>
    </QueryClientProvider>,
  );
}

describe('AnalysisInputComposer', () => {
  it('calls onSubmit with trimmed text and empty attachments', () => {
    const onSubmit = vi.fn();
    renderWithLang(<AnalysisInputComposer onSubmit={onSubmit} isAnalyzing={false} />);

    const ta = screen.getByTestId('analysis-input-textarea');
    fireEvent.change(ta, { target: { value: '  hello world  ' } });
    fireEvent.click(screen.getByTestId('analysis-input-send'));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith('hello world', [], undefined);
  });

  it('does not call onSubmit when textarea isSubmitting', () => {
    const onSubmit = vi.fn();
    renderWithLang(
      <AnalysisInputComposer onSubmit={onSubmit} isAnalyzing={false} isSubmitting />,
    );

    const ta = screen.getByTestId('analysis-input-textarea') as HTMLTextAreaElement;
    expect(ta.disabled).toBe(true);
    expect(screen.queryByTestId('analysis-input-send')).toBeNull();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
