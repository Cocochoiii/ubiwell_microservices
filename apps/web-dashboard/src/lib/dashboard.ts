export type DashboardTemplate = {
  id: string;
  title: string;
  chartType: string;
  dataSource: string;
  roles: string[];
};

export function inferRole(username: string): string {
  if (username === "clinician") return "clinician";
  if (username === "admin") return "admin";
  return "researcher";
}

export function getAuthHeaders(token: string, tenantId: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    "x-tenant-id": tenantId,
    "Content-Type": "application/json"
  };
}

export function filterVisibleTemplates(templates: DashboardTemplate[], role: string): DashboardTemplate[] {
  return templates.filter((template) => template.roles.includes(role));
}

export function paginateTemplates<T>(items: T[], page: number, pageSize: number): T[] {
  const safePage = Math.max(1, page);
  const start = (safePage - 1) * pageSize;
  return items.slice(start, start + pageSize);
}

export function buildReportUrl(
  apiBaseUrl: string,
  studyId: string,
  page: number,
  pageSize: number,
  participantFilter: string
): string {
  const url = new URL(`${apiBaseUrl}/reports/studies/${studyId}`);
  url.searchParams.set("page", String(page));
  url.searchParams.set("page_size", String(pageSize));
  if (participantFilter) {
    url.searchParams.set("participant_filter", participantFilter);
  }
  return url.toString();
}
