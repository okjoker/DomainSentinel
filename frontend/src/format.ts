// Small presentation helpers shared across pages.

// Timestamps within this many seconds of "now" in the future are treated as
// clock skew and shown as "just now" rather than "in the future".
const CLOCK_SKEW_TOLERANCE_S = 120;

export function timeAgo(value: string | null): string {
  if (!value) return "never";
  // Backend timestamps are naive UTC; treat them as UTC.
  const iso = value.endsWith("Z") || value.includes("+") ? value : `${value}Z`;
  const then = new Date(iso).getTime();
  const seconds = Math.round((Date.now() - then) / 1000);
  if (Number.isNaN(seconds)) return value;
  // Tolerate small client/server clock skew (common with VMs/WSL) so a
  // just-created item doesn't render as "in the future". Only flag timestamps
  // that are clearly ahead — that signals a genuinely wrong clock.
  if (seconds < -CLOCK_SKEW_TOLERANCE_S) return "in the future";
  if (seconds < 0) return "just now";
  const units: [number, string][] = [
    [60, "s"],
    [60, "m"],
    [24, "h"],
    [7, "d"],
    [4.345, "w"],
    [12, "mo"],
    [Number.POSITIVE_INFINITY, "y"],
  ];
  let amount = seconds;
  let unit = "s";
  for (const [step, label] of units) {
    if (amount < step) {
      unit = label;
      break;
    }
    amount = amount / step;
    unit = label;
  }
  return `${Math.floor(amount)}${unit} ago`;
}

export const SEVERITY_STYLES: Record<string, string> = {
  none: "bg-slate-700/50 text-slate-300 border-slate-600",
  low: "bg-sky-900/40 text-sky-300 border-sky-700",
  medium: "bg-amber-900/40 text-amber-300 border-amber-700",
  high: "bg-red-900/50 text-red-300 border-red-700",
};

export const STATUS_STYLES: Record<string, string> = {
  QUEUED: "bg-slate-700/50 text-slate-300 border-slate-600",
  SUBMITTED: "bg-indigo-900/40 text-indigo-300 border-indigo-700",
  FETCHING: "bg-indigo-900/40 text-indigo-300 border-indigo-700",
  COMPLETED: "bg-emerald-900/40 text-emerald-300 border-emerald-700",
  FAILED: "bg-red-900/50 text-red-300 border-red-700",
};

export const SIGNAL_LABELS: Record<string, string> = {
  verdict_became_malicious: "Flagged malicious",
  verdict_changed: "Verdict changed",
  new_threat_categories: "New threat categories",
  new_external_hosts: "New external hosts",
  removed_hosts: "Hosts removed",
  request_status_changes: "Request status changes",
  technology_changes: "Technology changes",
  final_url_changed: "Final URL changed",
  dom_changed: "DOM changed",
  visual_changed: "Visual change",
};

export function isInFlight(status: string | null): boolean {
  return status === "QUEUED" || status === "SUBMITTED" || status === "FETCHING";
}
