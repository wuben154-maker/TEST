import { describe, expect, it } from 'vitest';
import { stripLeadingPrefaceBeforeCjkReportBody } from './stripCjkReportPreface';

describe('stripLeadingPrefaceBeforeCjkReportBody', () => {
  it('returns unchanged when no CJK paragraph meets threshold', () => {
    const en = 'Hello world.\n\nSecond paragraph.';
    expect(stripLeadingPrefaceBeforeCjkReportBody(en)).toBe(en.trim());
  });

  it('strips English preface before Chinese report', () => {
    const raw = `Analyzing SOC Architecture

I'm currently focused on dissecting the integration of EDR and SIEM.

大规模SOC环境下的自动化分诊实施方案研究报告
在每日告警量达到10万级别的超大规模安全运营中心（SOC）中，传统的依靠人工逐一审计告警的模式已无法维系。`;
    const out = stripLeadingPrefaceBeforeCjkReportBody(raw);
    expect(out.startsWith('大规模SOC')).toBe(true);
    expect(out).not.toContain('Analyzing SOC');
  });
});
