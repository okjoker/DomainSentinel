import {
  api,
  type DnsDiff,
  type DomDiff,
  type HarDiff,
  type ResultDiff,
  type ScreenshotDiff,
} from "../api";
import { Badge } from "../ui";

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-sm font-medium text-slate-200">{value}</div>
    </div>
  );
}

function Unavailable() {
  return (
    <p className="text-sm text-slate-500">
      This artifact was not available for one of the scans, so no comparison could be made.
    </p>
  );
}

function List({ items, tone }: { items: string[]; tone: "add" | "remove" }) {
  const color = tone === "add" ? "text-emerald-300" : "text-red-300";
  const prefix = tone === "add" ? "+" : "−";
  return (
    <ul className="space-y-1 font-mono text-xs">
      {items.map((item, i) => (
        <li key={i} className={color}>
          <span className="mr-2 opacity-60">{prefix}</span>
          {item}
        </li>
      ))}
    </ul>
  );
}

export function ScreenshotPanel({
  diff,
  fromScanId,
  toScanId,
  diffId,
  hasOverlay,
}: {
  diff: ScreenshotDiff;
  fromScanId: number;
  toScanId: number;
  diffId: number;
  hasOverlay: boolean;
}) {
  if (!diff?.available) return <Unavailable />;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Similarity" value={`${Math.round((diff.similarity ?? 0) * 100)}%`} />
        <Stat label="Pixels changed" value={`${Math.round((diff.changed_ratio ?? 0) * 100)}%`} />
        <Stat label="Size changed" value={diff.size_changed ? "yes" : "no"} />
        <Stat label="Verdict" value={diff.changed ? "changed" : "unchanged"} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <figure>
          <figcaption className="mb-1 text-xs text-slate-500">Before (scan #{fromScanId})</figcaption>
          <img
            src={api.scanArtifactUrl(fromScanId, "screenshot")}
            className="w-full rounded-lg border border-ink-700"
            alt="before"
          />
        </figure>
        <figure>
          <figcaption className="mb-1 text-xs text-slate-500">After (scan #{toScanId})</figcaption>
          <img
            src={api.scanArtifactUrl(toScanId, "screenshot")}
            className="w-full rounded-lg border border-ink-700"
            alt="after"
          />
        </figure>
      </div>
      {hasOverlay && (
        <figure>
          <figcaption className="mb-1 text-xs text-slate-500">
            Difference overlay (changed regions tinted red)
          </figcaption>
          <img
            src={api.diffScreenshotUrl(diffId)}
            className="w-full rounded-lg border border-ink-700"
            alt="diff overlay"
          />
        </figure>
      )}
    </div>
  );
}

export function DomPanel({ diff }: { diff: DomDiff }) {
  if (!diff?.available) return <Unavailable />;
  if (!diff.changed) return <p className="text-sm text-slate-400">No DOM changes detected.</p>;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Similarity" value={`${Math.round((diff.similarity ?? 0) * 100)}%`} />
        <Stat label="Lines added" value={diff.added_count ?? 0} />
        <Stat label="Lines removed" value={diff.removed_count ?? 0} />
      </div>
      <pre className="max-h-[28rem] overflow-auto rounded-lg border border-ink-700 bg-ink-950 p-3 text-xs leading-relaxed">
        {(diff.unified ?? []).map((line, i) => {
          let cls = "text-slate-400";
          if (line.startsWith("+") && !line.startsWith("+++")) cls = "text-emerald-300";
          else if (line.startsWith("-") && !line.startsWith("---")) cls = "text-red-300";
          else if (line.startsWith("@@")) cls = "text-sky-400";
          return (
            <div key={i} className={cls}>
              {line || " "}
            </div>
          );
        })}
      </pre>
    </div>
  );
}

