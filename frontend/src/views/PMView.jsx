import React, { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  Edit3,
  AlertTriangle,
  Upload,
  Sparkles,
  Lock,
  MessageSquareQuote,
  RefreshCw,
  CheckCheck,
  Clock,
  DollarSign,
} from 'lucide-react';
import { api } from '../api';

const SAMPLE_TRANSCRIPT = `[00:01:05] Mohamed: Welcome everyone to our sprint sync. Let's review progress.
[00:01:30] Alex: The login API and README update for KAN-1 are completely done and tested.
[00:02:00] Mohamed: Great! Also, we need to finalize the Stripe webhook handler. Alex, can you finish that by Friday?
[00:02:20] Alex: Sure, I will get the Stripe webhook handler done by Friday.
[00:02:45] Sarah: We also decided as a team to use PostgreSQL on Neon for our production database instead of SQLite.
[00:03:15] Alex: One risk to flag: the external payment sandbox API has been timing out intermittently this morning.
[00:03:50] Sarah: By the way, a stakeholder asked if we can also build a native iOS mobile app in this release?
[00:04:15] Mohamed: Let's note that request, though it wasn't in our Phase 1 agreement. Also someone needs to update the deployment docs, though we don't have an owner or date for that yet.`;

export default function PMView({
  project,
  drafts,
  meetings,
  auditHistory,
  onRefresh,
  onOpenTranscript,
}) {
  const [title, setTitle] = useState('Sprint Sync Meeting');
  const [meetingDate, setMeetingDate] = useState(new Date().toISOString().slice(0, 10));
  const [transcript, setTranscript] = useState('');
  const [isPrivate, setIsPrivate] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  const [editingDraftId, setEditingDraftId] = useState(null);
  const [editJson, setEditJson] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [toast, setToast] = useState(null);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const handleIngest = async (e) => {
    e.preventDefault();
    if (!isPrivate && !transcript.trim()) {
      showToast('Please paste a transcript or load the sample.', 'error');
      return;
    }
    setIngesting(true);
    try {
      const res = await api.ingestMeeting(project.id, {
        title,
        meeting_date: meetingDate,
        raw_transcript: isPrivate ? '' : transcript,
        is_private: isPrivate,
      });
      if (res.is_private) {
        showToast('Private meeting logged without reading or storing transcript.');
      } else {
        showToast(`Meeting analyzed! Cost: $${res.cost_usd.toFixed(5)} (${res.token_count} tokens)`);
      }
      setTranscript('');
      onRefresh();
    } catch (err) {
      showToast(`Ingestion failed: ${err.message}`, 'error');
    } finally {
      setIngesting(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIngesting(true);
    try {
      const fd = new FormData();
      fd.append('title', title || file.name);
      fd.append('meeting_date', meetingDate);
      fd.append('is_private', String(isPrivate));
      fd.append('file', file);
      await api.uploadMeetingFile(project.id, fd);
      showToast(`Uploaded and analyzed '${file.name}'!`);
      onRefresh();
    } catch (err) {
      showToast(`Upload failed: ${err.message}`, 'error');
    } finally {
      setIngesting(false);
    }
  };

  const handleApprove = async (draft, editedPayload = null) => {
    setBusyId(draft.id);
    try {
      const res = await api.approveDraft(draft.id, 'Mohamed Shafeek (PM)', editedPayload);
      if (res.jira_sync_status === 'failed') {
        showToast(`Approved locally, but Jira sync failed: ${res.jira_sync_error}`, 'error');
      } else if (res.jira_issue_key) {
        showToast(`Approved & synced to Jira (${res.jira_issue_key})!`);
      } else {
        showToast('Draft approved and saved!');
      }
      setEditingDraftId(null);
      onRefresh();
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (draftId) => {
    setBusyId(draftId);
    try {
      await api.rejectDraft(draftId, 'Mohamed Shafeek (PM)');
      showToast('Draft rejected.');
      onRefresh();
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleBatchApprove = async () => {
    if (drafts.length === 0) return;
    setBusyId('batch');
    try {
      const res = await api.batchApproveDrafts(
        project.id,
        drafts.map((d) => d.id),
        'Mohamed Shafeek (PM)'
      );
      showToast(`Batch approved ${res.approved_count} draft(s)!`);
      onRefresh();
    } catch (err) {
      showToast(`Batch error: ${err.message}`, 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleRetryJira = async (auditId) => {
    setBusyId(auditId);
    try {
      const res = await api.retryJiraSync(auditId);
      if (res.jira_sync_status === 'retried') {
        showToast(`Jira retry succeeded (${res.jira_issue_key || 'Updated'})!`);
      } else {
        showToast(`Retry failed: ${res.jira_sync_error}`, 'error');
      }
      onRefresh();
    } catch (err) {
      showToast(`Retry error: ${err.message}`, 'error');
    } finally {
      setBusyId(null);
    }
  };

  const getConfidenceBadge = (score) => {
    const pct = Math.round(score * 100);
    if (pct >= 85) return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    if (pct >= 65) return 'bg-amber-50 text-amber-700 border-amber-200';
    return 'bg-rose-50 text-rose-700 border-rose-200';
  };

  const getCategoryStyle = (cat) => {
    const map = {
      action_item: 'bg-blue-50 text-blue-700 border-blue-200',
      decision: 'bg-purple-50 text-purple-700 border-purple-200',
      raid_item: 'bg-orange-50 text-orange-700 border-orange-200',
      scope_change: 'bg-rose-50 text-rose-700 border-rose-200',
      jira_status_update: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    };
    return map[cat] || 'bg-slate-100 text-slate-700';
  };

  return (
    <div className="space-y-6">
      {toast && (
        <div
          className={`fixed bottom-5 right-5 z-50 px-4 py-3 rounded-xl shadow-lg border text-sm font-medium ${
            toast.type === 'error'
              ? 'bg-rose-50 border-rose-200 text-rose-800'
              : 'bg-emerald-50 border-emerald-200 text-emerald-800'
          }`}
        >
          {toast.msg}
        </div>
      )}

      {/* 1. Ingest Meeting Panel */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-indigo-600" />
              Ingest Meeting Transcript
            </h2>
            <p className="text-xs text-slate-500">
              Supports Teams VTT, JSON, or speaker-timestamped text. Drafts appear in the Review Queue below.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setTranscript(SAMPLE_TRANSCRIPT)}
              className="text-xs px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-700 font-medium hover:bg-indigo-100 transition"
            >
              Load Sample Transcript
            </button>
            <label className="text-xs px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 font-medium hover:bg-slate-200 transition cursor-pointer flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5" />
              Upload File (.vtt / .txt)
              <input type="file" accept=".txt,.vtt,.json" className="hidden" onChange={handleFileUpload} />
            </label>
          </div>
        </div>

        <form onSubmit={handleIngest} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-slate-600 mb-1">Meeting Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Meeting Date</label>
              <input
                type="date"
                value={meetingDate}
                onChange={(e) => setMeetingDate(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          {!isPrivate && (
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Transcript</label>
              <textarea
                rows={4}
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                placeholder="[00:01:05] Alice: We finished the login API..."
                className="w-full px-3 py-2 text-sm font-mono border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-4">
            <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={isPrivate}
                onChange={(e) => setIsPrivate(e.target.checked)}
                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              <Lock className="w-4 h-4 text-amber-500" />
              <span>Mark as Private Meeting (never read or stored by AI)</span>
            </label>

            <button
              type="submit"
              disabled={ingesting}
              className="px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition flex items-center gap-2"
            >
              {ingesting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Analyzing with LangGraph...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  Analyze & Draft Updates
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* 2. PM Review Queue */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              Review Queue ({drafts.length} waiting)
            </h2>
            <p className="text-xs text-slate-500">
              Nothing reaches Jira or the project record until you explicitly approve it.
            </p>
          </div>
          {drafts.length > 0 && (
            <button
              onClick={handleBatchApprove}
              disabled={busyId === 'batch'}
              className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 transition flex items-center gap-1.5"
            >
              <CheckCheck className="w-4 h-4" />
              Batch Approve All ({drafts.length})
            </button>
          )}
        </div>

        {drafts.length === 0 ? (
          <div className="text-center py-10 text-slate-500 text-sm border border-dashed border-slate-200 rounded-xl">
            No pending drafts! Ingest a meeting above to generate proposals.
          </div>
        ) : (
          <div className="space-y-4">
            {drafts.map((draft) => {
              const isEditing = editingDraftId === draft.id;
              return (
                <div
                  key={draft.id}
                  className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white transition"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1.5 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`text-[11px] font-semibold uppercase px-2 py-0.5 rounded-full border ${getCategoryStyle(
                            draft.category
                          )}`}
                        >
                          {draft.category.replace(/_/g, ' ')}
                        </span>
                        <span
                          className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${getConfidenceBadge(
                            draft.confidence_score
                          )}`}
                        >
                          Confidence: {Math.round(draft.confidence_score * 100)}%
                        </span>
                        {draft.supporting_lines?.length > 0 && (
                          <button
                            onClick={() => onOpenTranscript(draft.meeting_id, draft.supporting_lines)}
                            className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100 flex items-center gap-1 transition"
                          >
                            <MessageSquareQuote className="w-3 h-3" />
                            Lines: {draft.supporting_lines.join(', ')}
                          </button>
                        )}
                      </div>

                      <h3 className="font-semibold text-slate-900 text-sm">{draft.title}</h3>

                      {draft.discrepancy_note && (
                        <div className="mt-2 p-2.5 rounded-lg bg-rose-50 border border-rose-200 flex items-start gap-2 text-xs text-rose-800">
                          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                          <div>
                            <span className="font-semibold">GitHub Discrepancy Detected: </span>
                            {draft.discrepancy_note}
                          </div>
                        </div>
                      )}

                      {isEditing ? (
                        <div className="mt-3 space-y-2">
                          <textarea
                            rows={5}
                            value={editJson}
                            onChange={(e) => setEditJson(e.target.value)}
                            className="w-full p-2.5 text-xs font-mono border border-indigo-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => {
                                try {
                                  const parsed = JSON.parse(editJson);
                                  handleApprove(draft, parsed);
                                } catch {
                                  showToast('Invalid JSON format', 'error');
                                }
                              }}
                              className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700"
                            >
                              Save & Approve
                            </button>
                            <button
                              onClick={() => setEditingDraftId(null)}
                              className="px-3 py-1.5 rounded-lg bg-slate-200 text-slate-700 text-xs font-medium hover:bg-slate-300"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 text-xs text-slate-600 bg-white p-3 rounded-lg border border-slate-100 grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {Object.entries(draft.proposed_payload || {}).map(([k, v]) => (
                            <div key={k}>
                              <span className="font-medium text-slate-400 uppercase text-[10px] mr-1.5">
                                {k.replace(/_/g, ' ')}:
                              </span>
                              <span className={v === 'MISSING' ? 'text-rose-600 font-semibold' : 'text-slate-800'}>
                                {typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v ?? '—')}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {!isEditing && (
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          onClick={() => handleApprove(draft)}
                          disabled={busyId === draft.id}
                          className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Approve
                        </button>
                        <button
                          onClick={() => {
                            setEditingDraftId(draft.id);
                            setEditJson(JSON.stringify(draft.proposed_payload, null, 2));
                          }}
                          className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 text-xs font-medium hover:bg-slate-100 flex items-center gap-1"
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                          Edit
                        </button>
                        <button
                          onClick={() => handleReject(draft.id)}
                          disabled={busyId === draft.id}
                          className="px-2.5 py-1.5 rounded-lg bg-white border border-rose-200 text-rose-600 text-xs font-medium hover:bg-rose-50 flex items-center gap-1"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          Reject
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 3. Recent Meetings & AI Cost + Audit History */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
          <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-500" />
            Recent Meetings & AI Cost
          </h3>
          <div className="space-y-2.5">
            {meetings.length === 0 ? (
              <p className="text-xs text-slate-500">No meetings ingested yet.</p>
            ) : (
              meetings.map((m) => (
                <div
                  key={m.id}
                  className="p-3 rounded-xl border border-slate-100 bg-slate-50 flex items-center justify-between text-xs"
                >
                  <div>
                    <p className="font-semibold text-slate-800 flex items-center gap-1.5">
                      {m.is_private && <Lock className="w-3.5 h-3.5 text-amber-500" />}
                      {m.title}
                    </p>
                    <p className="text-slate-500 mt-0.5">
                      {m.meeting_date?.slice(0, 10)} • Status: {m.status}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="inline-flex items-center gap-1 font-mono font-semibold text-slate-700 bg-white px-2 py-0.5 rounded border border-slate-200">
                      <DollarSign className="w-3 h-3 text-emerald-600" />
                      {m.cost_usd.toFixed(5)}
                    </span>
                    <p className="text-[10px] text-slate-400 mt-0.5">{m.token_count} tokens</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
          <h3 className="font-semibold text-slate-900 mb-3">Change & Audit History</h3>
          <div className="space-y-2.5 max-h-80 overflow-y-auto">
            {auditHistory.length === 0 ? (
              <p className="text-xs text-slate-500">No approvals or rejections recorded yet.</p>
            ) : (
              auditHistory.map((a) => (
                <div
                  key={a.id}
                  className="p-3 rounded-xl border border-slate-100 bg-slate-50 text-xs flex items-start justify-between gap-2"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-800 uppercase text-[10px]">
                        {a.category.replace(/_/g, ' ')}
                      </span>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          a.action === 'rejected'
                            ? 'bg-rose-100 text-rose-700'
                            : 'bg-emerald-100 text-emerald-700'
                        }`}
                      >
                        {a.action.replace(/_/g, ' ')}
                      </span>
                      {a.jira_issue_key && (
                        <span className="font-mono text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded">
                          {a.jira_issue_key}
                        </span>
                      )}
                    </div>
                    <p className="text-slate-500 mt-1">
                      By {a.approver_name} • Jira: {a.jira_sync_status}
                    </p>
                    {a.jira_sync_error && (
                      <p className="text-rose-600 text-[11px] mt-1">{a.jira_sync_error}</p>
                    )}
                  </div>
                  {a.jira_sync_status === 'failed' && (
                    <button
                      onClick={() => handleRetryJira(a.id)}
                      disabled={busyId === a.id}
                      className="px-2.5 py-1 rounded bg-amber-100 text-amber-800 font-medium hover:bg-amber-200 flex items-center gap-1 shrink-0"
                    >
                      <RefreshCw className="w-3 h-3" />
                      Retry Jira
                    </button>
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
