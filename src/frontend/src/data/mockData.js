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
