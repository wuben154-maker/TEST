import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SharedReport from './SharedReport';

vi.mock('@/lib/config', () => ({
  config: { pythonBackendUrl: 'http://api.local' },
}));

vi.mock('@/lib/api-client', () => ({
  getClientTimezoneHeaders: () => ({ 'x-client-timezone': 'UTC' }),
}));

vi.mock('@/contexts/LanguageContext', () => ({
  useLanguage: () => ({
    t: {
      workspace: {
        title: 'Analysis Report',
        generatedAt: 'Generated at',
        reportTemplates: {
          security_analysis: 'Security Analysis',
          research_brief: 'Research Brief',
          executive_summary: 'Executive Summary',
          generic_analysis: 'Analysis Report',
        },
        taskPanel: {
          risk: 'Risk',
          sourceCount: 'sources',
          severityLabels: {
            critical: 'Critical',
            high: 'High',
            medium: 'Medium',
            low: 'Low',
            info: 'Info',
          },
        },
      },
      workspaceBlocks: {
        rawLog: 'Raw log',
        decodingAnalysis: 'Decoding analysis',
        copy: 'Copy',
        copied: 'Copied',
      },
      intel: {
        highRisk: 'High risk',
        mediumRisk: 'Medium risk',
        lowRisk: 'Low risk',
        safe: 'Safe',
        ipAddress: 'IP address',
        domain: 'Domain',
        indicator: 'Indicator',
        fileHash: 'file hash',
        viewInVirusTotal: 'View in VirusTotal',
      },
    },
  }),
}));

describe('SharedReport', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          title: 'Shared security report',
          created_at: '2026-04-25T09:00:00.000Z',
          blocks: [
            {
              type: 'analysis',
              id: 'analysis-1',
              title: 'Detailed analysis',
              content: '## Executive Summary\n\nShared report body.',
            },
          ],
        }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders analysis blocks on the shared report page', async () => {
    render(
      <MemoryRouter initialEntries={['/share/token-1']}>
        <Routes>
          <Route path="/share/:token" element={<SharedReport />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getAllByText('Shared security report').length).toBeGreaterThan(0);
    });

    expect(screen.queryByTestId('report-cover')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Shared security report', level: 1 })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Executive Summary' })).toBeTruthy();
    expect(screen.getByText('Shared report body.')).toBeTruthy();
  }, 10000);
});
