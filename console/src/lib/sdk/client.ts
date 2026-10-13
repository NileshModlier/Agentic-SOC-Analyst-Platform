import type {
  Alert,
  AlertHit,
  CaseDetail,
  CaseRecord,
  Connector,
  DeadLetter,
  Draft,
  DraftSummary,
  Entity,
  EventDetail,
  EvidenceDetail,
  Facets,
  Finding,
  Investigation,
  InvestigationDetail,
  Page,
  Publication,
  QueryParams,
  Run,
  RunSummary,
} from "@/lib/sdk/types";

export class ApiClientError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function search(params: QueryParams = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    query.set(key, String(value));
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

export async function platform<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/platform/${path.replace(/^\//, "")}`, {
    ...init,
    headers: {
      accept: "application/json",
      ...(init?.body ? { "content-type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  const text = await response.text();
  const body = text ? (JSON.parse(text) as { error?: { code?: string; message?: string } }) : null;
  if (!response.ok) {
    throw new ApiClientError(
      response.status,
      body?.error?.code || "request_failed",
      body?.error?.message || "The platform request failed.",
    );
  }
  return body as T;
}

export const sdk = {
  searchAlerts: (params: QueryParams) => platform<Page<AlertHit>>(`api/v1/search/alerts${search(params)}`),
  getAlert: (id: string) => platform<Alert>(`api/v1/alerts/${id}`),
  searchEvents: (params: QueryParams) => platform<Page<Record<string, unknown>>>(`api/v1/search/events${search(params)}`),
  getEvent: (id: string) => platform<EventDetail>(`api/v1/events/${id}`),
  facets: (params: QueryParams = {}) => platform<Facets>(`api/v1/search/facets${search(params)}`),
  searchEntities: (params: QueryParams) => platform<Page<Entity>>(`api/v1/search/entities${search(params)}`),
  getEntity: (id: string) => platform<Entity>(`api/v1/search/entities/${id}`),
  listCases: (params: QueryParams) => platform<Page<CaseRecord>>(`api/v1/cases${search(params)}`),
  getCase: (id: string) => platform<CaseDetail>(`api/v1/cases/${id}`),
  listInvestigations: (params: QueryParams) =>
    platform<Page<Investigation>>(`api/v1/investigations${search(params)}`),
  getInvestigation: (id: string) => platform<InvestigationDetail>(`api/v1/investigations/${id}`),
  getFinding: (id: string) => platform<Finding>(`api/v1/findings/${id}`),
  getEvidence: (id: string) => platform<EvidenceDetail>(`api/v1/evidence/${id}`),
  listRuns: (params: QueryParams) => platform<Page<RunSummary>>(`api/v1/agent/runs${search(params)}`),
  getRun: (id: string) => platform<Run>(`api/v1/agent/runs/${id}`),
  startRun: (body: { alert_id?: string; question?: string }) =>
    platform<Run>("api/v1/agent/runs", { method: "POST", body: JSON.stringify(body) }),
  listDrafts: (params: QueryParams) => platform<Page<DraftSummary>>(`api/v1/agent/drafts${search(params)}`),
  getDraft: (id: string) => platform<Draft>(`api/v1/agent/drafts/${id}`),
  decide: (id: string, body: { decision: "approved" | "rejected"; note?: string; intent?: "request_changes" }) =>
    platform<Draft>(`api/v1/agent/drafts/${id}/decisions`, { method: "POST", body: JSON.stringify(body) }),
  connectors: () => platform<{ data: Connector[] }>("api/v1/operations/connectors"),
  deadLetters: (params: QueryParams) => platform<Page<DeadLetter>>(`api/v1/operations/dead-letters${search(params)}`),
  publications: (params: QueryParams) =>
    platform<Page<Publication>>(`api/v1/operations/publications${search(params)}`),
};
