// ---------------------------------------------------------------------------
// Mock/placeholder data that mirrors the provided design mockups exactly.
// These screens have NO backend endpoints yet (only /auth exists), so the data
// lives here. When the backend adds the routes listed in BACKEND_INTEGRATION.md,
// swap these constants for real fetch() calls.
// ---------------------------------------------------------------------------

// ---- Dashboard ----
export const dashboardStats = [
  { key: 'drives', label: 'Active Drives', value: '12', footnote: '+2 this week' },
  { key: 'cvs', label: 'CVs Processed', value: '4,892', footnote: '98% success rate' },
  { key: 'insights', label: 'AI Insights Gen', value: '14.2k', footnote: 'Across 4 models' },
]

export const ingestionQueue = [
  {
    id: 'q1',
    title: 'Frontend Engineering Batch',
    source: 'ZIP Upload',
    status: 'processing',
    statusLabel: 'Processing',
    detail: 'Processing 45 of 58 CVs',
    progress: 78,
    color: 'indigo',
  },
  {
    id: 'q2',
    title: 'Product Manager Candidates',
    source: 'Google Forms Integration',
    status: 'completed',
    statusLabel: 'Completed',
    detail: 'Added 12 new candidates. 3 duplicates prevented.',
    progress: 100,
    color: 'green',
  },
  {
    id: 'q3',
    title: 'Data Science Inbox Sync',
    source: 'Email Sync',
    status: 'error',
    statusLabel: 'Error',
    detail: 'Failed to parse 2 attachments. Auto-retrying...',
    progress: 35,
    color: 'red',
  },
]

export const systemAlerts = [
  {
    id: 'a1',
    level: 'success',
    text: 'Duplicate Prevention active: 14 identical CVs skipped today.',
  },
  {
    id: 'a2',
    level: 'warning',
    text: 'Rate limit approaching on OpenAI API (85%). Consider queuing non-urgent processing.',
  },
  {
    id: 'a3',
    level: 'error',
    text: "Missing permissions for shared inbox 'careers@company.com'. Check Admin Gateway.",
  },
]

// ---- Shortlisting ----
// Keyed by campaign so the "Frontend Eng | Product Mgr" switch works.
export const candidatesByCampaign = {
  'Frontend Eng': [
    {
      rank: 1,
      id: 'eleanor-rigby',
      name: 'Eleanor Rigby',
      title: 'Senior Frontend Engineer',
      years: 8,
      isNew: true,
      score: 98,
      skills: ['React', 'TypeScript', 'GraphQL', 'Team Leadership'],
    },
    {
      rank: 2,
      id: 'marcus-chen',
      name: 'Marcus Chen',
      title: 'Frontend Developer',
      years: 5,
      isNew: false,
      score: 85,
      skills: ['React', 'JavaScript', 'Redux', 'Tailwind CSS'],
    },
    {
      rank: 3,
      id: 'sarah-jenkins',
      name: 'Sarah Jenkins',
      title: 'Fullstack Engineer',
      years: 6,
      isNew: true,
      score: 72,
      skills: ['Angular', 'Node.js', 'PostgreSQL', 'AWS'],
    },
  ],
  'Product Mgr': [
    {
      rank: 1,
      id: 'priya-nair',
      name: 'Priya Nair',
      title: 'Senior Product Manager',
      years: 9,
      isNew: true,
      score: 94,
      skills: ['Roadmapping', 'Analytics', 'A/B Testing', 'Leadership'],
    },
    {
      rank: 2,
      id: 'david-okoro',
      name: 'David Okoro',
      title: 'Product Manager',
      years: 6,
      isNew: false,
      score: 81,
      skills: ['Agile', 'SQL', 'User Research', 'Figma'],
    },
  ],
}

export const shortlistFilters = ['Exp: 5+ years', 'Skills: React']
export const totalCandidates = 58

