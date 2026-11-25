const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL.replace(/\/$/, '')}/api`
  : '/api';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(errText || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  getProjects: () => request('/projects'),
  updateProject: (projectId, data) =>
    request(`/projects/${projectId}`, { method: 'PATCH', body: JSON.stringify(data) }),

  getDashboard: (projectId) => request(`/projects/${projectId}/dashboard`),
  getMeetings: (projectId) => request(`/projects/${projectId}/meetings`),
  ingestMeeting: (projectId, payload) =>
    request(`/projects/${projectId}/meetings`, { method: 'POST', body: JSON.stringify(payload) }),
  uploadMeetingFile: async (projectId, formData) => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/meetings/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  getTranscript: (meetingId) => request(`/meetings/${meetingId}/transcript`),

  getDrafts: (projectId, status = 'waiting') =>
    request(`/projects/${projectId}/drafts${status ? `?status=${status}` : ''}`),
  approveDraft: (draftId, approverName, editedPayload = null) =>
    request(`/drafts/${draftId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approver_name: approverName, edited_payload: editedPayload }),
    }),
  rejectDraft: (draftId, approverName) =>
    request(`/drafts/${draftId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ approver_name: approverName }),
    }),
  batchApproveDrafts: (projectId, draftIds, approverName) =>
    request(`/projects/${projectId}/drafts/batch-approve`, {
      method: 'POST',
      body: JSON.stringify({ draft_ids: draftIds, approver_name: approverName }),
    }),

  getAuditHistory: (projectId) => request(`/projects/${projectId}/audit-history`),
  retryJiraSync: (auditId) => request(`/audit-history/${auditId}/retry-jira`, { method: 'POST' }),

  updateActionItemStatus: (itemId, status) =>
    request(`/action-items/${itemId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),

  getConnections: (projectId) =>
    request(`/admin/connections${projectId ? `?project_id=${projectId}` : ''}`),
};
