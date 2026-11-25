import React, { useEffect, useState } from 'react';
import { X, MessageSquareQuote, Lock } from 'lucide-react';
import { api } from '../api';

export default function TranscriptDrawer({ meetingId, highlightLines = [], onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!meetingId) return;
    setLoading(true);
    api.getTranscript(meetingId)
      .then((res) => setData(res))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, [meetingId]);

  if (!meetingId) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40 backdrop-blur-xs">
      <div className="w-full max-w-xl bg-white h-full shadow-2xl flex flex-col border-l border-slate-200">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-2">
            <MessageSquareQuote className="w-5 h-5 text-indigo-600" />
            <div>
              <h3 className="font-semibold text-slate-900">Source Transcript Citation</h3>
              <p className="text-xs text-slate-500">
                {data?.meeting_title || 'Loading...'} • Highlighted lines: {highlightLines.join(', ')}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-2">
          {loading ? (
            <p className="text-sm text-slate-500">Loading transcript lines...</p>
          ) : data?.is_private ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-slate-500">
              <Lock className="w-10 h-10 mb-3 text-amber-500" />
              <p className="font-medium text-slate-800">Private Meeting</p>
              <p className="text-sm mt-1">Transcript was never read or stored per privacy policy.</p>
            </div>
          ) : (
            data?.lines?.map((line) => {
              const isHighlighted = highlightLines.includes(line.line_number);
              return (
                <div
                  key={line.line_number}
                  className={`p-3 rounded-lg border text-sm transition ${
                    isHighlighted
                      ? 'bg-amber-50 border-amber-300 ring-2 ring-amber-200'
                      : 'bg-white border-slate-100 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                      L{line.line_number}
                    </span>
                    <span className="font-semibold text-slate-800">{line.speaker}</span>
                    {line.timestamp && (
                      <span className="text-xs text-slate-400">{line.timestamp}</span>
                    )}
                    {isHighlighted && (
                      <span className="ml-auto text-[11px] font-semibold uppercase tracking-wide text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                        Cited Source
                      </span>
                    )}
                  </div>
                  <p className="text-slate-700 leading-relaxed">{line.text}</p>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