// ---- CV Analysis (Eleanor Rigby) ----
export const cvAnalysis = {
  fileName: 'Eleanor_Rigby_CV_2023.pdf',
  processedBy: 'Processed by HireWise • Version 2.1',
  matchScore: 98,
  processedIn: '1.2s',
  resume: {
    name: 'Eleanor Rigby',
    headline: 'Senior Frontend Engineer | San Francisco, CA | eleanor@example.com',
    experience: [
      {
        role: 'Tech Lead, Frontend',
        company: 'Acme Corp',
        period: '2019 - Present',
        bullets: [
          'Led a team of 6 engineers to rebuild the core SaaS platform using React, TypeScript, and GraphQL.',
          'Improved application load time by 40% through code splitting and strategic caching.',
          'Established comprehensive frontend testing standards using Jest and Cypress.',
        ],
      },
      {
        role: 'Senior Frontend Developer',
        company: 'Globex Inc',
        period: '2015 - 2019',
        bullets: [
          'Architected scalable component libraries used across 4 different product lines.',
          'Mentored junior developers and ran bi-weekly tech sharing sessions.',
        ],
      },
    ],
    education: [
      {
        degree: 'B.S. Computer Science',
        school: 'University of Technology',
        period: '2011 - 2015',
      },
    ],
  },
  profile: {
    totalExperience: '8 years',
    highestEducation: 'B.S. Computer Science',
    verifiedSkills: ['React', 'TypeScript', 'GraphQL', 'Leadership'],
  },
  deductions: [
    {
      title: 'Strong Leadership Experience',
      evidence:
        'Candidate has explicitly led a team of 6 engineers and established testing standards.',
    },
    {
      title: 'Deep React/TS Ecosystem Knowledge',
      evidence:
        'Mentions rebuilding core SaaS platform with required stack. Also notes architecture experience.',
    },
  ],
  flags: [
    {
      title: 'No explicit mention of Next.js',
      detail:
        'The job description highly preferred Next.js experience. While React/TS is strong, Next.js is not found in the text.',
    },
  ],
}

// ---------------------------------------------------------------------------
// Project-based workflow (frontend-only mock).
// A "project" == a Job Description campaign. Created on the Dashboard, listed as
// cards, opened into a detail view, and shortlisted against. All of this lives
// in client state (ProjectContext) — no backend wiring yet.
// ---------------------------------------------------------------------------

// Heuristic: pull a likely job title out of the free-text description.
export function deriveTitle(text) {
  if (!text || !text.trim()) return 'Untitled Role'
  const roles =
    /\b((?:senior|junior|lead|principal|staff)?\s*(?:frontend|front-end|backend|back-end|fullstack|full-stack|software|product|data|ml|devops|mobile|ios|android|qa|security|platform|cloud)?\s*(?:engineer|developer|manager|designer|scientist|analyst|architect|lead))\b/i
  const m = text.match(roles)
  if (m) {
    return m[1]
      .trim()
      .replace(/\s+/g, ' ')
      .replace(/\b\w/g, (ch) => ch.toUpperCase())
  }
  // Fallback: first few words.
  return text.trim().split(/\s+/).slice(0, 4).join(' ')
}

// Turn the natural-language brief into a structured, "AI-generated" JD.
export function generateJD(text) {
  const title = deriveTitle(text)
  const brief = (text || '').trim() || 'No description provided.'
  return {
    title,
    markdown: `# ${title}

## Role Overview
${brief}

## Key Responsibilities
- Own delivery of high-impact features end to end.
- Collaborate cross-functionally with design, product, and engineering.
- Mentor teammates and raise the bar on quality and best practices.
- Drive technical decisions and document architectural trade-offs.

## Required Qualifications
- Proven track record in a similar role.
- Strong fundamentals and hands-on expertise with the core stack.
- Excellent communication and collaboration skills.

## Nice to Have
- Experience leading or mentoring a team.
- Exposure to scaling systems and performance optimization.

## Scoring Matrix (auto-generated)
| Criteria | Weight |
| --- | --- |
| Core technical skills | 35% |
| Relevant experience | 30% |
| Leadership & collaboration | 20% |
| Culture & communication | 15% |`,
  }
}

// Build a full "intelligence brief" analysis from a lightweight candidate.
// Eleanor reuses the rich cvAnalysis above; everyone else gets a derived brief.
function buildAnalysis(c) {
  if (c.id === 'eleanor-rigby') {
    return {
      matchScore: cvAnalysis.matchScore,
      processedIn: cvAnalysis.processedIn,
      fileName: cvAnalysis.fileName,
      resume: cvAnalysis.resume,
      profile: cvAnalysis.profile,
      // `sources` = the résumé bullet keys (exp-<job>-<bullet>) each deduction
      // cites, so hovering a deduction highlights the evidence in the CV.
      deductions: [
        { ...cvAnalysis.deductions[0], sources: ['exp-0-0', 'exp-0-2'] },
        { ...cvAnalysis.deductions[1], sources: ['exp-0-0', 'exp-1-0'] },
      ],
      flags: cvAnalysis.flags,
    }
  }
  return {
    matchScore: c.score,
    processedIn: '1.4s',
    fileName: `${c.name.replace(/\s+/g, '_')}_CV.pdf`,
    resume: {
      name: c.name,
      headline: `${c.title} | ${c.years} years experience`,
      experience: [
        {
          role: c.title,
          company: 'Current Company',
          period: 'Recent',
          bullets: [
            `Worked extensively with ${c.skills.slice(0, 2).join(' and ')}.`,
            `${c.years} years of hands-on experience in the field.`,
          ],
        },
      ],
      education: [
        {
          degree: 'B.S. relevant field',
          school: 'University',
          period: '—',
        },
      ],
    },
    profile: {
      totalExperience: `${c.years} years`,
      highestEducation: 'B.S.',
      verifiedSkills: c.skills,
    },
    deductions: [
      {
        title: 'Relevant Technical Background',
        evidence: `Candidate lists ${c.skills.join(', ')} and ${c.years} years of experience.`,
        sources: ['exp-0-0', 'exp-0-1'],
      },
    ],
    flags:
      c.score < 80
        ? [
            {
              title: 'Partial skill match',
              detail:
                'Some preferred skills from the job description were not clearly found in the CV.',
            },
          ]
        : [],
  }
}

