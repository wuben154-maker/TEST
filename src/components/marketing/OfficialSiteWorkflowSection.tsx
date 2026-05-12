import { useId } from 'react';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/contexts/LanguageContext';
import './official-site-workflow.css';

function marketingTpl(template: string, vars: Record<string, string>): string {
  return Object.entries(vars).reduce((acc, [k, v]) => acc.replaceAll(`{{${k}}}`, v), template);
}

const SECONDARY_BTN =
  'inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-lg border border-[rgba(232,229,222,0.35)] bg-transparent px-4 text-[13px] font-normal text-[#e8e5de] transition-colors hover:bg-[rgba(232,229,222,0.06)] focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)] focus-visible:outline-none';

/** Workflow demo — parity with prototype HTML #workflow; strings from `t.marketing`. */
export function OfficialSiteWorkflowSection() {
  const uid = useId().replace(/:/g, '');
  const markerEndId = `workflowLoopArrowHead-${uid}`;
  const { t } = useLanguage();
  const m = t.marketing;

  return (
    <section
      id="workflow"
      className={cn(
        'official-site-workflow scroll-mt-[72px]',
        'border-y border-[#2e2c28]',
        'bg-[rgba(32,30,27,0.35)]',
        'px-4 pb-[clamp(64px,10vw,112px)] pt-[clamp(12px,2vw,24px)] md:px-6',
      )}
      aria-labelledby="workflow-title"
    >
      <div className="mx-auto max-w-[1200px]">
        <header className="mb-8 w-full">
          <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#e8e5de]/35">
            {m.wfEyebrow}
          </p>
          <h2
            id="workflow-title"
            className="mb-3 max-w-none text-[32px] font-semibold leading-tight tracking-[-0.5px] [word-break:keep-all]"
          >
            {m.wfTitle}
          </h2>
          <p className="max-w-[52rem] text-balance text-[16px] leading-[1.65] text-[#e8e5de]/83">
            {m.wfSubtitle}
          </p>
        </header>

        <div className="relative mx-auto mt-6 flex max-w-[760px] flex-col gap-6 overflow-visible" aria-label={m.wfTimelineAria}>
          <svg
            className="osw-loop-arrow-svg"
            viewBox="0 0 56 900"
            preserveAspectRatio="none"
            width={52}
            height={900}
            aria-hidden
            focusable="false"
          >
            <defs>
              <marker
                id={markerEndId}
                markerWidth={7}
                markerHeight={7}
                refX={6}
                refY={3.5}
                orient="auto"
              >
                <polygon fill="rgba(165,180,252,0.48)" points="0 0, 7 3.5, 0 7" />
              </marker>
            </defs>
            <path
              fill="none"
              stroke="rgba(165,180,252,0.38)"
              strokeWidth={1.5}
              strokeDasharray="6 5"
              strokeLinecap="round"
              markerEnd={`url(#${markerEndId})`}
              d="M 24 862 C -40 862, -44 480, -36 280 C -32 140, -8 48, 24 22"
            />
          </svg>
          <span className="osw-loop-label" aria-hidden>
            {m.wfLoop}
          </span>

          {/* Step 1 — Perceive */}
          <div className="osw-timeline-step relative z-[1] grid grid-cols-[48px_1fr] gap-x-5 gap-y-0 items-stretch">
            <div className="flex flex-col items-center pt-0.5" aria-hidden>
              <span
                className={cn(
                  'osw-step-number flex h-8 w-8 items-center justify-center rounded-full border text-sm font-semibold text-[#e8e5de]',
                  'border-[rgba(232,229,222,0.35)] bg-[rgba(232,229,222,0.02)] transition-[border-color] duration-200',
                )}
              >
                1
              </span>
              <span className="mx-auto mt-2 min-h-[1rem] w-px flex-1 bg-[#2e2c28]" />
            </div>
            <div>
              <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#e8e5de]/35">{m.wfPerceive}</p>
              <div
                className="flex min-h-[280px] flex-col overflow-hidden rounded-xl border border-[#2e2c28] bg-[#282623]"
                aria-label={m.wfPerceiveAria}
              >
                <div className="border-b border-[#2e2c28] bg-[#201e1b] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.06em] text-[#e8e5de]/35">
                  {m.wfRawSignalTitle}
                </div>
                <div className="flex-1 p-4">
                  <p className="m-0 font-mono text-[12px] leading-[1.55] text-[#e8e5de]/83" tabIndex={0}>
                    {m.wfRawSample}
                  </p>
                </div>
                <div className="flex flex-col border-t border-[rgba(165,180,252,0.15)] bg-[rgba(165,180,252,0.04)]">
                  <div className="border-b border-[rgba(165,180,252,0.08)] px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.07em] text-[rgba(165,180,252,0.7)]">
                    {m.wfAgentReasoning}
                  </div>
                  <div className="flex flex-col gap-2 px-4 py-3">
                    <div className="flex items-baseline gap-3 font-mono text-[12px] leading-normal">
                      <span className="w-16 shrink-0 text-[11px] font-semibold tracking-[0.02em] text-[rgba(165,180,252,0.6)]">
                        {m.wfIntent}
                      </span>
                      <span className="text-[#e8e5de]/83">{m.wfIntentValue}</span>
                    </div>
                    <div className="flex items-baseline gap-3 font-mono text-[12px] leading-normal">
                      <span className="w-16 shrink-0 text-[11px] font-semibold tracking-[0.02em] text-[rgba(165,180,252,0.6)]">
                        {m.wfStrategy}
                      </span>
                      <span className="text-[#e8e5de]/83">{m.wfStrategyValue}</span>
                    </div>
                    <div className="flex items-baseline gap-3 font-mono text-[12px] leading-normal">
                      <span className="w-16 shrink-0 text-[11px] font-semibold tracking-[0.02em] text-[rgba(165,180,252,0.6)]">
                        {m.wfPriority}
                      </span>
                      <span className="font-semibold text-[rgba(234,179,8,0.92)]">{m.wfPriorityValue}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Step 2 — Investigate */}
          <div className="osw-timeline-step relative z-[1] grid grid-cols-[48px_1fr] gap-x-5 items-stretch">
            <div className="flex flex-col items-center pt-0.5" aria-hidden>
              <span
                className={cn(
                  'osw-step-number flex h-8 w-8 items-center justify-center rounded-full border text-sm font-semibold text-[#e8e5de]',
                  'border-[rgba(232,229,222,0.35)] bg-[rgba(232,229,222,0.02)] transition-[border-color] duration-200',
                )}
              >
                2
              </span>
              <span className="mx-auto mt-2 min-h-[1rem] w-px flex-1 bg-[#2e2c28]" />
            </div>
            <div>
              <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#e8e5de]/35">{m.wfInvestigate}</p>
              <div
                className="osw-agent-log-panel flex min-h-[280px] flex-col overflow-hidden rounded-xl border border-[#2e2c28] bg-[#282623]"
                aria-label={m.wfExecAria}
              >
                <div className="flex items-center justify-between gap-3 border-b border-[#2e2c28] bg-[#201e1b] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.06em] text-[#e8e5de]/35">
                  <span>{m.wfLeadAgent}</span>
                  <span className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap font-semibold text-[rgba(232,229,222,0.78)]">
                    <span className="osw-agent-log-dot h-2 w-2 shrink-0 rounded-full bg-[rgba(34,197,94,0.9)]" aria-hidden />
                    {m.wfProcessing}
                  </span>
                </div>
                <div className="flex-1 p-4">
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-3 font-mono text-[12px] leading-[1.55] text-[#e8e5de]/83">
                      <span className="inline-flex min-w-0 items-start gap-2.5">
                        <span className="shrink-0 font-semibold text-[rgba(34,197,94,0.92)]">[✓]</span>
                        <span className="min-w-0">{m.wfLineIntent}</span>
                      </span>
                      <span className="shrink-0 whitespace-nowrap text-[rgba(232,229,222,0.55)]">
                        {marketingTpl(m.wfStepSeconds, { seconds: '0.3' })}
                      </span>
                    </div>

                    <div className="flex flex-col gap-2 rounded-lg border border-[rgba(165,180,252,0.14)] bg-[rgba(165,180,252,0.03)] px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[rgba(165,180,252,0.6)]" aria-hidden />
                        <span className="inline-flex items-center whitespace-nowrap rounded-full border border-[rgba(165,180,252,0.2)] bg-[rgba(165,180,252,0.08)] px-2 py-0.5 text-[11px] font-semibold tracking-[0.03em] text-[rgba(165,180,252,0.9)]">
                          {m.wfPhishingSubAgent}
                        </span>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <div className="flex items-center justify-between gap-3 font-mono text-[12px] leading-normal text-[#e8e5de]/83">
                          <span className="inline-flex items-center gap-2">
                            <span className="shrink-0 font-semibold text-[rgba(34,197,94,0.92)]">[✓]</span>
                            <span>{m.wfLineIoc}</span>
                          </span>
                          <span className="shrink-0 whitespace-nowrap text-[rgba(232,229,222,0.55)]">
                            {marketingTpl(m.wfIocFound, { count: '14' })}
                          </span>
                        </div>
                        <div className="flex items-center justify-between gap-3 font-mono text-[12px] leading-normal text-[#e8e5de]/83">
                          <span className="inline-flex items-center gap-2">
                            <span className="shrink-0 font-semibold text-[rgba(34,197,94,0.92)]">[✓]</span>
                            <span>{m.wfLineSandbox}</span>
                          </span>
                          <span className="shrink-0 whitespace-nowrap text-[rgba(232,229,222,0.55)]">
                            {m.wfSandboxMalicious}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col gap-2 rounded-lg border border-[rgba(165,180,252,0.14)] bg-[rgba(165,180,252,0.03)] px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[rgba(165,180,252,0.6)]" aria-hidden />
                        <span className="inline-flex items-center whitespace-nowrap rounded-full border border-[rgba(165,180,252,0.2)] bg-[rgba(165,180,252,0.08)] px-2 py-0.5 text-[11px] font-semibold tracking-[0.03em] text-[rgba(165,180,252,0.9)]">
                          {m.wfTracingSubAgent}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-3 font-mono text-[12px] leading-normal text-[#e8e5de]/83">
                        <span className="inline-flex items-center gap-2">
                          <span className="shrink-0 font-semibold text-[rgba(34,197,94,0.92)]">[✓]</span>
                          <span>{m.wfLineAttck}</span>
                        </span>
                        <span className="shrink-0 whitespace-nowrap text-[rgba(232,229,222,0.55)]">
                          {m.wfSandboxConfirmed}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Step 3 — Reflect */}
          <div className="osw-timeline-step relative z-[1] grid grid-cols-[48px_1fr] gap-x-5 items-stretch">
            <div className="flex flex-col items-center pt-0.5" aria-hidden>
              <span
                className={cn(
                  'osw-step-number flex h-8 w-8 items-center justify-center rounded-full border text-sm font-semibold text-[#e8e5de]',
                  'border-[rgba(232,229,222,0.35)] bg-[rgba(232,229,222,0.02)] transition-[border-color] duration-200',
                )}
              >
                3
              </span>
              <span className="mx-auto mt-2 min-h-[1rem] w-px flex-1 bg-[#2e2c28]" />
            </div>
            <div>
              <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#e8e5de]/35">{m.wfReflect}</p>
              <div
                className="flex flex-col overflow-hidden rounded-xl border border-[rgba(96,165,250,0.18)] bg-[rgba(96,165,250,0.03)]"
                aria-label={m.wfReflectAria}
              >
                <div className="flex items-center justify-between gap-3 border-b border-[rgba(96,165,250,0.12)] bg-[rgba(96,165,250,0.04)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.06em] text-[#e8e5de]/35">
                  <span>{m.wfSelfValidation}</span>
                  <span className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap font-semibold text-[rgba(96,165,250,0.9)]">
                    <span className="osw-reflect-dot h-2 w-2 shrink-0 rounded-full bg-[rgba(96,165,250,0.9)]" aria-hidden />
                    {m.wfVerified}
                  </span>
                </div>
                <div className="flex flex-col gap-2.5 p-4 font-mono text-[12px] leading-[1.55]">
                  <div className="flex items-center justify-between gap-3 text-[#e8e5de]/83">
                    <span className="inline-flex items-center gap-2.5">
                      <span className="shrink-0 font-semibold text-[rgba(34,197,94,0.92)]">[✓]</span>
                      <span>{m.wfReflect1}</span>
                    </span>
                    <span className="shrink-0 whitespace-nowrap text-[rgba(232,229,222,0.55)]">{m.wfReflectMeta1}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3 text-[#e8e5de]/83">
                    <span className="inline-flex items-center gap-2.5">
                      <span className="shrink-0 font-semibold text-[rgba(34,197,94,0.92)]">[✓]</span>
                      <span>{m.wfReflect2}</span>
                    </span>
                    <span className="shrink-0 whitespace-nowrap text-[rgba(232,229,222,0.55)]">{m.wfReflectMeta2}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3 text-[#e8e5de]/83">
                    <span className="inline-flex items-center gap-2.5">
                      <span className="shrink-0 font-semibold text-[rgba(34,197,94,0.92)]">[✓]</span>
                      <span>{m.wfReflect3}</span>
                    </span>
                    <span className="shrink-0 whitespace-nowrap text-[rgba(232,229,222,0.55)]">{m.wfReflectMeta3}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3 text-[#e8e5de]/83">
                    <span className="inline-flex items-center gap-2.5">
                      <span className="shrink-0 font-semibold text-[rgba(234,179,8,0.92)]">[⚠]</span>
                      <span>{m.wfReflect4}</span>
                    </span>
                    <span className="shrink-0 whitespace-nowrap text-[rgba(232,229,222,0.55)]">{m.wfReflectMeta4}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Step 4 — Verdict & Act */}
          <div className="osw-timeline-step relative z-[1] grid grid-cols-[48px_1fr] gap-x-5 items-stretch">
            <div className="flex flex-col items-center pt-0.5" aria-hidden>
              <span
                className={cn(
                  'osw-step-number flex h-8 w-8 items-center justify-center rounded-full border text-sm font-semibold text-[#e8e5de]',
                  'border-[rgba(232,229,222,0.35)] bg-[rgba(232,229,222,0.02)] transition-[border-color] duration-200',
                )}
              >
                4
              </span>
            </div>
            <div>
              <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#e8e5de]/35">{m.wfVerdictStep}</p>
              <div className="osw-output-card flex min-h-[100%] flex-col rounded-xl border border-[#2e2c28] bg-[#201e1b]" aria-label={m.wfOutputAria}>
                <div className="flex items-start justify-between gap-3 border-b border-[#2e2c28] p-4">
                  <h3 className="m-0 text-[16px] font-semibold tracking-[-0.3px] text-[#e8e5de]">{m.wfVerdictHeading}</h3>
                  <span className="inline-flex h-6 shrink-0 items-center rounded-md border border-[rgba(208,88,88,0.25)] bg-[rgba(208,88,88,0.08)] px-2.5 text-[12px] font-medium text-[#d05858]">
                    {m.wfCriticalBadge}
                  </span>
                </div>
                <p className="m-0 p-4 text-[14px] leading-[1.65] text-[#e8e5de]/83">{m.wfDemoBody}</p>
                <details className="border-t border-[#2e2c28]">
                  <summary className="cursor-pointer px-4 py-3 text-[13px] font-semibold text-[#e8e5de]">{m.wfEvidenceToggle}</summary>
                  <pre className="m-0 overflow-x-auto whitespace-pre px-4 pb-4 font-mono text-[12px] leading-normal text-[#e8e5de]/83" tabIndex={0}>
                    {m.wfEvidencePre}
                  </pre>
                </details>
                <div className="mt-auto flex flex-wrap gap-2 border-t border-[#2e2c28] p-4">
                  <button type="button" className={SECONDARY_BTN}>
                    {m.wfExportIoc}
                  </button>
                  <button type="button" className={SECONDARY_BTN}>
                    {m.wfDraftNotify}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
