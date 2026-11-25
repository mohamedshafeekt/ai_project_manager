import React, { useState } from 'react';
import { CheckCircle2, Circle, Clock, User, ExternalLink, AlertCircle } from 'lucide-react';
import { api } from '../api';

export default function MemberView({ dashboard, onRefresh }) {
  const actionItems = dashboard?.action_items || [];
  const overdueIds = new Set(
    (dashboard?.health_and_alerts?.overdue_alerts || []).map((a) => a.action_item_id)
  );

  // Build unique list of owners for quick role filter
  const owners = ['All', ...Array.from(new Set(actionItems.map((i) => i.owner)))];
  const [selectedOwner, setSelectedOwner] = useState('All');
  const [updatingId, setUpdatingId] = useState(null);

  const filtered =
    selectedOwner === 'All'
      ? actionItems
      : actionItems.filter((i) => i.owner === selectedOwner);

  const handleStatusTap = async (itemId, newStatus) => {
    setUpdatingId(itemId);
    try {
      await api.updateActionItemStatus(itemId, newStatus);
      onRefresh();
    } catch (err) {
      console.error(err);
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">My Action Items</h2>
            <p className="text-xs text-slate-500">
              Update your task progress in one tap. Overdue items are highlighted automatically.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <User className="w-4 h-4 text-slate-400" />
            <select
              value={selectedOwner}
              onChange={(e) => setSelectedOwner(e.target.value)}
              className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {owners.map((o) => (
                <option key={o} value={o}>
                  {o === 'All' ? 'All Team Members' : o}
                </option>
              ))}
            </select>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-sm border border-dashed border-slate-200 rounded-xl">
            No approved action items found. Approve items in the PM Review Queue first.
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((item) => {
              const isOverdue = overdueIds.has(item.id) && item.status !== 'done';
              return (
                <div
                  key={item.id}
                  className={`p-4 rounded-xl border transition flex flex-wrap items-center justify-between gap-4 ${
                    isOverdue
                      ? 'bg-rose-50/60 border-rose-200'
                      : item.status === 'done'
                      ? 'bg-emerald-50/40 border-emerald-200'
                      : 'bg-white border-slate-200'
                  }`}
                >
                  <div className="space-y-1 flex-1 min-w-[240px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                        {item.owner}
                      </span>
                      <span
                        className={`text-xs flex items-center gap-1 ${
                          item.due_date === 'MISSING' || isOverdue
                            ? 'text-rose-600 font-semibold'
                            : 'text-slate-500'
                        }`}
                      >
                        <Clock className="w-3.5 h-3.5" />
                        Due: {item.due_date}
                      </span>
                      {isOverdue && (
                        <span className="text-[11px] font-semibold bg-rose-100 text-rose-700 px-2 py-0.5 rounded-full flex items-center gap-1">
                          <AlertCircle className="w-3 h-3" />
                          Overdue
                        </span>
                      )}
                      {item.jira_issue_key && (
                        <span className="text-[11px] font-mono bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded flex items-center gap-1">
                          <ExternalLink className="w-3 h-3" />
                          {item.jira_issue_key}
                        </span>
                      )}
                    </div>
                    <p
                      className={`text-sm font-medium ${
                        item.status === 'done' ? 'line-through text-slate-400' : 'text-slate-900'
                      }`}
                    >
                      {item.description}
                    </p>
                  </div>

                  {/* One-Tap Status Buttons */}
                  <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-lg">
                    {[
                      { id: 'todo', label: 'To Do', icon: Circle },
                      { id: 'in_progress', label: 'In Progress', icon: Clock },
                      { id: 'done', label: 'Done', icon: CheckCircle2 },
                    ].map((opt) => {
                      const Icon = opt.icon;
                      const active = item.status === opt.id;
                      return (
                        <button
                          key={opt.id}
                          disabled={updatingId === item.id}
                          onClick={() => handleStatusTap(item.id, opt.id)}
                          className={`px-3 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 transition ${
                            active
                              ? opt.id === 'done'
                                ? 'bg-emerald-600 text-white shadow-xs'
                                : opt.id === 'in_progress'
                                ? 'bg-indigo-600 text-white shadow-xs'
                                : 'bg-white text-slate-900 shadow-xs'
                              : 'text-slate-600 hover:text-slate-900'
                          }`}
                        >
                          <Icon className="w-3.5 h-3.5" />
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
