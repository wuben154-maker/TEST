/**
 * Solution landing copy sourced from static HTML under docs/marketing reference
 * (user-provided exports from solutions/*.html).
 */

export const marketingSolutionPagesEn = {
  securityTeam: {
    docTitle: "Security Team — Security Manus",
    navTitle: "Security Team",
    heroEyebrow: "For",
    heroTitle: "Your AI teammate for the SOC.",
    lead: "Hand off triage, scoping, and runbook execution to the agent. You stay in control — review verdicts, cite evidence, ship the action.",
    benefitsHeading: "What you get",
    benefits: [
      {
        title: "Less toil, more judgment",
        desc: "Repeat triage and scoping handled by the agent. You spend time on decisions.",
      },
      {
        title: "Cited verdicts, not vibes",
        desc: "Every conclusion ships with evidence and a clear next step.",
      },
      {
        title: "Same console, three jobs",
        desc: "Triage, IR, and hunting share one agent and one investigation history.",
      },
      {
        title: "Audit-ready by default",
        desc: "Actions are logged and replayable — ready for review and reporting.",
      },
    ],
    stepsHeading: "How a shift looks",
    steps: [
      { title: "Inbox lands", body: "Alerts, user reports, and IOCs flow into one queue." },
      { title: "Agent triages", body: "Verdict, evidence, and recommended action are drafted automatically." },
      { title: "You review", body: "Approve, edit, or escalate. Your decisions shape the next investigation." },
      { title: "Agent acts", body: "Containment, pivots, and ticket drafts run under your approval." },
      { title: "Hand off clean", body: "Closed cases turn into reusable, cited runbooks for the next shift." },
    ],
    sampleHeading: "Sample output",
    sampleCardTitle: "Shift summary — 18:00–02:00",
    sampleBody: `Closed by agent (with your approval)
  · 47 user-reported emails  →  3 phishing, 44 benign
  · 12 SIEM alerts           →  10 closed, 2 escalated
  · 6 IOC pivots             →  1 confirmed infected host (HOSTNAME)

Escalated for IR
  · "Impossible travel + new OAuth grant" (Okta) — confirmed ATO
  · Suspicious binary on HOSTNAME — sandbox verdict 9.4/10

Knowledge captured
  · 2 new runbooks generated from tonight's investigations
  · 4 detections suggested for review

Time saved this shift   ~4.8 hours of manual triage`,
    whyHeading: "Why it matters",
    metrics: [
      { kpi: "Less toil", label: "Routine triage hours → minutes" },
      { kpi: "Faster scoping", label: "Cross-log pivots happen by default" },
      { kpi: "Knowledge keeps", label: "Every case becomes a cited runbook" },
    ],
    trustHeading: "Built for how the team actually works",
    trustBullets: [
      "Tier-1/2 analyst: auto-triage, evidence-backed verdicts, one-click escalate.",
      "Incident responder: scope, attack timeline, and report draft from a single IOC.",
      "Threat hunter: plain-language pivots and new detection drafts on close.",
    ],
  },
  msspMdr: {
    docTitle: "MSSP & MDR — Security Manus",
    navTitle: "MSSP & MDR",
    heroEyebrow: "For",
    heroTitle: "Serve more tenants per analyst — without lowering the bar.",
    lead: "Multi-tenant by design. The agent triages, scopes, and reports per tenant — your team stays in the loop and on-brand.",
    benefitsHeading: "What you get",
    benefits: [
      {
        title: "Multi-tenant isolation",
        desc: "Per-tenant context, data, and audit. No cross-tenant leakage.",
      },
      {
        title: "Standardized delivery",
        desc: "Consistent reports across tenants — your template, your tone.",
      },
      {
        title: "White-label ready",
        desc: "Brand the analyst console and the customer-facing portal.",
      },
      {
        title: "Margin math that works",
        desc: "More tenants per analyst, lower cost-to-serve.",
      },
    ],
    stepsHeading: "How it works",
    steps: [
      { title: "Onboard tenant", body: "Configure connectors, data residency, and policies per tenant." },
      { title: "Route alerts", body: "Each tenant’s alerts flow into its isolated agent context." },
      { title: "Agent investigates", body: "Triage and scoping run per tenant, with citations." },
      { title: "Analyst reviews", body: "Approve, edit, or escalate inside one console across many tenants." },
      { title: "Deliver", body: "Branded report and ticket drafts pushed to the tenant portal." },
    ],
    sampleHeading: "Sample output",
    sampleCardTitle: "Weekly Tenant Brief — Acme Bank",
    sampleBody: `Week overview
  · Alerts ingested     1,284
  · Cases opened        38
  · Cases closed        35
  · SLA met             99.4%

Top incidents
  · ATO attempt via OAuth grant — contained (Okta + M365)
  · Malware on HOSTNAME — remediated (EDR isolate + cleanup)

Coverage & hygiene
  · Email phishing: improved detection on 2 sender patterns
  · Endpoint: 3 policy recommendations

Recommendations (next 7 days)
  · Enforce MFA on 12 privileged accounts
  · Add 2 detections (draft queries included)`,
    whyHeading: "Why it matters",
    metrics: [
      { kpi: "More tenants", label: "Per analyst — without adding headcount" },
      { kpi: "Defensible delivery", label: "Evidence-cited reports every time" },
      { kpi: "Stable SLA", label: "Consistency across tenants and shifts" },
    ],
    trustHeading: "Trust & Deploy",
    trustBullets: [
      "Tenant isolation: per-tenant connectors, policies, and audit history.",
      "Customer-controlled retention and export of reports and evidence.",
      "Multi-tenant SaaS or single-tenant private deployment (VPC / on-prem).",
    ],
  },
  securityLeader: {
    docTitle: "Security Leader — Security Manus",
    navTitle: "Security Leader",
    heroEyebrow: "For",
    heroTitle: "Defensible decisions, backed by evidence.",
    lead: "Turn investigations into defensible decisions — executive narrative, audit-grade history, and clear next-month risks.",
    benefitsHeading: "What you get",
    benefits: [
      {
        title: "Board-ready narrative",
        desc: "A monthly story executives can repeat — backed by citations.",
      },
      {
        title: "Audit-grade history",
        desc: "Replayable decisions, evidence, and actions over time.",
      },
      {
        title: "Coverage visibility",
        desc: "What you covered, what you missed, and why.",
      },
      {
        title: "Lower cost-to-serve",
        desc: "Less manual reporting and fewer context switches.",
      },
    ],
    stepsHeading: "How it works",
    steps: [
      { title: "Pick a window", body: "Select a time range (week / month / quarter) and scope." },
      { title: "Agent aggregates", body: "Collects cases, evidence, actions, and outcomes across your stack." },
      { title: "Draft the brief", body: "Turns operational output into an executive narrative with citations." },
      { title: "You edit", body: "Adjust emphasis, add context, and align with your reporting style." },
      { title: "Export", body: "PDF / doc output, plus an audit appendix if needed." },
    ],
    sampleHeading: "Sample output",
    sampleCardTitle: "Executive Brief — April 2026",
    sampleBody: `Headline outcomes
  · MTTD  8m → 6m
  · MTTR  62m → 41m
  · Tier-1 closure rate  78% → 91%

Top incidents (with citations)
  · OAuth-based ATO attempt — contained; no confirmed data loss
  · Malware on HOSTNAME — isolated and remediated within 23 minutes

Open risks
  · 12 privileged accounts without enforced MFA
  · Incomplete endpoint coverage on 8% of fleet

Investments recommended
  · Close MFA gap (priority 1)
  · Add 2 detections (draft queries included)
  · Improve endpoint onboarding runbook (agent-generated)

Next month focus
  · Reduce repeat triage categories via automation + training loop`,
    whyHeading: "Why it matters",
    metrics: [
      { kpi: "Defensible", label: "Every claim backed by evidence" },
      { kpi: "Comparable", label: "Month-over-month metrics and trends" },
      { kpi: "Lower cost-to-serve", label: "Less manual reporting overhead" },
    ],
    trustHeading: "Trust & Deploy",
    trustBullets: [
      "Read-only by default: start with reporting without changing production systems.",
      "Replayable audit appendix: citations for decisions, evidence, and actions.",
      "On-prem / VPC deployment options for regulated environments.",
    ],
  },
  phishingEmail: {
    docTitle: "Phishing & Email — Security Manus",
    navTitle: "Phishing & Email",
    heroEyebrow: "Use case",
    heroTitle: "Triage phishing in seconds, not hours.",
    lead: "Drop an .eml or paste a URL. Get a verdict, IOCs, and a containment plan — every claim cited with evidence.",
    benefitsHeading: "What it does",
    benefits: [
      {
        title: "User-reported email triage",
        desc: "Forward suspicious emails to a shared inbox. The agent triages and returns a verdict with evidence.",
      },
      {
        title: "Executive inbox screening",
        desc: "Prioritize high-risk messages for high-value mailboxes — fast, consistent, and auditable.",
      },
      {
        title: "Campaign clustering",
        desc: "Group similar emails into a single campaign so one investigation covers many reports.",
      },
      {
        title: "URL & attachment safety check",
        desc: "Paste a URL or drop an attachment. Get a detonation-backed verdict in under a minute.",
      },
    ],
    stepsHeading: "How it works",
    steps: [
      { title: "Submit", body: "Drop an .eml, forward to the agent inbox, or paste a URL." },
      { title: "Parse", body: "Headers, SPF/DKIM/DMARC signals, links, and attachments are extracted." },
      { title: "Detonate", body: "Attachments and URLs are detonated in an isolated sandbox for behavior-backed evidence." },
      { title: "Correlate", body: "IOCs are pivoted across your stack and matched to historical campaigns and intel." },
      { title: "Conclude", body: "The Lead Agent writes the verdict, cites evidence, and proposes containment steps." },
    ],
    sampleHeading: "Sample output",
    sampleCardTitle: "Phishing verdict — cited evidence",
    sampleBody: `Verdict        Phishing — High confidence (0.94)
Campaign       "Payroll Lure" cluster · active since 2024-11
Key evidence
  · SPF fail / DKIM fail / DMARC quarantine
  · Sender domain  secure-payroll-alerts.com  (registered 4 days ago)
  · Attachment    Payroll_Update.js — obfuscated downloader
  · C2 contacted  mal-c2[.]xyz  → 185.x.x.x
Recommended actions
  · Quarantine 7 messages in user mailboxes
  · Block sender domain on email gateway
  · Reset credentials for 2 users who clicked the link`,
    whyHeading: "Why it matters",
    metrics: [
      { kpi: "~25 min → ~2 min", label: "Time to verdict for routine reports" },
      { kpi: "3–5×", label: "More reports per analyst per shift" },
      { kpi: "Audit-ready", label: "Every verdict ships with cited evidence" },
    ],
    trustHeading: "Trust & Deploy",
    trustBullets: [
      "Attachments are detonated in an isolated sandbox. Optional zero-retention mode for email content.",
      "SSO + RBAC + full audit trail for every agent action.",
      "On-prem / VPC deployment for regulated environments.",
    ],
  },
  malwareAnalysis: {
    docTitle: "Malware Analysis — Security Manus",
    navTitle: "Malware Analysis",
    heroEyebrow: "Use case",
    heroTitle: "Verdict any binary — sandbox to ATT&CK map.",
    lead: "Submit a sample. Get a verdict, behavioral evidence, and an ATT&CK matrix — without standing up your own sandbox.",
    benefitsHeading: "What it does",
    benefits: [
      {
        title: "Suspicious file triage",
        desc: "Verdict a file pulled from EDR, email, or user upload — fast and evidence-backed.",
      },
      {
        title: "IR sample triage",
        desc: "Get a quick verdict during a live incident — no waiting on manual reverse engineering.",
      },
      {
        title: "Red team artifact analysis",
        desc: "Confirm payload behavior and TTP coverage against your test environment.",
      },
      {
        title: "Supply chain component check",
        desc: "Verdict third‑party components before deployment with consistent reporting.",
      },
    ],
    stepsHeading: "How it works",
    steps: [
      { title: "Upload", body: "Drop a file or hash. Archives are unpacked safely before analysis." },
      { title: "Static review", body: "Strings, imports, signatures, entropy, and signing status are examined." },
      { title: "Dynamic detonation", body: "Execute in an isolated sandbox. Behaviors are recorded with timestamps and artifacts." },
      { title: "Map", body: "Observed behaviors are mapped to MITRE ATT&CK techniques and tactics." },
      { title: "Conclude", body: "The Lead Agent returns verdict, score, ATT&CK map, and the full execution log." },
    ],
    sampleHeading: "Sample output",
    sampleCardTitle: "Malware verdict — ATT&CK mapped",
    sampleBody: `Verdict        Malicious — Loader → Cobalt Strike beacon
Score          9.4 / 10
Family         Bumblebee (high confidence)

ATT&CK techniques
  T1027   Obfuscated Files or Information
  T1055   Process Injection
  T1071.001  Application Layer Protocol: Web

Observed behaviors
  · Spawns rundll32.exe with suspicious DLL path
  · Beacons to 185.x.x.x every 60s (with jitter)
  · Persists via scheduled task "WindowsUpdateAssist"

Recommended actions
  · Block hash on EDR
  · Hunt the C2 IP across last 30 days of proxy logs (one-click pivot)`,
    whyHeading: "Why it matters",
    metrics: [
      { kpi: "~45 min → ~4 min", label: "Time per sample for routine triage" },
      { kpi: "ATT&CK-ready", label: "TTPs mapped automatically, not hand‑tagged" },
      { kpi: "Defensible", label: "Execution logs and artifacts included by default" },
    ],
    trustHeading: "Trust & Deploy",
    trustBullets: [
      "Sandbox runs in an isolated VPC. Samples never share tenants.",
      "Customer-controlled retention policy for samples and artifacts.",
      "Optional private deployment for sensitive environments.",
    ],
  },
  threatInvestigation: {
    docTitle: "Threat Investigation — Security Manus",
    navTitle: "Threat Investigation",
    heroEyebrow: "Use case",
    heroTitle: "From an alert or IOC, to the full attack story.",
    lead: "Hand the agent a SIEM alert, an IOC, or a question. It investigates across your stack and returns a closed-case report.",
    benefitsHeading: "How investigations start",
    benefits: [
      {
        title: "From an alert",
        desc: "Turn noisy SIEM/EDR alerts into closed cases with scoped impact and actions.",
      },
      {
        title: "From an IOC",
        desc: "Pivot one indicator across logs and endpoints to build the full attack graph.",
      },
      {
        title: "From a question",
        desc: "Ask in plain language. Get cited, executable answers and tailored runbooks.",
      },
      {
        title: "Closed-case reports",
        desc: "Verdict, attack timeline, scoped impact, and containment — cited end to end.",
      },
    ],
    stepsHeading: "How it works",
    steps: [
      {
        title: "Receive",
        body: "Start from an alert, an IOC, or a plain‑language question (UI, API, or SIEM webhook).",
      },
      { title: "Plan", body: "The Lead Agent decides which SubAgents to dispatch and what evidence to collect." },
      {
        title: "Pivot",
        body: "Tracing SubAgent expands across identity, endpoint, proxy, DNS, and mail to scope impact.",
      },
      {
        title: "Evidence",
        body: "Findings are bundled with timestamps, sources, and artifacts — ready for review.",
      },
      { title: "Conclude", body: "You get a verdict, attack timeline, scoped impact, and a containment plan." },
    ],
    sampleHeading: "Sample output",
    sampleCardTitle: "Investigation report — scoped, cited, actionable",
    sampleBody: `From an alert (Okta) — "Impossible travel login"
Verdict     Confirmed account takeover

Attack timeline
  14:02   Successful login from VPS in NL
  14:04   MFA push approved (user later denied)
  14:09   OAuth grant created for "mail backup" app
  14:12   1.2 GB mailbox content exfiltrated via Graph API

Scope       1 user · 2 OAuth grants · 1 forwarding rule
Actions     Revoke sessions, remove forwarding rule,
            force password + MFA reset, hunt VPS IP across 14d

---

From an IOC — 185.x.x.x

Hits across stack
  Proxy   3 internal hosts beaconed in last 7 days
  DNS     14 lookups of mal-c2[.]xyz → this IP
  EDR     1 host: rundll32.exe beaconing

Impact      1 confirmed infected host (HOSTNAME)
            2 hosts with probable contact
Actions     Isolate host on EDR · block IP/domain
            at perimeter · pull memory image

---

From a question
Q   "Are we exposed to CVE-2024-XXXX in our Confluence stack?"

A   Plain answer with cited references (NVD, vendor advisory)
    Step-by-step runbook tailored to your stack
    One-click hunt across asset inventory
    Suggested ticket draft for the asset owner`,
    whyHeading: "Why it matters",
    metrics: [
      { kpi: "Hours → minutes", label: "Mean time to close routine investigations" },
      { kpi: "Full scope", label: "Cross-log pivots happen by default" },
      { kpi: "Reusable", label: "Every case becomes a cited runbook" },
    ],
    trustHeading: "Trust & Deploy",
    trustBullets: [
      "Read-only connectors by default. Write actions require explicit approval.",
      "All agent actions are logged and replayable for audit and review.",
      "On-prem / VPC deployment for regulated environments.",
    ],
  },
} as const;
