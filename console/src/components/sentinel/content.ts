export type GuideSection = {
  title: string;
  body: string;
};

export type GuideLink = {
  href: string;
  label: string;
  access?: "review" | "admin";
};

export type GuidePage = {
  id: string;
  title: string;
  summary: string;
  sections: GuideSection[];
  links: GuideLink[];
};

const DASHBOARD: GuidePage = {
  id: "dashboard",
  title: "Dashboard",
  summary: "A first look at this tenant. Counts on the cards come from the current page of records, up to 100 rows. A plus sign means another page exists. Event facets are complete counts.",
  sections: [
    {
      title: "Widgets",
      body: "Open alerts are detections whose status is new. High severity alerts add the high and critical cards. Active cases are open or investigating. Pending reviews are drafts waiting for a person. Investigation throughput counts investigations that are open or active on this page.",
    },
    {
      title: "Alert counts",
      body: "The alert cards and the alert trend use the latest alert page, so they are a working set rather than a warehouse total. Severity distribution and entity activity use event facets, which count the whole event corpus for this tenant.",
    },
    {
      title: "Investigation throughput",
      body: "The throughput chart groups investigations on this page by the day they were opened. It shows how work arrived. It is not a forecast, and it does not mean an agent has finished those investigations.",
    },
  ],
  links: [
    { href: "/alerts", label: "Open the alert explorer" },
    { href: "/investigations", label: "Open investigations" },
    { href: "/reviews", label: "Open the review queue", access: "review" },
  ],
};

const ALERTS: GuidePage = {
  id: "alerts",
  title: "Alerts",
  summary: "Search detections stored for this tenant. This page does not change alert status.",
  sections: [
    {
      title: "Severity",
      body: "Critical, high, medium, low, informational, and unknown describe the stored detection. Severity is not a verdict that the activity is malicious.",
    },
    {
      title: "Status",
      body: "New, in review, closed, and suppressed are the workflow states already stored on the alert. Filtering by status only changes which rows you see.",
    },
    {
      title: "Filtering",
      body: "Search text, severity, source, status, and sort apply to the alert index. Changing a filter returns you to the first page. The default sort is detection time, newest first.",
    },
    {
      title: "Facets",
      body: "Severity, source, event type, host, and user count the event corpus. Each facet leaves out its own filter and keeps the rest of the query. Choosing a host or user opens that value in the entity explorer.",
    },
  ],
  links: [
    { href: "/entities", label: "Browse entities" },
    { href: "/agent-workspace", label: "Open the agent workspace" },
  ],
};

const ALERT_DETAIL: GuidePage = {
  id: "alert-detail",
  title: "Alert detail",
  summary: "One detection and the canonical event linked to it. Running an investigation drafts cited claims. It does not change this alert.",
  sections: [
    {
      title: "Evidence",
      body: "The detection panel shows the stored title, rule, vendor, and description. The linked event is the projected canonical record: message, class, host, and user. Raw source bytes are not shown here.",
    },
    {
      title: "Investigation workflow",
      body: "Run investigation opens the agent workspace with this alert id. Supervisor, triage, entity, threat, and reporting run locally and store a draft. A person still has to approve that draft.",
    },
    {
      title: "Linked entities",
      body: "Host and user on the linked event are catalog values, not a separate graph. Search them from Entities. Technique ids are the ATT&CK identifiers stored on the alert. If none were stored, the page says so.",
    },
  ],
  links: [
    { href: "/alerts", label: "Back to alerts" },
    { href: "/entities", label: "Browse entities" },
    { href: "/agent-workspace", label: "Open the agent workspace" },
  ],
};

const CASES: GuidePage = {
  id: "cases",
  title: "Cases",
  summary: "Cases are incident containers already stored for this tenant. This console reads them. It does not move a case from one status to another.",
  sections: [
    {
      title: "Case lifecycle",
      body: "Stored statuses are open, investigating, contained, recovered, and closed. The list filter uses those values. Active work on the dashboard is the open and investigating set.",
    },
    {
      title: "Investigation status",
      body: "A case can list linked investigations. Each investigation has its own status, separate from the case. Opening a case shows those investigations and any findings. Approving an investigation draft does not create a finding.",
    },
  ],
  links: [
    { href: "/investigations", label: "Open investigations" },
    { href: "/alerts", label: "Open alerts" },
  ],
};

const INVESTIGATIONS: GuidePage = {
  id: "investigations",
  title: "Investigations",
  summary: "An investigation is a unit of analysis stored on the platform. Open one to read its timeline.",
  sections: [
    {
      title: "Timeline",
      body: "The detail timeline is ordered by time. It includes when the investigation opened, each linked alert, agent runs for those alerts, and the close event when one is stored.",
    },
    {
      title: "Evidence relationships",
      body: "Linked alerts are the evidence relationship you can navigate. The timeline is those stored records. It is not a separate evidence graph, and a draft approval does not write a new finding onto the investigation.",
    },
  ],
  links: [
    { href: "/alerts", label: "Open alerts" },
    { href: "/cases", label: "Open cases" },
    { href: "/agent-workspace", label: "Open the agent workspace" },
  ],
};

