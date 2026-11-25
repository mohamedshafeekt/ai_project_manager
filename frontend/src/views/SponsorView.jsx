import React from 'react';
import {
  TrendingUp,
  AlertTriangle,
  ShieldAlert,
  GitPullRequest,
  CheckCircle2,
  DollarSign,
  FileWarning,
} from 'lucide-react';

export default function SponsorView({ project, dashboard }) {
  const health = dashboard?.health_and_alerts || {};
  const decisions = dashboard?.decisions || [];
  const raid = dashboard?.raid_items || [];
  const scopeChanges = dashboard?.scope_changes || [];
  const codeActivity = dashboard?.code_activity || [];

  const forecastColor =
    health.forecast_status === 'On Track'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : health.forecast_status === 'At Risk'
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : 'bg-rose-50 text-rose-700 border-rose-200';

  return (
    <div className="space-y-6">
      {/* Executive KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase">Delivery Forecast</p>
          <div className="mt-2 flex items-center gap-2">
            <span className={`px-3 py-1 rounded-full text-sm font-bold border ${forecastColor}`}>
              {health.forecast_status || 'On Track'}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-2">{health.forecast_reason}</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase">Action Completion</p>
          <p className="text-2xl font-bold text-slate-900 mt-2 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-indigo-600" />
            {health.completion_percentage ?? 0}%
          </p>
          <p className="text-xs text-slate-500 mt-2">
            {health.completed_action_items ?? 0} of {health.total_action_items ?? 0} items completed
          </p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase">Open High Risks</p>
          <p className="text-2xl font-bold text-slate-900 mt-2 flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-orange-500" />
            {health.open_high_risks ?? 0}
          </p>
          <p className="text-xs text-slate-500 mt-2">
            {health.overdue_alerts?.length ?? 0} overdue deadline alert(s)
          </p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase">Total Project AI Cost</p>
          <p className="text-2xl font-bold text-slate-900 mt-2 flex items-center gap-1">
            <DollarSign className="w-5 h-5 text-emerald-600" />
            {(project?.total_ai_cost_usd ?? 0).toFixed(5)}
          </p>
          <p className="text-xs text-slate-500 mt-2">
            {(project?.total_tokens ?? 0).toLocaleString()} total tokens used
          </p>
        </div>
      </div>

      {/* Overdue Deadline Alerts */}
      {health.overdue_alerts?.length > 0 && (
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-5 space-y-2">
          <h3 className="text-sm font-semibold text-rose-900 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600" />
            Active Deadline Alerts ({health.overdue_alerts.length})
          </h3>
          {health.overdue_alerts.map((a) => (
            <p key={a.action_item_id} className="text-xs text-rose-800">
              • {a.alert_message}
            </p>
          ))}
        </div>
      )}

      {/* Decisions & Scope Changes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
          <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            Approved Decisions ({decisions.length})
          </h3>
          <div className="space-y-2.5">
            {decisions.length === 0 ? (
              <p className="text-xs text-slate-500">No approved decisions logged yet.</p>
            ) : (
              decisions.map((d) => (
                <div key={d.id} className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs text-slate-800">
                  {d.decision_text}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
          <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
            <FileWarning className="w-4 h-4 text-rose-600" />
            Approved Scope Changes ({scopeChanges.length})
          </h3>
          <div className="space-y-2.5">
            {scopeChanges.length === 0 ? (
              <p className="text-xs text-slate-500">No scope changes approved.</p>
            ) : (
              scopeChanges.map((s) => (
                <div key={s.id} className="p-3 rounded-xl bg-rose-50/50 border border-rose-100 text-xs">
                  <p className="font-semibold text-slate-900">{s.requested_change}</p>
                  <p className="text-slate-500 italic mt-1">"{s.verbatim_quote}"</p>
                  <p className="text-slate-600 mt-1">Impact: {s.impact_summary}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* RAID Log & GitHub Code Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
          <h3 className="font-semibold text-slate-900 mb-3">RAID Log ({raid.length})</h3>
          <div className="space-y-2.5">
            {raid.length === 0 ? (
              <p className="text-xs text-slate-500">No RAID entries logged.</p>
            ) : (
              raid.map((r) => (
                <div key={r.id} className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="uppercase font-bold text-[10px] px-2 py-0.5 rounded bg-orange-100 text-orange-800">
                      {r.type}
                    </span>
                    <span className="uppercase font-semibold text-[10px] text-slate-500">
                      Severity: {r.severity}
                    </span>
                    <span className="ml-auto text-slate-500">Owner: {r.owner}</span>
                  </div>
                  <p className="text-slate-800">{r.description}</p>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
          <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
            <GitPullRequest className="w-4 h-4 text-indigo-600" />
            GitHub Code Activity & Discrepancies
          </h3>
          <div className="space-y-2.5">
            {codeActivity.length === 0 ? (
              <p className="text-xs text-slate-500">No GitHub PR activity synced yet.</p>
            ) : (
              codeActivity.map((c) => (
                <div key={c.id} className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-800">
                      {c.identifier}: {c.title}
                    </span>
                    <span
                      className={`uppercase text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        c.state === 'merged'
                          ? 'bg-purple-100 text-purple-700'
                          : 'bg-emerald-100 text-emerald-700'
                      }`}
                    >
                      {c.state}
                    </span>
                  </div>
                  <p className="text-slate-500 mt-1">
                    Author: {c.author} {c.jira_issue_key && `• Linked Jira: ${c.jira_issue_key}`}
                  </p>
                  {c.has_discrepancy && (
                    <p className="mt-1.5 text-rose-700 bg-rose-50 p-2 rounded border border-rose-200 font-medium">
                      [!] {c.discrepancy_details}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
