import { SEVERITY_STYLES, SIGNAL_LABELS, STATUS_STYLES } from "./format";

export function Badge({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${className}`}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string | null }) {
  const key = severity ?? "none";
  return <Badge className={SEVERITY_STYLES[key] ?? SEVERITY_STYLES.none}>{key}</Badge>;
}

export function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <Badge className={SEVERITY_STYLES.none}>no scans</Badge>;
  return <Badge className={STATUS_STYLES[status] ?? SEVERITY_STYLES.none}>{status}</Badge>;
}

export function SignalChip({ signal }: { signal: string }) {
  const critical = signal.includes("malicious") || signal.includes("threat");
  const style = critical
    ? "border-red-700 bg-red-900/40 text-red-300"
    : "border-ink-600 bg-ink-800 text-slate-300";
  return <Badge className={style}>{SIGNAL_LABELS[signal] ?? signal}</Badge>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-slate-400">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
}: {
  title: string;
  hint?: string;
}) {
  return (
    <div className="card flex flex-col items-center gap-1 px-6 py-12 text-center">
      <p className="text-slate-300">{title}</p>
      {hint && <p className="text-sm text-slate-500">{hint}</p>}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="card border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-300">
      {message}
    </div>
  );
}
