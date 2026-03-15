import {
  buildReportUrl,
  filterVisibleTemplates,
  getAuthHeaders,
  inferRole,
  paginateTemplates,
  type DashboardTemplate
} from "./dashboard";

describe("dashboard helpers", () => {
  test("inferRole resolves known roles", () => {
    expect(inferRole("clinician")).toBe("clinician");
    expect(inferRole("admin")).toBe("admin");
    expect(inferRole("other")).toBe("researcher");
  });

  test("getAuthHeaders returns required headers", () => {
    expect(getAuthHeaders("tkn", "tenant-a")).toEqual({
      Authorization: "Bearer tkn",
      "x-tenant-id": "tenant-a",
      "Content-Type": "application/json"
    });
  });

  test("buildReportUrl encodes participant filter when provided", () => {
    const url = buildReportUrl("http://localhost:8000", "study-a", 2, 25, "p-1");
    expect(url).toContain("page=2");
    expect(url).toContain("page_size=25");
    expect(url).toContain("participant_filter=p-1");
  });

  const templates: DashboardTemplate[] = [
    { id: "a", title: "A", chartType: "bar", dataSource: "r", roles: ["researcher", "admin"] },
    { id: "b", title: "B", chartType: "line", dataSource: "r", roles: ["clinician"] },
    { id: "c", title: "C", chartType: "pie", dataSource: "r", roles: ["admin"] }
  ];

  test("filterVisibleTemplates applies role filtering", () => {
    expect(filterVisibleTemplates(templates, "researcher").map((x) => x.id)).toEqual(["a"]);
    expect(filterVisibleTemplates(templates, "admin").map((x) => x.id)).toEqual(["a", "c"]);
  });

  for (let page = 1; page <= 110; page += 1) {
    test(`paginateTemplates deterministic case ${page}`, () => {
      const items = Array.from({ length: 1000 }, (_, i) => i + 1);
      const pageSize = 5;
      const paged = paginateTemplates(items, page, pageSize);
      const start = (Math.max(1, page) - 1) * pageSize + 1;
      const expected = items.slice(start - 1, start - 1 + pageSize);
      expect(paged).toEqual(expected);
    });
  }
});
