/**
 * My Reports — the investigations this person has saved, and nothing else.
 *
 * The audit found this page carrying five panels: Identity, Organisations,
 * Saved cases, Activity log and Users — the last three of which `/admin` also
 * rendered, with a second add-user form. So a citizen who opened "My Reports"
 * looking for a complaint PDF was shown a table of platform tenants and a
 * form for creating accounts on the platform.
 *
 * Tenancy moved to `pages/admin/Tenancy.tsx` and is rendered by the admin
 * route. Identity moved to Profile, which is where an account lives. What is
 * left is the page its own lede always described.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileText, RefreshCw, ScanSearch } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import * as api from "@/lib/api";
import type { CaseSummary } from "@/lib/api";

export function CaseBook() {
  return (
    <div className="page">
      <PageHeader
        title="My Reports"
        lede="Every investigation you've saved — ready to reopen, download as a complaint, or take to the police."
      />
      <SavedCases />
    </div>
  );
}

/* ------------------------------------------------------------- saved cases */

function SavedCases() {
  const [rows, setRows] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await api.listReports();
    if (res.ok) setRows(res.data.reports);
    else setError(res.error);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="card">
      <h2 className="card__title">
        <FileText size={16} /> Saved cases
        <button className="btn2 btn2--ghost cb-refresh" onClick={load}>
          <RefreshCw size={13} /> Refresh
        </button>
      </h2>
      {error && (
        <ErrorState
          inline
          title="We couldn't load your saved reports"
          onRetry={() => {
            setError(null);
            void load();
          }}
          detail={error}
        />
      )}
      {!rows && !error && <SkeletonRows rows={3} cols={6} />}
      {rows && rows.length === 0 && (
        <EmptyState
          title="No saved reports yet"
          body="When a check turns up something worth keeping, save it and it lands here — with the evidence, the reasoning, and a complaint you can file."
          icon={<FileText size={20} />}
          action={
            <Link className="btn2 btn2--primary" to="/analyze">
              <ScanSearch size={15} aria-hidden="true" /> Check something suspicious
            </Link>
          }
        />
      )}
      {rows && rows.length > 0 && (
        <div className="cb-tablewrap">
          <table className="cb-table">
            <thead>
              <tr>
                <th>Report</th>
                <th>Incident</th>
                <th>Peak</th>
                <th>Caller</th>
                <th>By</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.report_id}>
                  <td className="mono">{r.report_id}</td>
                  <td>{r.incident_type ?? "—"}</td>
                  <td>
                    {r.peak_threat != null ? `${r.peak_threat.toFixed(0)}` : "—"}
                    {r.final_level ? ` · ${r.final_level}` : ""}
                  </td>
                  <td className="mono">{r.caller_number ?? "—"}</td>
                  <td>{r.created_by ?? "—"}</td>
                  <td className="small muted">{fmt(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


/* ----------------------------------------------------------------- helpers */

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}
