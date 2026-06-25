import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import { ErrorState } from "../ui";

export default function AddDomainForm() {
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [scanNow, setScanNow] = useState(true);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: () =>
      api.addDomain({
        url,
        label: label || undefined,
        scan_now: scanNow,
      }),
    onSuccess: (domain) => {
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      setUrl("");
      setLabel("");
      navigate(`/domains/${domain.id}`);
    },
  });

  return (
    <form
      className="card p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (url.trim()) mutation.mutate();
      }}
    >
      <h2 className="mb-3 text-sm font-semibold text-slate-200">Monitor a new domain</h2>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          className="input sm:flex-1"
          placeholder="example.com or https://example.com/path"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          autoFocus
        />
        <input
          className="input sm:w-48"
          placeholder="label (optional)"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <button type="submit" className="btn-primary sm:w-36" disabled={mutation.isPending}>
          {mutation.isPending ? "Adding…" : "Add domain"}
        </button>
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm text-slate-400">
        <input
          type="checkbox"
          checked={scanNow}
          onChange={(e) => setScanNow(e.target.checked)}
          className="accent-sky-600"
        />
        Run an initial scan immediately
      </label>
      {mutation.isError && (
        <div className="mt-3">
          <ErrorState error={mutation.error} />
        </div>
      )}
    </form>
  );
}