// A fresh, independent copy of the seed candidate set for a new project, with
// override-tracking fields initialized. Each project gets its own array so
// overrides on one project never bleed into another.
export function makeSeedCandidates() {
  const base = [
    {
      id: 'eleanor-rigby',
      name: 'Eleanor Rigby',
      title: 'Senior Frontend Engineer',
      years: 8,
      isNew: true,
      score: 98,
      skills: ['React', 'TypeScript', 'GraphQL', 'Team Leadership'],
    },
    {
      id: 'marcus-chen',
      name: 'Marcus Chen',
      title: 'Frontend Developer',
      years: 5,
      isNew: false,
      score: 85,
      skills: ['React', 'JavaScript', 'Redux', 'Tailwind CSS'],
    },
    {
      id: 'sarah-jenkins',
      name: 'Sarah Jenkins',
      title: 'Fullstack Engineer',
      years: 6,
      isNew: true,
      score: 72,
      skills: ['Angular', 'Node.js', 'PostgreSQL', 'AWS'],
    },
    {
      id: 'david-okoro',
      name: 'David Okoro',
      title: 'Software Engineer',
      years: 4,
      isNew: false,
      score: 68,
      skills: ['Vue', 'JavaScript', 'CSS', 'REST'],
    },
  ]
  return base.map((c) => ({
    ...c,
    aiScore: c.score, // original AI score, preserved even after override
    overridden: false,
    shortlisted: false,
    editHistory: [], // { field, oldValue, newValue, editor, timestamp }
    analysis: buildAnalysis(c),
  }))
}

// ---- Admin Gateway: Agent Monitor ----
export const adminStats = {
  systemStatus: 'Operational',
  apiCalls: '24.5k',
  apiLimit: '50k limit',
  activeAgents: 4,
  errorRate: '0.42%',
}

// 24-hour LLM tool invocation series (one point every 2h). Limit line = 1000.
export const llmInvocations = [
  { t: '00:00', v: 120 },
  { t: '02:00', v: 110 },
  { t: '04:00', v: 100 },
  { t: '06:00', v: 260 },
  { t: '08:00', v: 540 },
  { t: '10:00', v: 820 },
  { t: '12:00', v: 900 },
  { t: '14:00', v: 880 },
  { t: '16:00', v: 840 },
  { t: '18:00', v: 540 },
  { t: '20:00', v: 300 },
  { t: '22:00', v: 200 },
  { t: '24:00', v: 170 },
]
export const llmLimit = 1000

export const errorLogs = [
  { label: 'Rate Limit', value: 100 },
  { label: 'Parsing Fail', value: 62 },
  { label: 'Auth Error', value: 24 },
  { label: 'Timeout', value: 30 },
]

// ---- Admin Gateway: Access Control (RBAC) ----
export const rbacRoles = [
  { key: 'admin', name: 'System Admin', subtitle: 'Full Access', icon: 'shield' },
  { key: 'hr', name: 'HR Manager', subtitle: 'Campaigns & Review', icon: 'users' },
  { key: 'recruiter', name: 'Recruiter', subtitle: 'View Only', icon: 'users' },
]

export const rbacPermissions = [
  {
    key: 'campaigns',
    label: 'Create/Edit Campaigns',
    sub: 'Modify Job Descriptions and settings',
    values: { admin: true, hr: true, recruiter: false },
  },
  {
    key: 'ingestion',
    label: 'Configure Ingestion Channels',
    sub: 'Link Google Forms, sync emails',
    values: { admin: true, hr: true, recruiter: false },
  },
  {
    key: 'pii',
    label: 'View Candidate PII',
    sub: 'Access names, contact info on CVs',
    values: { admin: true, hr: true, recruiter: true },
  },
  {
    key: 'override',
    label: 'Override AI Deductions',
    sub: 'Manually edit extracted skills/experience',
    values: { admin: true, hr: true, recruiter: false },
  },
  {
    key: 'agents',
    label: 'Manage AI Agents',
    sub: 'Start/stop agents, view API keys',
    values: { admin: true, hr: false, recruiter: false },
  },
  {
    key: 'settings',
    label: 'Modify System Settings',
    sub: 'Change rate limits, webhook URLs',
    values: { admin: true, hr: false, recruiter: false },
  },
]