export function HarPanel({ diff }: { diff: HarDiff }) {
  if (!diff?.available) return <Unavailable />;
  const sections: [string, string[], "add" | "remove"][] = [
    ["New hosts contacted", diff.added_hosts ?? [], "add"],
    ["Hosts no longer contacted", diff.removed_hosts ?? [], "remove"],
    ["New requests", diff.added_requests ?? [], "add"],
    ["Removed requests", diff.removed_requests ?? [], "remove"],
  ];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Requests before" value={diff.old_request_count ?? 0} />
        <Stat label="Requests after" value={diff.new_request_count ?? 0} />
      </div>
      {(diff.added_hosts?.length ?? 0) > 0 && (
        <p className="text-xs text-amber-300">
          ⚠ {diff.added_hosts!.length} new external host(s) — review for injected scripts or
          trackers.
        </p>
      )}
      {sections.map(([title, items, tone]) =>
        items.length ? (
          <div key={title}>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {title}
            </h4>
            <List items={items} tone={tone} />
          </div>
        ) : null,
      )}
      {(diff.status_changes?.length ?? 0) > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Status code changes
          </h4>
          <ul className="space-y-1 font-mono text-xs text-amber-300">
            {diff.status_changes!.map((c, i) => (
              <li key={i}>
                {c.from} → {c.to} {c.url}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!diff.changed && <p className="text-sm text-slate-400">No network changes detected.</p>}
    </div>
  );
}

export const DNS_TYPE_LABELS: Record<string, string> = {
  ns: "Nameservers (NS)",
  mx: "Mail servers (MX)",
  txt: "TXT records",
  spf: "SPF",
  dmarc: "DMARC",
};

export function DnsPanel({ diff }: { diff: DnsDiff }) {
  if (!diff?.available) return <Unavailable />;
  const types = Object.keys(DNS_TYPE_LABELS);
  const critical = (diff.changed_types ?? []).some((t) => t === "ns" || t === "mx");
  return (
    <div className="space-y-4">
      {diff.zone && (
        <p className="text-xs text-slate-500">
          Records for zone <span className="font-mono text-slate-300">{diff.zone}</span>
        </p>
      )}
      {critical && (
        <p className="text-xs text-red-300">
          ⚠ Nameserver or MX changes can indicate a domain hijack or mail interception — verify
          this change was intentional.
        </p>
      )}
      {!diff.changed && <p className="text-sm text-slate-400">No DNS record changes detected.</p>}
      {types.map((rtype) => {
        const rec = diff.records?.[rtype];
        const current = diff.new?.[rtype];
        return (
          <div key={rtype}>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {DNS_TYPE_LABELS[rtype]}
            </h4>
            {rec && !rec.available ? (
              <p className="text-xs text-slate-500">Lookup failed for one of the scans.</p>
            ) : rec && (rec.added.length || rec.removed.length) ? (
              <div className="space-y-1">
                {rec.removed.length > 0 && <List items={rec.removed} tone="remove" />}
                {rec.added.length > 0 && <List items={rec.added} tone="add" />}
              </div>
            ) : (
              <ul className="space-y-1 font-mono text-xs text-slate-400">
                {(current ?? []).length ? (
                  (current ?? []).map((v, i) => <li key={i}>{v}</li>)
                ) : (
                  <li className="text-slate-600">none</li>
                )}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Change({ label, from, to }: { label: string; from: React.ReactNode; to: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-slate-500">{label}:</span>
      <span className="font-mono text-red-300">{String(from)}</span>
      <span className="text-slate-500">→</span>
      <span className="font-mono text-emerald-300">{String(to)}</span>
    </div>
  );
}

export function VerdictPanel({ diff }: { diff: ResultDiff }) {
  if (!diff?.available) return <Unavailable />;
  if (!diff.changed)
    return <p className="text-sm text-slate-400">No verdict, technology or metadata changes.</p>;
  return (
    <div className="space-y-3">
      {diff.verdict_change && (
        <Change
          label="Malicious verdict"
          from={diff.verdict_change.from}
          to={diff.verdict_change.to}
        />
      )}
      {diff.title_change && (
        <Change label="Page title" from={diff.title_change.from} to={diff.title_change.to} />
      )}
      {diff.final_url_change && (
        <Change
          label="Final URL"
          from={diff.final_url_change.from}
          to={diff.final_url_change.to}
        />
      )}
      {(diff.categories_added?.length ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-500">New threat categories:</span>
          {diff.categories_added!.map((c) => (
            <Badge key={c} className="border-red-700 bg-red-900/40 text-red-300">
              {c}
            </Badge>
          ))}
        </div>
      )}
      {(diff.technologies_added?.length ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-500">Technologies added:</span>
          {diff.technologies_added!.map((t) => (
            <Badge key={t} className="border-emerald-700 bg-emerald-900/40 text-emerald-300">
              {t}
            </Badge>
          ))}
        </div>
      )}
      {(diff.technologies_removed?.length ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-500">Technologies removed:</span>
          {diff.technologies_removed!.map((t) => (
            <Badge key={t} className="border-red-700 bg-red-900/40 text-red-300">
              {t}
            </Badge>
          ))}
        </div>
      )}
      {((diff.ips_added?.length ?? 0) > 0 || (diff.ips_removed?.length ?? 0) > 0) && (
        <div className="text-sm">
          <span className="text-slate-500">IP changes: </span>
          <span className="font-mono text-emerald-300">
            {(diff.ips_added ?? []).map((ip) => `+${ip}`).join(" ")}
          </span>{" "}
          <span className="font-mono text-red-300">
            {(diff.ips_removed ?? []).map((ip) => `-${ip}`).join(" ")}
          </span>
        </div>
      )}
    </div>
  );
}
