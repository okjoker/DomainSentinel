import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api";
import AddDomainForm from "../components/AddDomainForm";
import { isInFlight, timeAgo } from "../format";
import { EmptyState, ErrorState, SeverityBadge, Spinner, StatusBadge } from "../ui";

export default function Dashboard() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["domains"],
    queryFn: api.listDomains,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((d) => isInFlight(d.last_scan_status)) ? 3000 : false,
  });

  return (
    <div className="flex flex-col gap-6">
      <AddDomainForm />

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-white">Monitored domains</h1>
          {data && <span className="text-sm text-slate-500">{data.length} total</span>}
        </div>

        {isLoading && <Spinner label="Loading domains…" />}
        {isError && <ErrorState error={error} />}
        {data && data.length === 0 && (
          <EmptyState title="No domains yet" hint="Add one above to start monitoring." />
        )}

        {data && data.length > 0 && (
          <div className="card divide-y divide-ink-700 overflow-hidden">
            {data.map((d) => (
              <Link
                key={d.id}
                to={`/domains/${d.id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-ink-800/60"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium text-slate-100">
                      {d.label || d.url}
                    </span>
                    {d.last_diff_changed && (
                      <span className="h-2 w-2 shrink-0 rounded-full bg-amber-400" title="changed" />
                    )}
                  </div>
                  <div className="truncate text-xs text-slate-500">{d.url}</div>
                </div>
                <div className="flex shrink-0 items-center gap-3 text-xs text-slate-400">
                  <span className="hidden sm:inline">{d.scan_count} scans</span>
                  <span className="hidden w-20 text-right sm:inline">
                    {timeAgo(d.last_scan_at)}
                  </span>
                  <SeverityBadge severity={d.last_diff_severity} />
                  <StatusBadge status={d.last_scan_status} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
