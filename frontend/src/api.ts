// Typed client for the DomainSentinel REST API (same-origin "/api").

export interface DomainBase {
  id: number;
  url: string;
  label: string | null;
  active: boolean;
  interval_hours: number;
  created_at: string;
  last_scan_at: string | null;
  next_scan_at: string | null;
}

export interface DomainSummary extends DomainBase {
  scan_count: number;
  last_scan_status: string | null;
  last_diff_severity: string | null;
  last_diff_changed: boolean | null;
}

export interface DnsRecords {
  available: boolean;
  hostname?: string;
  zone?: string;
  // A record type is null when its lookup failed for that scan.
  ns?: string[] | null;
  mx?: string[] | null;
  txt?: string[] | null;
  spf?: string[] | null;
  dmarc?: string[] | null;
  errors?: Record<string, string>;
  error?: string;
}

export interface Scan {
  id: number;
  domain_id: number;
  status: string;
  cf_scan_id: string | null;
  error: string | null;
  created_at: string;
  submitted_at: string | null;
  completed_at: string | null;
  final_url: string | null;
  page_title: string | null;
  verdict_malicious: boolean | null;
  dns_records: DnsRecords | null;
  has_screenshot: boolean;
  has_dom: boolean;
  has_har: boolean;
}

export interface DomDiff {
  available: boolean;
  changed: boolean;
  similarity?: number;
  added_count?: number;
  removed_count?: number;
  added_lines?: string[];
  removed_lines?: string[];
  unified?: string[];
}

export interface HarDiff {
  available: boolean;
  changed: boolean;
  added_hosts?: string[];
  removed_hosts?: string[];
  added_requests?: string[];
  removed_requests?: string[];
  status_changes?: { url: string; from: number; to: number }[];
  old_request_count?: number;
  new_request_count?: number;
}

export interface ScreenshotDiff {
  available: boolean;
  changed: boolean;
  similarity?: number;
  changed_ratio?: number;
  size_changed?: boolean;
  old_size?: number[];
  new_size?: number[];
}

export interface ResultDiff {
  available: boolean;
  changed: boolean;
  now_malicious?: boolean | null;
  verdict_change?: { from: boolean | null; to: boolean | null } | null;
  categories_added?: string[];
  technologies_added?: string[];
  technologies_removed?: string[];
  title_change?: { from: string | null; to: string | null } | null;
  final_url_change?: { from: string | null; to: string | null } | null;
  ips_added?: string[];
  ips_removed?: string[];
}

export interface DnsTypeDiff {
  available: boolean;
  added: string[];
  removed: string[];
}

export interface DnsDiff {
  available: boolean;
  changed: boolean;
  changed_types?: string[];
  records?: Record<string, DnsTypeDiff>;
  old?: Record<string, string[] | null>;
  new?: Record<string, string[] | null>;
  zone?: string;
}

export interface DiffSummary {
  changed: boolean;
  severity: string;
  signals: string[];
  screenshot: ScreenshotDiff;
  dom: DomDiff;
  har: HarDiff;
  result: ResultDiff;
  dns: DnsDiff;
}

export interface Diff {
  id: number;
  domain_id: number;
  from_scan_id: number;
  to_scan_id: number;
  created_at: string;
  changed: boolean;
  severity: string;
  summary: DiffSummary;
  has_screenshot_diff: boolean;
}

export interface DomainDetail extends DomainBase {
  scans: Scan[];
  latest_diff: Diff | null;
}

export interface AppInfo {
  version: string;
  fake_cloudflare: boolean;
  default_scan_interval_hours: number;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

const jsonHeaders = { "Content-Type": "application/json" };

export const api = {
  info: () => fetch("/api/info").then(handle<AppInfo>),
  listDomains: () => fetch("/api/domains").then(handle<DomainSummary[]>),
  getDomain: (id: number) => fetch(`/api/domains/${id}`).then(handle<DomainDetail>),
  addDomain: (body: { url: string; label?: string; interval_hours?: number; scan_now?: boolean }) =>
    fetch("/api/domains", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }).then(handle<DomainDetail>),
  deleteDomain: (id: number) => fetch(`/api/domains/${id}`, { method: "DELETE" }),
  scanDomain: (id: number) =>
    fetch(`/api/domains/${id}/scan`, { method: "POST" }).then(handle<DomainDetail>),
  listDiffs: (id: number) => fetch(`/api/domains/${id}/diffs`).then(handle<Diff[]>),
  computeDiff: (domainId: number, from: number, to: number) =>
    fetch(`/api/domains/${domainId}/diff?from_scan=${from}&to_scan=${to}`, {
      method: "POST",
    }).then(handle<Diff>),
  scanArtifactUrl: (scanId: number, kind: "screenshot" | "dom" | "har") =>
    `/api/scans/${scanId}/${kind}`,
  diffScreenshotUrl: (diffId: number) => `/api/diffs/${diffId}/screenshot`,
};
