export type PageInfo = {
  limit: number;
  has_more: boolean;
  next_cursor: string | null;
};

export type Page<T> = {
  data: T[];
  page: PageInfo;
};

export type Alert = {
  id: string;
  tenant_id: string;
  canonical_event_id: string | null;
  source: string;
  external_id: string | null;
  title: string;
  description: string | null;
  severity: string;
  status: string;
  rule_id: string | null;
  rule_name: string | null;
  vendor: string | null;
  product: string | null;
  technique_ids: string[];
  tactics: string[];
  detected_at: string;
  created_at: string;
  updated_at: string;
};

export type AlertHit = {
  id: string;
  canonical_event_id: string | null;
  source: string;
  title: string;
  severity: string;
  status: string;
  rule_name: string | null;
  event_type: string | null;
  hostname: string | null;
  username: string | null;
  detected_at: string;
  created_at: string;
  headline: string | null;
};

export type EventDetail = {
  id: string;
  source: string;
  event_time: string;
  class_name: string;
  activity_name: string;
  severity: string;
  outcome: string;
  hostname: string | null;
  username: string | null;
  message: string;
  technique_ids: string[];
  document: Record<string, unknown>;
};

export type CaseRecord = {
  id: string;
  title: string;
  description: string | null;
  status: string;
  severity: string;
  assignee: string | null;
  external_ref: string | null;
  opened_at: string;
  closed_at: string | null;
};

export type CaseDetail = CaseRecord & {
  investigation_ids: string[];
  finding_ids: string[];
};

export type Investigation = {
  id: string;
  case_id: string | null;
  title: string;
  status: string;
  priority: string;
  hypothesis: string | null;
  summary: string | null;
  assignee: string | null;
  opened_at: string;
  closed_at: string | null;
};

export type InvestigationDetail = Investigation & {
  alert_ids: string[];
};

export type Finding = {
  id: string;
  case_id: string | null;
  investigation_id: string | null;
  title: string;
  summary: string | null;
  severity: string;
  confidence: number | null;
  status: string;
  disposition: string | null;
  technique_ids: string[];
  created_by: string;
  created_at: string;
};

export type Evidence = {
  id: string;
  source: string;
  evidence_type: string;
  description: string;
  content_sha256: string;
  byte_size: number;
  collected_at: string;
  collected_by: string;
};

export type EvidenceDetail = Evidence & {
  links: Array<{
    id: string;
    alert_id: string | null;
    canonical_event_id: string | null;
    finding_id: string | null;
    investigation_id: string | null;
    case_id: string | null;
    linked_by: string;
    linked_at: string;
  }>;
};

export type Entity = {
  id: string;
  entity_type: string;
  value: string;
  display_value: string;
  severity: string;
  first_seen: string;
  last_seen: string;
  event_count: number;
  headline: string | null;
};

export type FacetBucket = { value: string; count: number };

export type Facets = {
  event_type: FacetBucket[];
  severity: FacetBucket[];
  source: FacetBucket[];
  host: FacetBucket[];
  user: FacetBucket[];
};

export type Citation = { kind: string; record_id: string };

export type Claim = {
  position: number;
  template: string;
  statement: string;
  arguments: Record<string, unknown>;
  citations: Citation[];
};

export type Approval = {
  decision: "approved" | "rejected";
  actor: string;
  note: string | null;
  created_at: string;
};

export type Draft = {
  id: string;
  run_id: string;
  status: string;
  title: string;
  summary: string;
  severity: string;
  source_of_truth: false;
  notice: string;
  claims: Claim[];
  approval: Approval | null;
  created_at: string;
  updated_at: string;
};

export type DraftSummary = {
  id: string;
  run_id: string;
  status: string;
  title: string;
  summary: string;
  severity: string;
  source_of_truth: false;
  approval: Approval | null;
  created_at: string;
  updated_at: string;
};

export type Memory = {
  sequence: number;
  agent: string;
  kind: string;
  payload: Record<string, unknown>;
};

export type Run = {
  id: string;
  alert_id: string | null;
  question: string | null;
  status: string;
  error_code: string | null;
  error_message: string | null;
  requested_by: string;
  draft: Draft | null;
  memory: Memory[];
  created_at: string;
  finished_at: string | null;
};

export type RunSummary = {
  id: string;
  alert_id: string | null;
  question: string | null;
  status: string;
  error_code: string | null;
  error_message: string | null;
  requested_by: string;
  draft_id: string | null;
  draft_status: string | null;
  draft_title: string | null;
  draft_severity: string | null;
  created_at: string;
  finished_at: string | null;
};

export type Connector = {
  source: string;
  label: string;
  projected: number;
  dead_lettered: number;
  last_received_at: string | null;
};

export type DeadLetter = {
  id: string;
  source_record_id: string | null;
  outbox_event_id: string | null;
  stage: string;
  reason_code: string;
  error_message: string;
  attempt_count: number;
  payload_sha256: string | null;
  created_at: string;
  resolved_at: string | null;
};

export type Publication = {
  id: string;
  aggregate_type: string;
  aggregate_id: string;
  event_type: string;
  status: string;
  attempts: number;
  last_error: string | null;
  created_at: string;
  published_at: string | null;
};

export type QueryParams = Record<string, string | number | boolean | undefined | null>;
