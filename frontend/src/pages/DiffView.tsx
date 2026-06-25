import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { DomPanel, HarPanel, ScreenshotPanel, VerdictPanel } from "../components/diffPanels";
import { ErrorState, SeverityBadge, SignalChip, Spinner } from "../ui";

type Tab = "screenshot" | "dom" | "har" | "verdict";
const TABS: { key: Tab; label: string }[] = [
  { key: "screenshot", label: "Screenshot" },
  { key: "dom", label: "DOM" },
  { key: "har", label: "Network (HAR)" },
  { key: "verdict", label: "Verdict & tech" },
];

export default function DiffView() {
  const { id } = useParams();
  const domainId = Number(id);
  const [params] = useSearchParams();
  const fromId = Number(params.get("from"));
  const toId = Number(params.get("to"));
  const [tab, setTab] = useState<Tab>("screenshot");

  const { data: diff, isLoading, isError, error } = useQuery({
    queryKey: ["diff", domainId, fromId, toId],
    queryFn: () => api.computeDiff(domainId, fromId, toId),
    enabled: Boolean(domainId && fromId && toId),
  });

  if (!fromId || !toId) return <ErrorState error="Missing scan ids to compare." />;
  if (isLoading) return <Spinner label="Computing diff…" />;
  if (isError) return <ErrorState error={error} />;
  if (!diff) return null;

  const s = diff.summary;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link to={`/domains/${domainId}`} className="text-xs text-sky-400 hover:underline">
          ← back to domain
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-white">
            Diff: scan #{diff.from_scan_id} → #{diff.to_scan_id}
          </h1>
          <SeverityBadge severity={diff.severity} />
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {diff.changed ? (
            s.signals.map((sig) => <SignalChip key={sig} signal={sig} />)
          ) : (
            <span className="text-sm text-slate-400">No meaningful changes detected.</span>
          )}
        </div>
      </div>

      <div className="flex gap-1 border-b border-ink-700">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.key
                ? "border-sky-500 text-white"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="card p-4">
        {tab === "screenshot" && (
          <ScreenshotPanel
            diff={s.screenshot}
            fromScanId={diff.from_scan_id}
            toScanId={diff.to_scan_id}
            diffId={diff.id}
            hasOverlay={diff.has_screenshot_diff}
          />
        )}
        {tab === "dom" && <DomPanel diff={s.dom} />}
        {tab === "har" && <HarPanel diff={s.har} />}
        {tab === "verdict" && <VerdictPanel diff={s.result} />}
      </div>
    </div>
  );
}
