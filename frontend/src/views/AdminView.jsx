import React, { useEffect, useState } from 'react';
import { Server, CheckCircle2, XCircle, Save, Users, Wrench } from 'lucide-react';
import { api } from '../api';

export default function AdminView({ project, onRefresh }) {
  const [connections, setConnections] = useState(null);
  const [scope, setScope] = useState(project?.agreed_scope || '');
  const [jiraKey, setJiraKey] = useState(project?.jira_project_key || 'APM');
  const [githubRepo, setGithubRepo] = useState(project?.github_repo || '');
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');

  useEffect(() => {
    if (project) {
      setScope(project.agreed_scope || '');
      setJiraKey(project.jira_project_key || 'APM');
      setGithubRepo(project.github_repo || '');
      api.getConnections(project.id).then(setConnections).catch(console.error);
    }
  }, [project]);

  const handleSaveConfig = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.updateProject(project.id, {
        agreed_scope: scope,
        jira_project_key: jiraKey,
        github_repo: githubRepo,
      });
      setSavedMsg('Project configuration saved!');
      setTimeout(() => setSavedMsg(''), 3000);
      onRefresh();
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Connected MCP Systems */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Server className="w-5 h-5 text-indigo-600" />
          Connected Systems & MCP Connectors
        </h2>

        {!connections ? (
          <p className="text-xs text-slate-500">Checking live connector health...</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { name: 'Jira Cloud (MCP)', data: connections.jira },
              { name: 'GitHub (MCP)', data: connections.github },
              { name: 'Teams / Transcripts', data: connections.teams_upload },
            ].map((sys) => (
              <div key={sys.name} className="p-4 rounded-xl border border-slate-200 bg-slate-50">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm text-slate-900">{sys.name}</span>
                  {sys.data?.connected ? (
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Live
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-700 bg-rose-100 px-2 py-0.5 rounded-full">
                      <XCircle className="w-3.5 h-3.5" />
                      Error
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-600 mb-3">{sys.data?.details}</p>
                {sys.data?.tools && (
                  <div className="space-y-1 pt-2 border-t border-slate-200">
                    <p className="text-[10px] font-semibold uppercase text-slate-400 flex items-center gap-1">
                      <Wrench className="w-3 h-3" />
                      Exposed MCP Tools
                    </p>
                    {sys.data.tools.map((t) => (
                      <p key={t.name} className="text-[11px] font-mono text-slate-700">
                        • {t.name}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. Agreed Scope Baseline & Connector Settings */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
        <h3 className="font-semibold text-slate-900 mb-1">Project Configuration & Agreed Scope Baseline</h3>
        <p className="text-xs text-slate-500 mb-4">
          The Scope Change Agent compares every meeting transcript against this baseline to flag scope creep.
        </p>

        <form onSubmit={handleSaveConfig} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Jira Project Key</label>
              <input
                type="text"
                value={jiraKey}
                onChange={(e) => setJiraKey(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">GitHub Repository (owner/repo)</label>
              <input
                type="text"
                value={githubRepo}
                onChange={(e) => setGithubRepo(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Agreed Scope Baseline</label>
            <textarea
              rows={7}
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              className="w-full px-3 py-2 text-xs font-mono border border-slate-200 rounded-lg"
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 flex items-center gap-1.5"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving...' : 'Save Configuration'}
            </button>
            {savedMsg && <span className="text-xs text-emerald-600 font-medium">{savedMsg}</span>}
          </div>
        </form>
      </div>

      {/* 3. Project Members */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
        <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
          <Users className="w-4 h-4 text-slate-500" />
          Project Members & Roles
        </h3>
        <div className="divide-y divide-slate-100">
          {(project?.members || []).map((m) => (
            <div key={m.id} className="py-2.5 flex items-center justify-between text-sm">
              <div>
                <p className="font-medium text-slate-800">{m.name}</p>
                <p className="text-xs text-slate-500">{m.email}</p>
              </div>
              <span className="text-xs font-semibold uppercase px-2.5 py-1 rounded-full bg-slate-100 text-slate-700">
                {m.role.replace('_', ' ')}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
