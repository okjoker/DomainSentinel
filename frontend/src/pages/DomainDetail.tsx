import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, type DnsRecords, type Scan } from "../api";
import { DNS_TYPE_LABELS } from "../components/diffPanels";
import { isInFlight, timeAgo } from "../format";
import { Badge, EmptyState, ErrorState, SeverityBadge, SignalChip, Spinner, StatusBadge } from "../ui";

export default function DomainDetail() {
  const { id } = useParams();
  const domainId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["domain", domainId],
    queryFn: () => api.getDomain(domainId),
    refetchInterval: (query) =>
      (query.state.data?.scans ?? []).some((s) => isInFlight(s.status)) ? 2500 : false,
  });

  const scanMutation = useMutation({
    mutationFn: () => api.scanDomain(domainId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["domain", domainId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteDomain(domainId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      navigate("/");
    },
  });

  if (isLoading) return <Spinner label="Loading domain…" />;
  if (isError) return <ErrorState error={error} />;
  if (!data) return null;

  const completed = data.scans.filter((s) => s.status === "COMPLETED");
  const latest = data.latest_diff;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to="/" className="text-xs text-sky-400 hover:underline">
            ← all domains
          </Link>
          <h1 className="mt-1 truncate text-xl font-semibold text-white">
            {data.label || data.url}
          </h1>
          <a
            href={data.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-slate-400 hover:text-sky-400"
          >
            {data.url}
          </a>
          <div className="mt-1 text-xs text-slate-500">
            Last scanned {timeAgo(data.last_scan_at)} · every {data.interval_hours}h ·{" "}
            {data.active ? "active" : "paused"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-primary"
            onClick={() => scanMutation.mutate()}
            disabled={scanMutation.isPending}
          >
            {scanMutation.isPending ? "Starting…" : "Scan now"}
          </button>
          {completed.length >= 2 && (
            <Link
              className="btn-ghost"
              to={`/domains/${domainId}/compare?from=${completed[1].id}&to=${completed[0].id}`}
            >
              Compare latest two
            </Link>
          )}
          <button
            className="btn-ghost text-red-300 hover:bg-red-950/40"
            onClick={() => {
              if (confirm("Stop monitoring and delete this domain and its scans?"))
                deleteMutation.mutate();
            }}
          >
            Delete
          </button>
        </div>
      </div>

      {latest && (
        <section className="card p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200">Latest change</h2>
            <Link
              to={`/domains/${domainId}/compare?from=${latest.from_scan_id}&to=${latest.to_scan_id}`}
              className="text-xs text-sky-400 hover:underline"
            >
              view full diff →
            </Link>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={latest.severity} />
            {latest.changed ? (
              latest.summary.signals.map((s) => <SignalChip key={s} signal={s} />)
            ) : (
              <span className="text-sm text-slate-400">No changes vs previous scan.</span>
            )}
          </div>
        </section>
      )}

      {completed[0]?.dns_records && (
        <DnsRecordsCard dns={completed[0].dns_records} capturedAt={completed[0].completed_at} />
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-200">
          Scan history ({data.scans.length})
        </h2>
        {data.scans.length === 0 ? (
          <EmptyState title="No scans yet" hint="Run a scan to capture the first snapshot." />
        ) : (
          <div className="flex flex-col gap-2">
            {data.scans.map((scan, idx) => (
              <ScanRow
                key={scan.id}
                scan={scan}
                domainId={domainId}
                previousCompleted={data.scans.slice(idx + 1).find((s) => s.status === "COMPLETED")}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function DnsRecordsCard({ dns, capturedAt }: { dns: DnsRecords; capturedAt: string | null }) {
  return (
    <section className="card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-200">DNS records</h2>
        <span className="text-xs text-slate-500">
          {dns.zone && (
            <>
              zone <span className="font-mono text-slate-400">{dns.zone}</span> ·{" "}
            </>
          )}
          captured {timeAgo(capturedAt)}
        </span>
      </div>
      {!dns.available ? (
        <p className="text-sm text-slate-500">
          DNS lookup failed for the latest scan{dns.error ? `: ${dns.error}` : "."}
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(DNS_TYPE_LABELS).map(([rtype, label]) => {
            const values = dns[rtype as keyof DnsRecords] as string[] | null | undefined;
            return (
              <div key={rtype} className="rounded-lg border border-ink-700 bg-ink-900 px-3 py-2">
                <div className="text-xs text-slate-500">{label}</div>
                {values == null ? (
                  <div className="text-xs text-amber-300">lookup failed</div>
                ) : values.length === 0 ? (
                  <div className="text-xs text-slate-600">none</div>
                ) : (
                  <ul className="mt-1 space-y-0.5 font-mono text-xs text-slate-300">
                    {values.map((v, i) => (
                      <li key={i} className="break-all">
                        {v}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ScanRow({
  scan,
  domainId,
  previousCompleted,
}: {
  scan: Scan;
  domainId: number;
  previousCompleted?: Scan;
}) {
  return (
    <div className="card flex items-center gap-4 p-3">
      <div className="h-16 w-24 shrink-0 overflow-hidden rounded-md border border-ink-700 bg-ink-950">
        {scan.has_screenshot ? (
          <img
            src={api.scanArtifactUrl(scan.id, "screenshot")}
            className="h-full w-full object-cover object-top"
            alt={`scan ${scan.id}`}
          />
        ) : (
          <div className="grid h-full place-items-center text-[10px] text-slate-600">
            no image
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <StatusBadge status={scan.status} />
          <span className="text-xs text-slate-500">#{scan.id}</span>
          {scan.verdict_malicious && (
            <Badge className="border-red-700 bg-red-900/40 text-red-300">malicious</Badge>
          )}
        </div>
        <div className="mt-1 truncate text-sm text-slate-200">
          {scan.page_title || scan.final_url || "—"}
        </div>
        <div className="text-xs text-slate-500">
          {scan.completed_at ? `completed ${timeAgo(scan.completed_at)}` : `created ${timeAgo(scan.created_at)}`}
          {scan.error && <span className="text-red-400"> · {scan.error}</span>}
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1 text-xs">
        <div className="flex gap-2 text-slate-400">
          {scan.has_screenshot && (
            <a className="hover:text-sky-400" href={api.scanArtifactUrl(scan.id, "screenshot")} target="_blank" rel="noreferrer">
              shot
            </a>
          )}
          {scan.has_dom && (
            <a className="hover:text-sky-400" href={api.scanArtifactUrl(scan.id, "dom")} target="_blank" rel="noreferrer">
              dom
            </a>
          )}
          {scan.has_har && (
            <a className="hover:text-sky-400" href={api.scanArtifactUrl(scan.id, "har")} target="_blank" rel="noreferrer">
              har
            </a>
          )}
        </div>
        {previousCompleted && scan.status === "COMPLETED" && (
          <Link
            className="text-sky-400 hover:underline"
            to={`/domains/${domainId}/compare?from=${previousCompleted.id}&to=${scan.id}`}
          >
            compare ▸ previous
          </Link>
        )}
      </div>
    </div>
  );
}
