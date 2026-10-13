"use client";

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PageHeader } from "@/components/page-header";
import { SEVERITY_COLOR } from "@/components/severity";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { countLabel, dayKey, label } from "@/lib/format";
import { ApiClientError, sdk } from "@/lib/sdk/client";

const tooltip = {
  contentStyle: { background: "#0e1626", border: "1px solid #243049", fontSize: 12 },
  labelStyle: { color: "#e7eefc" },
};

function message(error: unknown) {
  return error instanceof ApiClientError ? error.message : "The dashboard could not be loaded.";
}

export function DashboardView() {
  const openAlerts = useQuery({
    queryKey: ["dashboard", "open-alerts"],
    queryFn: () => sdk.searchAlerts({ status: "new", limit: 100, sort: "event_time" }),
  });
  const high = useQuery({
    queryKey: ["dashboard", "high"],
    queryFn: () => sdk.searchAlerts({ severity: "high", limit: 100 }),
  });
  const critical = useQuery({
    queryKey: ["dashboard", "critical"],
    queryFn: () => sdk.searchAlerts({ severity: "critical", limit: 100 }),
  });
  const cases = useQuery({
    queryKey: ["dashboard", "cases"],
    queryFn: () => sdk.listCases({ limit: 100 }),
  });
  const reviews = useQuery({
    queryKey: ["dashboard", "reviews"],
    queryFn: () => sdk.listDrafts({ status: "pending_approval", limit: 100 }),
  });
  const investigations = useQuery({
    queryKey: ["dashboard", "investigations"],
    queryFn: () => sdk.listInvestigations({ limit: 100 }),
  });
  const facets = useQuery({
    queryKey: ["dashboard", "facets"],
    queryFn: () => sdk.facets(),
  });
  const trend = useQuery({
    queryKey: ["dashboard", "trend"],
    queryFn: () => sdk.searchAlerts({ limit: 100, sort: "event_time" }),
  });

  const failed = [openAlerts, high, critical, cases, reviews, investigations, facets, trend].find((query) => query.isError);
  if (failed?.isError) return <ErrorState message={message(failed.error)} onRetry={() => failed.refetch()} />;
  if ([openAlerts, high, critical, cases, reviews, investigations, facets, trend].some((query) => query.isLoading)) {
    return <LoadingBlock label="Loading dashboard" />;
  }

  const activeCases = (cases.data?.data ?? []).filter((item) => item.status === "open" || item.status === "investigating");
  const openInvestigations = (investigations.data?.data ?? []).filter(
    (item) => item.status === "open" || item.status === "active",
  );
  const trendRows = bucket(trend.data?.data.map((item) => item.detected_at) ?? []);
  const throughput = bucket(investigations.data?.data.map((item) => item.opened_at) ?? []);
  const severity = (facets.data?.severity ?? []).map((item) => ({
    name: label(item.value),
    value: item.count,
    key: item.value,
  }));
  const hosts = (facets.data?.host ?? []).map((item) => ({ name: item.value, value: item.count }));
  const caseStatus = Object.entries(
    (cases.data?.data ?? []).reduce<Record<string, number>>((counts, item) => {
      counts[item.status] = (counts[item.status] ?? 0) + 1;
      return counts;
    }, {}),
  ).map(([name, value]) => ({ name: label(name), value }));

  const widgets = [
    { href: "/alerts", label: "Open alerts", value: countLabel(openAlerts.data?.data.length ?? 0, Boolean(openAlerts.data?.page.has_more)), hint: "Status new" },
    {
      href: "/alerts",
      label: "High severity alerts",
      value: countLabel((high.data?.data.length ?? 0) + (critical.data?.data.length ?? 0), Boolean(high.data?.page.has_more || critical.data?.page.has_more)),
      hint: "High and critical",
    },
    { href: "/cases", label: "Active cases", value: countLabel(activeCases.length, Boolean(cases.data?.page.has_more)), hint: "Open and investigating" },
    { href: "/reviews", label: "Pending reviews", value: countLabel(reviews.data?.data.length ?? 0, Boolean(reviews.data?.page.has_more)), hint: "Drafts awaiting a person" },
    { href: "/investigations", label: "Investigation throughput", value: String(openInvestigations.length), hint: "Open and active in this page" },
  ];

  return (
    <div>
      <PageHeader
        title="Dashboard"
        detail="Counts come from the current tenant page, up to 100 rows. A plus means another page exists. Event facets are complete counts."
      />
      <section className="grid gap-3 md:grid-cols-5">
        {widgets.map((widget) => (
          <Link key={widget.label} href={widget.href} className="panel rounded-lg p-4 hover:border-accent/50">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{widget.label}</p>
            <p className="mt-2 font-mono text-3xl">{widget.value}</p>
            <p className="mt-1 text-xs text-muted-foreground">{widget.hint}</p>
          </Link>
        ))}
      </section>
      <section className="mt-4 grid gap-4 xl:grid-cols-2">
        <ChartCard title="Alert trends" empty={trendRows.length === 0} emptyBody="No alerts in the latest page.">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={trendRows}>
              <CartesianGrid stroke="#1e2a42" vertical={false} />
              <XAxis dataKey="day" stroke="#8ea0c2" fontSize={11} />
              <YAxis stroke="#8ea0c2" fontSize={11} allowDecimals={false} />
              <Tooltip {...tooltip} />
              <Bar dataKey="count" fill="#3dd6f5" radius={3} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Severity distribution" empty={severity.length === 0} emptyBody="The event corpus has no severity counts.">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={severity}>
              <CartesianGrid stroke="#1e2a42" vertical={false} />
              <XAxis dataKey="name" stroke="#8ea0c2" fontSize={11} />
              <YAxis stroke="#8ea0c2" fontSize={11} allowDecimals={false} />
              <Tooltip {...tooltip} />
              <Bar dataKey="value" radius={3}>
                {severity.map((item) => (
                  <Cell key={item.key} fill={SEVERITY_COLOR[item.key] || "#3dd6f5"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Entity activity" empty={hosts.length === 0} emptyBody="No hosts are present in the event corpus.">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={hosts} layout="vertical" margin={{ left: 24 }}>
              <CartesianGrid stroke="#1e2a42" horizontal={false} />
              <XAxis type="number" stroke="#8ea0c2" fontSize={11} allowDecimals={false} />
              <YAxis type="category" dataKey="name" stroke="#8ea0c2" fontSize={11} width={120} />
              <Tooltip {...tooltip} />
              <Bar dataKey="value" fill="#7c9cff" radius={3} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Case statuses" empty={caseStatus.length === 0} emptyBody="No cases are open in this tenant.">
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={caseStatus} dataKey="value" nameKey="name" innerRadius={55} outerRadius={80} stroke="#0b1220">
                {caseStatus.map((item) => (
                  <Cell key={item.name} fill={item.name === "open" ? "#3dd6f5" : "#7c9cff"} />
                ))}
              </Pie>
              <Tooltip {...tooltip} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </section>
      <div className="mt-4">
        <ChartCard title="Investigation throughput" empty={throughput.length === 0} emptyBody="No investigations have been created yet.">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={throughput}>
              <CartesianGrid stroke="#1e2a42" vertical={false} />
              <XAxis dataKey="day" stroke="#8ea0c2" fontSize={11} />
              <YAxis stroke="#8ea0c2" fontSize={11} allowDecimals={false} />
              <Tooltip {...tooltip} />
              <Bar dataKey="count" fill="#3dd68c" radius={3} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}

function bucket(values: string[]) {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(dayKey(value), (counts.get(dayKey(value)) ?? 0) + 1);
  return [...counts.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([day, count]) => ({ day, count }));
}

function ChartCard({
  title,
  empty,
  emptyBody,
  children,
}: {
  title: string;
  empty: boolean;
  emptyBody: string;
  children: ReactNode;
}) {
  return (
    <section className="panel rounded-lg p-4">
      <h2 className="mb-3 text-sm font-medium">{title}</h2>
      {empty ? <EmptyState title="Nothing to chart" body={emptyBody} /> : children}
    </section>
  );
}
