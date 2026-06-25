import { useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "react-router-dom";

import { api } from "../api";

export default function Layout() {
  const { data: info } = useQuery({ queryKey: ["info"], queryFn: api.info });

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-ink-700 bg-ink-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="flex items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-sky-600 text-lg">
              🛡️
            </span>
            <span className="text-lg font-semibold tracking-tight text-white">
              DomainSentinel
            </span>
          </Link>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            {info?.fake_cloudflare && (
              <span className="rounded-full border border-amber-700 bg-amber-900/40 px-2 py-0.5 text-amber-300">
                demo mode (synthetic scans)
              </span>
            )}
            {info && <span>v{info.version}</span>}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
