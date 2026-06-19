import React, { useState, useEffect, useRef } from 'react';
import {
  Mic,
  Square,
  Search,
  CheckCircle,
  Clock,
  Trash2,
  Calendar,
  Mail,
  AlertTriangle,
  Play,
  ListTodo,
  ExternalLink,
  Users,
  Award,
  Sparkles,
  Info,
  Check,
  X,
  Plus
} from 'lucide-react';

const API_BASE = 'http://localhost:8000/api';
// In dev, vite proxy sends /ws to backend, so just hit /ws/stt
const WS_PATH = '/ws/stt';

export default function App() {
  const [meetings, setMeetings] = useState([]);
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [meetingSegments, setMeetingSegments] = useState([]);
  const [actionItems, setActionItems] = useState([]);
  const [approvals, setApprovals] = useState([]);
  
  // Recording states
  const [isRecording, setIsRecording] = useState(false);
  const [recordingMeetingId, setRecordingMeetingId] = useState(null);
  const [liveTranscript, setLiveTranscript] = useState([]);
  
  // Search states
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResponse] = useState(null);
  const [isSearching, setIsSearching] = useState(false);

  // Audio Context Ref for streaming
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);
  const streamRef = useRef(null);
  const wsRef = useRef(null);

  // Load meeting list on boot
  useEffect(() => {
    fetchMeetings();
  }, []);

  // Poll for meeting status changes & approvals when a meeting is selected
  useEffect(() => {
    let interval;
    if (selectedMeeting) {
      fetchMeetingDetails(selectedMeeting.id);
      interval = setInterval(() => {
        fetchMeetingDetails(selectedMeeting.id, true);
      }, 4000);
    }
    return () => clearInterval(interval);
  }, [selectedMeeting?.id]);

  const fetchMeetings = async () => {
    try {
      const res = await fetch(`${API_BASE}/meetings`);
      if (!res.ok) {
        console.error(`Failed to load meetings: ${res.status} ${res.statusText}`);
        return;
      }
      const data = await res.json();
      setMeetings(data);
    } catch (e) {
      console.error('Failed to load meetings', e);
    }
  };

  const fetchMeetingDetails = async (id, silent = false) => {
    try {
      if (!silent) {
        // Only trigger visual loaders for non-polling refreshes
      }
      const [mRes, segRes, actRes, appRes] = await Promise.all([
        fetch(`${API_BASE}/meetings/${id}`),
        fetch(`${API_BASE}/meetings/${id}/segments`),
        fetch(`${API_BASE}/meetings/${id}/action-items`),
        fetch(`${API_BASE}/meetings/${id}/approvals`)
      ]);

      if (!mRes.ok) {
        console.error(`Failed to load meeting ${id}: ${mRes.status} ${mRes.statusText}`);
        return;
      }

      const meeting = await mRes.json();
      const segments = segRes.ok ? await segRes.json() : [];
      const actions = actRes.ok ? await actRes.json() : [];
      const apps = appRes.ok ? await appRes.json() : [];

      if (!segRes.ok) console.error(`Failed to load segments: ${segRes.status}`);
      if (!actRes.ok) console.error(`Failed to load action items: ${actRes.status}`);
      if (!appRes.ok) console.error(`Failed to load approvals: ${appRes.status}`);

      setSelectedMeeting(meeting);
      setMeetingSegments(segments);
      setActionItems(actions);
      setApprovals(apps);

      // Refresh list to capture status transitions (e.g. from processing to completed)
      fetchMeetings();
    } catch (e) {
      console.error('Failed to load details', e);
    }
  };

  const startNewMeeting = async () => {
    try {
      const res = await fetch(`${API_BASE}/meetings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: `Meeting - ${new Date().toLocaleTimeString()}` })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        console.error('Failed to create meeting:', err.detail || res.statusText);
        alert(`Failed to create meeting: ${err.detail || res.statusText}`);
        return;
      }
      const meeting = await res.json();
      
      setMeetings([meeting, ...meetings]);
      setSelectedMeeting(meeting);
      setRecordingMeetingId(meeting.id);
      setLiveTranscript([]);
      setMeetingSegments([]);
      setActionItems([]);
      setApprovals([]);
      
      // Start browser audio capture
      await startAudioStreaming(meeting.id);
    } catch (e) {
      console.error('Error starting meeting', e);
    }
  };

  const startAudioStreaming = async (meetingId) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      streamRef.current = stream;

      // Init WebSocket
      const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + WS_PATH;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('STT WebSocket connected');
        setIsRecording(true);
        // Handshake
        ws.send(JSON.stringify({ meeting_id: meetingId }));
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.status === 'ready') {
            console.log('WS ready for audio for meeting', msg.meeting_id);
            return;
          }
          if (msg.text) {
            setLiveTranscript((prev) => [...prev, msg]);
            setMeetingSegments((prev) => [...prev, msg]);
          }
        } catch (e) {
          console.warn('Non-JSON WS message', event.data);
        }
      };

      ws.onerror = (e) => console.error('WS Error:', e);
      ws.onclose = () => {
        console.log('WS Connection closed');
        setIsRecording(false);
      };

      // Set up Audio Context downsampler to 16kHz mono 16-bit PCM
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      // Buffer size of 4096 samples
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        
        const inputData = e.inputBuffer.getChannelData(0);
        // Downsample / convert float32 to int16 (PCM 16bit)
        const l = inputData.length;
        const buf = new Int16Array(l);
        for (let i = 0; i < l; i++) {
          let s = Math.max(-1, Math.min(1, inputData[i]));
          buf[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        ws.send(buf.buffer);
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

    } catch (e) {
      console.error('Failed to init mic streaming:', e);
      alert('Mic permission or device error: please allow microphone access and try again. Falling back to mock transcript.');
      // Simple mock recording periodic segment addition
      setIsRecording(true);
      const mockInterval = setInterval(() => {
        if (!isRecording) {
          clearInterval(mockInterval);
          return;
        }
        const mockTexts = [
          "Let's finalize our Q3 budget alignment meeting.",
          "Sarah, please ensure you update the Notion tracker for engineering milestones.",
          "I will schedule a calendar sync for next Monday at 10 AM UTC to align on team hiring plans.",
          "We decided to delay the marketing campaign until our main SDK build succeeds."
        ];
        const randomText = mockTexts[Math.floor(Math.random() * mockTexts.length)];
        const mockSegment = {
          speaker: "Speaker 1",
          start_ms: 0,
          end_ms: 1000,
          text: randomText,
          is_final: true
        };
        // Post mock segment to DB via simulated HTTP or state
        setLiveTranscript((prev) => [...prev, mockSegment]);
        setMeetingSegments((prev) => [...prev, mockSegment]);
      }, 5000);
      processorRef.current = { mockInterval }; // holder to clear
    }
  };

  const stopRecording = async () => {
    setIsRecording(false);
    
    // Clear audio capture
    if (processorRef.current) {
      if (processorRef.current.mockInterval) {
        clearInterval(processorRef.current.mockInterval);
      } else {
        processorRef.current.disconnect();
      }
    }
    if (audioContextRef.current) {
      await audioContextRef.current.close();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
    }
    if (wsRef.current) {
      wsRef.current.close();
    }

    const currentMeetingId = recordingMeetingId;
    setRecordingMeetingId(null);

    if (currentMeetingId) {
      // Finalize transcription & run agents in backend
      try {
        const finRes = await fetch(`${API_BASE}/meetings/${currentMeetingId}/finalize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        if (!finRes.ok) {
          const err = await finRes.json().catch(() => ({}));
          console.error('Error finalizing meeting:', err.detail || finRes.statusText);
          alert(`Error finalizing meeting: ${err.detail || finRes.statusText}`);
        }
        fetchMeetingDetails(currentMeetingId);
      } catch (e) {
        console.error('Error finalising meeting', e);
      }
    }
  };

  const deleteMeeting = async (id) => {
    if (!confirm('Are you sure you want to delete this meeting?')) return;
    try {
      const delRes = await fetch(`${API_BASE}/meetings/${id}`, { method: 'DELETE' });
      if (!delRes.ok) {
        const err = await delRes.json().catch(() => ({}));
        console.error('Failed to delete meeting:', err.detail || delRes.statusText);
        alert(`Failed to delete meeting: ${err.detail || delRes.statusText}`);
        return;
      }
      setMeetings(meetings.filter(m => m.id !== id));
      if (selectedMeeting?.id === id) {
        setSelectedMeeting(null);
      }
    } catch (e) {
      console.error('Error deleting meeting', e);
    }
  };

  const handleApprovalAction = async (approvalId, action) => {
    try {
      const res = await fetch(`${API_BASE}/approvals/${approvalId}/action?action=${action}`, {
        method: 'POST'
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(`Approval action failed: ${err.detail || res.statusText}`);
        return;
      }
      const data = await res.json();
      if (data.success) {
        // reload approvals
        if (selectedMeeting) {
          fetchMeetingDetails(selectedMeeting.id, true);
        }
      } else {
        alert(`Action execution failed: ${data.message || 'unknown error'}`);
      }
    } catch (e) {
      console.error('Error triggering approval action', e);
    }
  };

  const executeSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery || !searchQuery.trim()) return;
    setIsSearching(true);
    try {
      const res = await fetch(`${API_BASE}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery, top_k: 6 })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        console.error('Search failed:', err.detail || res.statusText);
        alert(`Search failed: ${err.detail || res.statusText}`);
        return;
      }
      const data = await res.json();
      setSearchResponse(data);
    } catch (e) {
      console.error('Search failed', e);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 text-slate-900 font-sans overflow-hidden">
      {/* LEFT SIDEBAR: MEETINGS LIST */}
      <div className="w-80 border-r border-slate-200 bg-white flex flex-col h-full shrink-0">
        <div className="p-4 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-indigo-600 animate-pulse" />
            <h1 className="font-bold text-lg tracking-tight">Meeting Intel</h1>
          </div>
          {isRecording ? (
            <button
              onClick={stopRecording}
              className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-full flex items-center justify-center shadow-lg shadow-red-200 transition-all"
              title="Stop Recording"
            >
              <Square className="w-4 h-4 fill-current" />
            </button>
          ) : (
            <button
              onClick={startNewMeeting}
              className="bg-indigo-600 hover:bg-indigo-700 text-white p-2 rounded-full flex items-center justify-center shadow-lg shadow-indigo-100 transition-all"
              title="Start New Meeting"
            >
              <Mic className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Live meeting status alert */}
        {isRecording && (
          <div className="m-3 p-3 bg-red-50 border border-red-100 rounded-lg flex items-center gap-3 animate-pulse">
            <span className="w-3 h-3 rounded-full bg-red-500 block shrink-0" />
            <div className="text-xs text-red-700">
              <span className="font-semibold block">Recording Live...</span>
              Speak now to stream 16kHz PCM
            </div>
          </div>
        )}

        {/* Meetings List */}
        <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
          {meetings.map((m) => {
            const isSelected = selectedMeeting?.id === m.id;
            return (
              <div
                key={m.id}
                onClick={() => fetchMeetingDetails(m.id)}
                className={`p-4 cursor-pointer hover:bg-slate-50 transition-all ${
                  isSelected ? 'bg-indigo-50/50 border-l-4 border-indigo-600' : ''
                }`}
              >
                <div className="flex justify-between items-start gap-2">
                  <h3 className={`font-semibold text-sm ${isSelected ? 'text-indigo-900' : 'text-slate-800'}`}>
                    {m.title}
                  </h3>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteMeeting(m.id);
                    }}
                    className="text-slate-400 hover:text-red-500 p-1"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-slate-400 text-[11px] flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {new Date(m.started_at).toLocaleDateString()}
                  </span>
                  
                  {/* Badge status */}
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                      m.status === 'completed'
                        ? 'bg-emerald-50 text-emerald-700'
                        : m.status === 'processing'
                        ? 'bg-amber-50 text-amber-700 animate-pulse'
                        : 'bg-indigo-50 text-indigo-700'
                    }`}
                  >
                    {m.status}
                  </span>
                </div>
              </div>
            );
          })}
          {meetings.length === 0 && (
            <div className="p-8 text-center text-slate-400 text-sm">
              No meetings recorded yet. Click the microphone icon to begin!
            </div>
          )}
        </div>
      </div>

      {/* CENTRAL AREA & TABS */}
      <div className="flex-1 flex flex-col h-full bg-slate-50 overflow-hidden">
        {/* TOP BAR / SEARCH BAR */}
        <div className="h-16 border-b border-slate-200 bg-white px-6 flex items-center justify-between">
          <form onSubmit={executeSearch} className="flex-1 max-w-xl relative">
            <input
              type="text"
              placeholder="Hybrid search across meetings: e.g. 'budget discussion'"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg text-sm bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            />
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          </form>

          <div className="flex items-center gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              Qdrant Online
            </span>
          </div>
        </div>

        {/* MAIN SPLIT VIEW */}
        <div className="flex-1 flex overflow-hidden">
          {searchResults ? (
            /* SEARCH CONSOLE VIEW */
            <div className="flex-1 p-6 overflow-y-auto max-w-5xl mx-auto w-full">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-xl font-bold flex items-center gap-2">
                    Search Results for: <span className="text-indigo-600 italic">"{searchQuery}"</span>
                  </h2>
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-xs font-semibold bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full uppercase tracking-wider">
                      Intent: {searchResults.intent.intent} ({Math.round(searchResults.intent.confidence * 100)}%)
                    </span>
                    <span className="text-slate-400 text-xs">
                      Rationale: {searchResults.intent.rationale}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => setSearchResponse(null)}
                  className="text-slate-500 hover:text-slate-900 text-sm font-semibold border border-slate-200 px-3 py-1.5 rounded-lg bg-white"
                >
                  Back to Dashboard
                </button>
              </div>

              {/* Amplified queries tags */}
              {searchResults.expanded_queries.length > 1 && (
                <div className="bg-white border border-slate-200 rounded-xl p-4 mb-6">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                    Multi-Query Amplification
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {searchResults.expanded_queries.map((q, idx) => (
                      <span key={idx} className="bg-slate-50 text-slate-600 text-xs px-2.5 py-1 rounded-md border border-slate-200">
                        {q}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Hit blocks */}
              <div className="space-y-4">
                {searchResults.hits.map((hit, idx) => (
                  <div
                    key={idx}
                    onClick={() => {
                      // Lookup this meeting in list & detail
                      const match = meetings.find(m => m.id === hit.meeting_id);
                      if (match) {
                        fetchMeetingDetails(match.id);
                        setSearchResponse(null);
                      }
                    }}
                    className="bg-white border border-slate-200 hover:border-indigo-300 rounded-xl p-5 cursor-pointer transition-all shadow-sm hover:shadow-md"
                  >
                    <div className="flex justify-between items-start gap-4">
                      <div>
                        <h3 className="font-bold text-slate-900 group-hover:text-indigo-600">
                          {hit.title || 'Untitled Meeting'}
                        </h3>
                        <p className="text-xs text-slate-400 mt-1">
                          Recorded {hit.started_at ? new Date(hit.started_at).toLocaleDateString() : ''}
                        </p>
                      </div>
                      <span className="bg-emerald-50 text-emerald-700 text-xs font-semibold px-2.5 py-1 rounded-md border border-emerald-100 flex items-center gap-1">
                        Score: {Math.round(hit.score * 100)}%
                      </span>
                    </div>
                    <div className="mt-4 bg-slate-50 p-3 rounded-lg border border-slate-100 text-sm text-slate-700 leading-relaxed italic">
                      "... {hit.text} ..."
                    </div>
                  </div>
                ))}
                {searchResults.hits.length === 0 && (
                  <div className="text-center p-12 bg-white border border-slate-200 rounded-xl">
                    <Info className="w-8 h-8 text-slate-300 mx-auto mb-3" />
                    <p className="text-slate-500 text-sm font-medium">No results found matching your query.</p>
                  </div>
                )}
              </div>
            </div>
          ) : selectedMeeting ? (
            /* DETAILED MEETING WORKFLOW PANELS */
            <div className="flex-1 flex overflow-hidden">
              
              {/* PANELS LEFT: TRANSCRIPT & DISCUSSIONS */}
              <div className="flex-1 flex flex-col h-full bg-white border-r border-slate-200 overflow-y-auto p-6">
                <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-4">
                  <div>
                    <h2 className="text-lg font-bold text-slate-900">{selectedMeeting.title}</h2>
                    <p className="text-xs text-slate-400 mt-1">
                      Status: <span className="font-semibold capitalize text-indigo-600">{selectedMeeting.status}</span>
                    </p>
                  </div>
                </div>

                {/* Speaker roster */}
                {selectedMeeting.participants && selectedMeeting.participants.length > 0 && (
                  <div className="mb-6">
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <Users className="w-3.5 h-3.5" />
                      Participants
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {selectedMeeting.participants.map((p, idx) => (
                        <span key={idx} className="bg-slate-100 text-slate-700 text-xs px-2.5 py-1 rounded-full font-medium">
                          {p}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Live Transcript / Segments Feed */}
                <div className="space-y-4">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider border-b border-slate-100 pb-1.5">
                    Transcript Segments
                  </h4>
                  {meetingSegments.map((seg, idx) => (
                    <div key={idx} className="flex gap-4 items-start hover:bg-slate-50/50 p-2 rounded-lg transition-all">
                      <div className="w-24 shrink-0 text-xs font-semibold text-slate-400">
                        {seg.speaker || 'Speaker'}
                      </div>
                      <div className="flex-1 text-sm text-slate-700 leading-relaxed">
                        {seg.text}
                      </div>
                    </div>
                  ))}
                  {meetingSegments.length === 0 && (
                    <div className="p-8 text-center text-slate-400 text-sm">
                      {selectedMeeting.status === 'recording' ? 'Say something! Waiting for streaming audio buffers...' : 'No segments available.'}
                    </div>
                  )}
                </div>
              </div>

              {/* PANELS RIGHT: MULTI-AGENT SUMMARY, DECISIONS, & ACTION ITEMS APPROVAL QUEUE */}
              <div className="w-[420px] bg-slate-50/50 flex flex-col h-full shrink-0 overflow-y-auto p-6 border-l border-slate-100">
                
                {/* 1. NARRATIVE SUMMARY */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-6">
                  <h3 className="font-bold text-sm text-slate-900 flex items-center gap-1.5 border-b border-slate-100 pb-2 mb-3">
                    <Sparkles className="w-4 h-4 text-indigo-600" />
                    Agent 3: Meeting Summary
                  </h3>
                  {selectedMeeting.status === 'processing' ? (
                    <div className="py-4 text-center text-slate-400 text-xs animate-pulse">
                      Synthesizing meeting summary with executive agents...
                    </div>
                  ) : selectedMeeting.summary ? (
                    <p className="text-xs text-slate-600 leading-relaxed">{selectedMeeting.summary}</p>
                  ) : (
                    <div className="text-xs text-slate-400 py-3 italic flex items-center gap-2">
                      <Info className="w-4 h-4 text-slate-400 shrink-0" />
                      Ready to synthesize summary. Complete/finalize recording to trigger agents.
                    </div>
                  )}
                </div>

                {/* 2. CORE DECISIONS */}
                {selectedMeeting.key_decisions && selectedMeeting.key_decisions.length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-6">
                    <h3 className="font-bold text-sm text-slate-900 flex items-center gap-1.5 border-b border-slate-100 pb-2 mb-3">
                      <Award className="w-4 h-4 text-emerald-600" />
                      Key Decisions
                    </h3>
                    <ul className="space-y-2">
                      {selectedMeeting.key_decisions.map((dec, idx) => (
                        <li key={idx} className="text-xs text-slate-700 flex gap-2 items-start leading-relaxed">
                          <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                          <span>{dec}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 3. STAGED ACTION ITEMS & APPROVALS QUEUE */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                  <h3 className="font-bold text-sm text-slate-900 flex items-center gap-1.5 border-b border-slate-100 pb-2 mb-3">
                    <ListTodo className="w-4 h-4 text-indigo-600" />
                    Autonomous Actions Queue
                  </h3>
                  
                  <div className="space-y-3.5">
                    {approvals.map((app) => {
                      const isPending = app.status === 'pending';
                      const isExecuted = app.status === 'executed';
                      return (
                        <div
                          key={app.id}
                          className={`border rounded-lg p-3.5 transition-all ${
                            isExecuted
                              ? 'bg-emerald-50/50 border-emerald-100'
                              : app.status === 'rejected'
                              ? 'bg-slate-100/50 border-slate-200 opacity-60'
                              : 'bg-white border-slate-200 shadow-sm'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 flex items-center gap-1">
                              {app.tool_name === 'add_to_todoist' ? (
                                <>
                                  <ListTodo className="w-3.5 h-3.5 text-red-500" />
                                  Todoist Task
                                </>
                              ) : (
                                <>
                                  <Mail className="w-3.5 h-3.5 text-indigo-500" />
                                  Gmail Summary
                                </>
                              )}
                            </span>
                            <span
                              className={`text-[9px] px-1.5 py-0.5 rounded font-bold capitalize ${
                                isExecuted
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : isPending
                                  ? 'bg-blue-50 text-blue-700 animate-pulse'
                                  : 'bg-slate-200 text-slate-700'
                              }`}
                            >
                              {app.status}
                            </span>
                          </div>

                          <div className="mt-2 text-xs text-slate-700 font-medium">
                            {app.payload.task || app.payload.subject || 'Meeting action'}
                          </div>

                          {isPending && (
                            <div className="flex gap-2 mt-3.5 border-t border-slate-100 pt-3">
                              <button
                                onClick={() => handleApprovalAction(app.id, 'approve')}
                                className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold py-1.5 px-2 rounded-md flex items-center justify-center gap-1 shadow-sm"
                              >
                                <Check className="w-3.5 h-3.5" /> Approve
                              </button>
                              <button
                                onClick={() => handleApprovalAction(app.id, 'reject')}
                                className="flex-1 bg-white hover:bg-slate-50 text-slate-600 border border-slate-200 text-xs font-semibold py-1.5 px-2 rounded-md flex items-center justify-center gap-1"
                              >
                                <X className="w-3.5 h-3.5" /> Reject
                              </button>
                            </div>
                          )}

                          {isExecuted && (
                            <div className="mt-2 text-[10px] text-emerald-700 font-semibold flex items-center gap-1 bg-emerald-100/50 p-1.5 rounded border border-emerald-200/50">
                              <Check className="w-3 h-3 text-emerald-600 shrink-0" />
                              Action successfully processed in workspace!
                            </div>
                          )}
                        </div>
                      );
                    })}

                    {approvals.length === 0 && (
                      <div className="text-center py-6 text-slate-400 text-xs">
                        No autonomous action items to approve.
                      </div>
                    )}
                  </div>
                </div>

              </div>
            </div>
          ) : (
            /* EMPTY INITIAL VIEW / SELECT MEETING */
            <div className="flex-1 flex flex-col items-center justify-center text-slate-400 p-12">
              <Sparkles className="w-12 h-12 text-indigo-200 mb-4 animate-bounce" />
              <h3 className="font-bold text-lg text-slate-700 mb-1">Welcome to Meeting Intelligence</h3>
              <p className="text-sm max-w-md text-center text-slate-500 leading-relaxed">
                Select an existing meeting from the left sidebar to view its summaries, transcripts, and staged autonomous tasks, or start recording a new session.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