const ENTITIES: GuidePage = {
  id: "entities",
  title: "Entities",
  summary: "One catalog for values observed in events. A detail page searches alerts and events for that same value.",
  sections: [
    {
      title: "Users",
      body: "A user is an account or person string extracted from events. First seen and last seen come from those events. Related alerts are a text search for the display value.",
    },
    {
      title: "Hosts",
      body: "A host is a computer name observed on events. Facets on the alert explorer can open a host here. The row does not include a live asset inventory.",
    },
    {
      title: "Files",
      body: "A file is a path or file name stored from an event. Search matches the catalog value. It does not open file contents.",
    },
    {
      title: "Processes",
      body: "A process is the process name or command value stored from an event. Use it to see which events and alerts mention that value.",
    },
    {
      title: "IPs",
      body: "An IP is an address observed on events. The catalog row is that address plus severity and event counts. It is not a reputation lookup.",
    },
  ],
  links: [
    { href: "/alerts", label: "Open alerts" },
    { href: "/investigations", label: "Open investigations" },
  ],
};

const WORKSPACE: GuidePage = {
  id: "agent-workspace",
  title: "Agent workspace",
  summary: "Start a local investigation from an alert id or a question. The result is a cited draft. Agents are not a source of truth, and approval is always human.",
  sections: [
    {
      title: "Supervisor",
      body: "The supervisor records the plan and routes the workflow through triage, entity, threat, and reporting. It does not decide that a claim is true, and it cannot approve the draft.",
    },
    {
      title: "Triage",
      body: "Triage reads the stored alert, or searches stored events when you ask a question. Claims are rendered from those rows. If the alert is missing, the run fails instead of inventing one.",
    },
    {
      title: "Entity agent",
      body: "The entity agent looks up users, hosts, processes, files, and IP addresses already present on the related events. It uses the catalog. It does not browse the network.",
    },
    {
      title: "Threat agent",
      body: "The threat agent searches stored alerts that share a technique id already on the alert. If no technique was stored, it records that and does not look outside the platform.",
    },
    {
      title: "Reporting agent",
      body: "Reporting checks each claim against the stored record and saves a draft. A matching draft waits for a person. A mismatch is marked validation failed. No citable claim is marked insufficient evidence.",
    },
    {
      title: "Agents are not sources of truth",
      body: "A draft is a proposal. Approval records a person's decision and does not promote the draft into a finding, alert, or case. Reject and request changes are also human decisions.",
    },
  ],
  links: [
    { href: "/reviews", label: "Open the review queue", access: "review" },
    { href: "/alerts", label: "Choose an alert" },
  ],
};

const REVIEWS: GuidePage = {
  id: "reviews",
  title: "Review queue",
  summary: "A person decides a draft that is pending approval. The decision is stored. Canonical alerts, events, cases, and findings stay as they were.",
  sections: [
    {
      title: "Approve",
      body: "Approve records that you accept the cited draft. The draft is not copied into a finding, and the alert status does not change.",
    },
    {
      title: "Reject",
      body: "Reject records that you decline the draft. Add a note when the reason should stay with the decision. The draft cannot be decided twice.",
    },
    {
      title: "Request changes",
      body: "Request changes stores a rejection whose note is marked as changes requested. It is not a third workflow state. The draft leaves the pending queue.",
    },
  ],
  links: [
    { href: "/agent-workspace", label: "Open the agent workspace" },
    { href: "/alerts", label: "Open alerts" },
  ],
};

const ADMIN: GuidePage = {
  id: "admin",
  title: "Administration",
  summary: "Intake health for this tenant. Payloads, source bytes, and outbox bodies are not shown.",
  sections: [
    {
      title: "Connector health",
      body: "Each connector shows how many receipts were projected, how many were dead-lettered, and the last intake time. The sources are Sigma alerts, mock EDR alerts, and Windows events.",
    },
    {
      title: "Replay",
      body: "Replay re-projects one source record from the bytes stored at intake. Paste the source record id. The form does not accept a new payload.",
    },
    {
      title: "Dead letters",
      body: "Dead letters are parse, publish, and replay failures. The table shows stage, reason, and time. It does not show the failed bytes.",
    },
  ],
  links: [
    { href: "/dashboard", label: "Return to the dashboard" },
    { href: "/alerts", label: "Open alerts" },
  ],
};

export function guideFor(pathname: string): GuidePage {
  if (pathname.startsWith("/alerts/")) return ALERT_DETAIL;
  if (pathname.startsWith("/alerts")) return ALERTS;
  if (pathname.startsWith("/cases")) return CASES;
  if (pathname.startsWith("/investigations")) return INVESTIGATIONS;
  if (pathname.startsWith("/entities")) return ENTITIES;
  if (pathname.startsWith("/agent-workspace")) return WORKSPACE;
  if (pathname.startsWith("/reviews")) return REVIEWS;
  if (pathname.startsWith("/admin")) return ADMIN;
  return DASHBOARD;
}
