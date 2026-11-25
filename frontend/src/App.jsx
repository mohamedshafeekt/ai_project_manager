import React, { useEffect, useState, useCallback } from 'react';
import {
  Bot,
  ClipboardCheck,
  UserCheck,
  BarChart3,
  Settings,
  RefreshCw,
} from 'lucide-react';
import { api } from './api';
import PMView from './views/PMView';
import MemberView from './views/MemberView';
import SponsorView from './views/SponsorView';
import AdminView from './views/AdminView';
import TranscriptDrawer from './components/TranscriptDrawer';

const ROLES = [
  { id: 'pm', label: 'Project Manager', icon: ClipboardCheck },
  { id: 'member', label: 'Team Member', icon: UserCheck },
  { id: 'sponsor', label: 'Sponsor', icon: BarChart3 },
  { id: 'admin', label: 'Admin', icon: Settings },
];

export default function App() {
  const [role, setRole] = useState('pm');
  const [projects, setProjects] = useState([]);
  const [activeProject, setActiveProject] = useState(null);

  const [drafts, setDrafts] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [auditHistory, setAuditHistory] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);

  const [drawerState, setDrawerState] = useState({ meetingId: null, lines: [] });

  const loadAll = useCallback(async (projectId) => {
    try {
      const [d, m, a, dash] = await Promise.all([
        api.getDrafts(projectId, 'waiting'),
        api.getMeetings(projectId),
        api.getAuditHistory(projectId),
        api.getDashboard(projectId),
      ]);
      setDrafts(d);
      setMeetings(m);
      setAuditHistory(a);
      setDashboard(dash);
    } catch (err) {
      console.error('Failed to load project data:', err);
    }
  }, []);

  const init = useCallback(async () => {
    setLoading(true);
    try {
      const projs = await api.getProjects();
      setProjects(projs);
      if (projs.length > 0) {
        setActiveProject(projs[0]);
        await loadAll(projs[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch projects:', err);
    } finally {
      setLoading(false);
    }
  }, [loadAll]);

  useEffect(() => {
    init();
  }, [init]);

  const handleRefresh = async () => {
    if (!activeProject) return;
    const projs = await api.getProjects();
    const updated = projs.find((p) => p.id === activeProject.id) || projs[0];
    setProjects(projs);
    setActiveProject(updated);
    await loadAll(updated.id);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* Top Navbar */}
      <header className="sticky top-0 z-30 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-600 text-white flex items-center justify-center shadow-xs">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-slate-900 leading-tight">
                AI Project Manager
              </h1>
              <p className="text-[11px] text-slate-500">
                {activeProject ? `${activeProject.name} (${activeProject.jira_project_key})` : 'Loading...'}
              </p>
            </div>
          </div>

          {/* 4-Role View Switcher */}
          <nav className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl">
            {ROLES.map((r) => {
              const Icon = r.icon;
              const isActive = role === r.id;
              return (
                <button
                  key={r.id}
                  onClick={() => setRole(r.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition ${
                    isActive
                      ? 'bg-white text-indigo-700 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">{r.label}</span>
                  {r.id === 'pm' && drafts.length > 0 && (
                    <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-indigo-600 text-white">
                      {drafts.length}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          <button
            onClick={handleRefresh}
            className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition"
            title="Refresh live data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {loading ? (
          <div className="text-center py-20 text-slate-500 text-sm">
            Connecting to FastAPI backend and Neon PostgreSQL...
          </div>
        ) : !activeProject ? (
          <div className="text-center py-20 text-rose-600 text-sm">
            No project found. Run <code>uv run init_database.py</code> to seed the default project.
          </div>
        ) : (
          <>
            {role === 'pm' && (
              <PMView
                project={activeProject}
                drafts={drafts}
                meetings={meetings}
                auditHistory={auditHistory}
                onRefresh={handleRefresh}
                onOpenTranscript={(meetingId, lines) =>
                  setDrawerState({ meetingId, lines })
                }
              />
            )}
            {role === 'member' && (
              <MemberView dashboard={dashboard} onRefresh={handleRefresh} />
            )}
            {role === 'sponsor' && (
              <SponsorView project={activeProject} dashboard={dashboard} />
            )}
            {role === 'admin' && (
              <AdminView project={activeProject} onRefresh={handleRefresh} />
            )}
          </>
        )}
      </main>

      {/* Transcript Citation Drawer */}
      <TranscriptDrawer
        meetingId={drawerState.meetingId}
        highlightLines={drawerState.lines}
        onClose={() => setDrawerState({ meetingId: null, lines: [] })}
      />
    </div>
  );
}
