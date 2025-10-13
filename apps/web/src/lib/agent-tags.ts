/**
 * Predefined agent tags for categorization and filtering.
 *
 * These tags help users organize and discover agents by business function.
 * Tags are organized into logical groups for better UX.
 */

export const AGENT_TAGS = {
  // Customer-facing functions
  SALES: "sales",
  MARKETING: "marketing",
  CUSTOMER_SERVICE: "customer-service",
  SUPPORT: "support",

  // Analysis & Research
  RESEARCH: "research",
  DATA_ANALYSIS: "data-analysis",
  REPORTING: "reporting",

  // Operations & Management
  OPERATIONS: "operations",
  PROJECT_MANAGEMENT: "project-management",
  AUTOMATION: "automation",
  WORKFLOW: "workflow",

  // Business Functions
  FINANCE: "finance",
  HR: "hr",
  LEGAL: "legal",
  COMPLIANCE: "compliance",

  // Content & Communication
  CONTENT_CREATION: "content-creation",
  COMMUNICATION: "communication",
  DOCUMENTATION: "documentation",
  WRITING: "writing",

  // Technical & Development
  DEVELOPMENT: "development",
  SECURITY: "security",

  // General
  PRODUCTIVITY: "productivity",
  STRATEGY: "strategy",
  GENERAL: "general",
} as const;

/**
 * Tag display metadata for UI rendering
 */
export interface TagMetadata {
  value: string;
  label: string;
  description: string;
  category: string;
}

/**
 * Organized tag groups with metadata for UI display
 */
export const AGENT_TAG_GROUPS: Record<string, TagMetadata[]> = {
  "Customer-Facing": [
    {
      value: AGENT_TAGS.SALES,
      label: "Sales",
      description: "Lead generation, pipeline management, customer acquisition",
      category: "Customer-Facing",
    },
    {
      value: AGENT_TAGS.MARKETING,
      label: "Marketing",
      description: "Campaigns, brand management, market research",
      category: "Customer-Facing",
    },
    {
      value: AGENT_TAGS.CUSTOMER_SERVICE,
      label: "Customer Service",
      description: "Customer support, issue resolution, satisfaction",
      category: "Customer-Facing",
    },
    {
      value: AGENT_TAGS.SUPPORT,
      label: "Support",
      description: "Technical support, troubleshooting, assistance",
      category: "Customer-Facing",
    },
  ],
  "Analysis & Insights": [
    {
      value: AGENT_TAGS.RESEARCH,
      label: "Research",
      description: "Market research, competitive analysis, insights",
      category: "Analysis & Insights",
    },
    {
      value: AGENT_TAGS.DATA_ANALYSIS,
      label: "Data Analysis",
      description: "Data processing, statistical analysis, insights",
      category: "Analysis & Insights",
    },
    {
      value: AGENT_TAGS.REPORTING,
      label: "Reporting",
      description: "Report generation, KPI tracking, summaries",
      category: "Analysis & Insights",
    },
  ],
  "Operations": [
    {
      value: AGENT_TAGS.OPERATIONS,
      label: "Operations",
      description: "Business operations, process management",
      category: "Operations",
    },
    {
      value: AGENT_TAGS.PROJECT_MANAGEMENT,
      label: "Project Management",
      description: "Planning, tracking, coordination, delivery",
      category: "Operations",
    },
    {
      value: AGENT_TAGS.AUTOMATION,
      label: "Automation",
      description: "Process automation, workflow optimization",
      category: "Operations",
    },
    {
      value: AGENT_TAGS.WORKFLOW,
      label: "Workflow",
      description: "Workflow design, integration, orchestration",
      category: "Operations",
    },
  ],
  "Business Functions": [
    {
      value: AGENT_TAGS.FINANCE,
      label: "Finance",
      description: "Financial analysis, budgeting, forecasting",
      category: "Business Functions",
    },
    {
      value: AGENT_TAGS.HR,
      label: "HR",
      description: "Human resources, recruiting, employee management",
      category: "Business Functions",
    },
    {
      value: AGENT_TAGS.LEGAL,
      label: "Legal",
      description: "Contract review, compliance, legal research",
      category: "Business Functions",
    },
    {
      value: AGENT_TAGS.COMPLIANCE,
      label: "Compliance",
      description: "Regulatory compliance, policy enforcement",
      category: "Business Functions",
    },
  ],
  "Content & Communication": [
    {
      value: AGENT_TAGS.CONTENT_CREATION,
      label: "Content Creation",
      description: "Content writing, copywriting, creative work",
      category: "Content & Communication",
    },
    {
      value: AGENT_TAGS.COMMUNICATION,
      label: "Communication",
      description: "Internal comms, messaging, coordination",
      category: "Content & Communication",
    },
    {
      value: AGENT_TAGS.DOCUMENTATION,
      label: "Documentation",
      description: "Technical docs, knowledge base, guides",
      category: "Content & Communication",
    },
    {
      value: AGENT_TAGS.WRITING,
      label: "Writing",
      description: "Business writing, editing, proofreading",
      category: "Content & Communication",
    },
  ],
  "Technical": [
    {
      value: AGENT_TAGS.DEVELOPMENT,
      label: "Development",
      description: "Software development, coding, engineering",
      category: "Technical",
    },
    {
      value: AGENT_TAGS.SECURITY,
      label: "Security",
      description: "Security audits, vulnerability assessment",
      category: "Technical",
    },
  ],
  "General": [
    {
      value: AGENT_TAGS.PRODUCTIVITY,
      label: "Productivity",
      description: "Personal productivity, task management, efficiency",
      category: "General",
    },
    {
      value: AGENT_TAGS.STRATEGY,
      label: "Strategy",
      description: "Strategic planning, decision support, analysis",
      category: "General",
    },
    {
      value: AGENT_TAGS.GENERAL,
      label: "General Purpose",
      description: "Multi-purpose agents for various tasks",
      category: "General",
    },
  ],
};

/**
 * Flat list of all available tags with metadata
 */
export const ALL_AGENT_TAGS: TagMetadata[] = Object.values(AGENT_TAG_GROUPS).flat();

/**
 * Get tag metadata by value
 */
export function getTagMetadata(tagValue: string): TagMetadata | undefined {
  return ALL_AGENT_TAGS.find((tag) => tag.value === tagValue);
}

/**
 * Get display label for a tag value
 */
export function getTagLabel(tagValue: string): string {
  const metadata = getTagMetadata(tagValue);
  return metadata?.label || tagValue;
}
