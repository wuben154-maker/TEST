import type { ReactElement } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider, Outlet } from 'react-router-dom';
import { LanguageProvider } from '@/contexts/LanguageContext';
import { PostLoginWorkspaceStart } from '@/components/PostLoginWorkspaceStart';

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

vi.mock('@/components/TopNavbar', () => ({
  TopNavbar: () => <div data-testid="top-navbar-mock" />,
}));

function renderWithRouter(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      {
        path: '/start',
        element: (
          <QueryClientProvider client={client}>
            <LanguageProvider>
              <Outlet context={{ openMobileSidebar: vi.fn(), closeMobileSidebar: vi.fn() }} />
            </LanguageProvider>
          </QueryClientProvider>
        ),
        children: [{ index: true, element: ui }],
      },
    ],
    { initialEntries: ['/start'] },
  );
  return render(<RouterProvider router={router} />);
}

describe('PostLoginWorkspaceStart', () => {
  it('renders top navbar and start composer only (no right workspace pane)', () => {
    renderWithRouter(
      <PostLoginWorkspaceStart
        onStart={vi.fn()}
        ensureProjectForLanding={vi.fn().mockResolvedValue('proj-test-id')}
        isAnalyzing={false}
      />,
    );

    expect(screen.getByTestId('top-navbar-mock')).toBeTruthy();
    expect(screen.getByText('What do you want to work on?')).toBeTruthy();
    expect(document.querySelector('[data-testid="post-login-workspace-preview"]')).toBeNull();
  });
});
