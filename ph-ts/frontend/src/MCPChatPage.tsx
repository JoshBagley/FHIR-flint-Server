/**
 * MCPChatPage — standalone FHIR MCP chat test page.
 *
 * Backed by POST /mcp-chat/chat which runs an agentic AI loop using
 * xSoVx/fhir-mcp–style tools (fhir_capabilities, fhir_search, fhir_read,
 * terminology_lookup, terminology_expand, terminology_translate).
 *
 * Each AI response that involved tool calls shows an expandable "Tool Trace"
 * section so you can see exactly which FHIR operations were executed.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  ArrowLeft, Send, Loader2, ChevronDown, ChevronUp,
  MessageSquare, Wrench, Zap, AlertCircle, RotateCcw,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
  result: unknown;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCall[];
  provider?: string;
  model?: string;
  error?: boolean;
}

interface McpTool {
  name: string;
  description: string;
}

interface ProviderInfo {
  provider: string;
  model: string;
  configured: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function uid(): string {
  return Math.random().toString(36).slice(2);
}

const TOOL_COLORS: Record<string, string> = {
  fhir_capabilities:    'bg-indigo-100 text-indigo-700 border-indigo-200',
  fhir_search:          'bg-blue-100 text-blue-700 border-blue-200',
  fhir_read:            'bg-cyan-100 text-cyan-700 border-cyan-200',
  terminology_lookup:   'bg-emerald-100 text-emerald-700 border-emerald-200',
  terminology_expand:   'bg-teal-100 text-teal-700 border-teal-200',
  terminology_translate:'bg-purple-100 text-purple-700 border-purple-200',
};

const STARTER_PROMPTS = [
  'How many ValueSets does this server have?',
  'Find ValueSets related to COVID-19',
  'Expand the ValueSet for race and ethnicity codes',
  'Look up SNOMED code 840539006',
  'Search for CodeSystems with status active',
  'What FHIR operations does this server support?',
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProviderBadge({ info }: { info: ProviderInfo | null }) {
  if (!info) return null;
  const colour = info.configured
    ? 'bg-green-100 text-green-700 border-green-200'
    : 'bg-red-100 text-red-700 border-red-200';
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${colour}`}>
      <Zap className="w-3 h-3" />
      {info.provider} / {info.model}
    </span>
  );
}

function ToolChip({ name }: { name: string }) {
  const cls = TOOL_COLORS[name] ?? 'bg-gray-100 text-gray-700 border-gray-200';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono font-medium rounded border ${cls}`}>
      <Wrench className="w-3 h-3" />
      {name}
    </span>
  );
}

function ToolTrace({ calls }: { calls: ToolCall[] }) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const toggle = (i: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  };

  return (
    <div className="mt-2 border border-gray-200 rounded-lg overflow-hidden text-xs">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <span className="flex items-center gap-2 font-medium text-gray-600">
          <Wrench className="w-3 h-3" />
          {calls.length} tool call{calls.length !== 1 ? 's' : ''}
        </span>
        {open
          ? <ChevronUp className="w-3.5 h-3.5 text-gray-400" />
          : <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
        }
      </button>

      {open && (
        <div className="divide-y divide-gray-100 bg-white">
          {calls.map((tc, i) => (
            <div key={i}>
              {/* Call header */}
              <button
                onClick={() => toggle(i)}
                className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-50 transition-colors text-left"
              >
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gray-200 text-gray-500 flex items-center justify-center font-semibold">
                  {i + 1}
                </span>
                <ToolChip name={tc.tool} />
                <span className="text-gray-400 truncate flex-1 font-mono">
                  {Object.entries(tc.args)
                    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                    .join(', ')}
                </span>
                {expanded.has(i)
                  ? <ChevronUp className="w-3 h-3 text-gray-400 flex-shrink-0" />
                  : <ChevronDown className="w-3 h-3 text-gray-400 flex-shrink-0" />
                }
              </button>

              {/* Expanded detail: args + result */}
              {expanded.has(i) && (
                <div className="px-3 pb-3 space-y-2">
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase mb-1">Input</p>
                    <pre className="bg-gray-50 rounded p-2 text-xs font-mono overflow-x-auto whitespace-pre-wrap break-all">
                      {JSON.stringify(tc.args, null, 2)}
                    </pre>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase mb-1">Result</p>
                    <pre className="bg-gray-50 rounded p-2 text-xs font-mono overflow-x-auto whitespace-pre-wrap break-all max-h-64">
                      {JSON.stringify(tc.result, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm whitespace-pre-wrap">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 max-w-[85%]">
      {/* Assistant bubble */}
      <div className={`rounded-2xl rounded-tl-sm px-4 py-3 text-sm whitespace-pre-wrap ${
        msg.error
          ? 'bg-red-50 text-red-700 border border-red-200'
          : 'bg-white border border-gray-200 text-gray-800 shadow-sm'
      }`}>
        {msg.error && <AlertCircle className="w-4 h-4 inline mr-1.5 -mt-0.5" />}
        {msg.content}
      </div>

      {/* Tool trace */}
      {msg.toolCalls && msg.toolCalls.length > 0 && (
        <ToolTrace calls={msg.toolCalls} />
      )}

      {/* Provider/model stamp */}
      {msg.provider && (
        <p className="text-xs text-gray-400 pl-1">
          {msg.provider} / {msg.model}
        </p>
      )}
    </div>
  );
}

function ToolSidebar({ tools }: { tools: McpTool[] }) {
  return (
    <div className="w-64 flex-shrink-0 border-r border-gray-200 bg-gray-50 overflow-y-auto">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-1.5">
          <Wrench className="w-3.5 h-3.5" /> Available Tools
        </h2>
      </div>
      <div className="p-3 space-y-2">
        {tools.map(tool => (
          <div key={tool.name} className="rounded-lg bg-white border border-gray-200 p-3">
            <ToolChip name={tool.name} />
            <p className="mt-1.5 text-xs text-gray-500 leading-relaxed">
              {tool.description}
            </p>
          </div>
        ))}
        {tools.length === 0 && (
          <p className="text-xs text-gray-400 italic px-1">Loading tools…</p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

interface MCPChatPageProps {
  onBack: () => void;
}

export default function MCPChatPage({ onBack }: MCPChatPageProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [tools, setTools] = useState<McpTool[]>([]);
  const [provider, setProvider] = useState<ProviderInfo | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const _apiKey = import.meta.env.VITE_ADMIN_API_KEY;
  const _authHeader = (_apiKey ? { 'X-API-Key': _apiKey } : {}) as Record<string, string>;

  // Fetch tool list + provider info on mount
  useEffect(() => {
    fetch('/mcp-chat/tools', { headers: _authHeader })
      .then(r => r.json())
      .then(d => setTools(d.tools ?? []))
      .catch(() => {});

    fetch('/ai/provider', { headers: _authHeader })
      .then(r => r.json())
      .then(d => setProvider(d))
      .catch(() => {});
  }, []);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const sendMessage = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMsg: ChatMessage = { id: uid(), role: 'user', content: trimmed };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);

    try {
      const resp = await fetch('/mcp-chat/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ..._authHeader },
        body: JSON.stringify({
          messages: nextMessages.map(m => ({ role: m.role, content: m.content })),
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        setMessages(prev => [
          ...prev,
          {
            id: uid(),
            role: 'assistant',
            content: err.detail ?? `HTTP ${resp.status}`,
            error: true,
          },
        ]);
        return;
      }

      const data = await resp.json();
      setMessages(prev => [
        ...prev,
        {
          id: uid(),
          role: 'assistant',
          content: data.reply,
          toolCalls: data.tool_calls ?? [],
          provider: data.provider,
          model: data.model,
        },
      ]);
    } catch (e) {
      setMessages(prev => [
        ...prev,
        {
          id: uid(),
          role: 'assistant',
          content: `Network error: ${e instanceof Error ? e.message : String(e)}`,
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [messages, loading]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const clearChat = () => {
    setMessages([]);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-screen bg-gray-50">

      {/* ── Header ─────────────────────────────────────────────── */}
      <header className="flex-shrink-0 bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-full mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            <div className="w-px h-5 bg-gray-200" />
            <div className="flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-indigo-500" />
              <div>
                <h1 className="text-base font-semibold text-gray-900 leading-tight">
                  MCP FHIR Chat
                </h1>
                <p className="text-xs text-gray-400">
                  AI-driven FHIR queries · xSoVx/fhir-mcp tool set
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <ProviderBadge info={provider} />
            {messages.length > 0 && (
              <button
                onClick={clearChat}
                title="Clear conversation"
                className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800 border border-gray-300 rounded-lg px-2.5 py-1.5 hover:bg-gray-50 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" /> Clear
              </button>
            )}
            <button
              onClick={() => setSidebarOpen(o => !o)}
              className="text-xs text-gray-500 hover:text-gray-800 border border-gray-300 rounded-lg px-2.5 py-1.5 hover:bg-gray-50 transition-colors"
            >
              {sidebarOpen ? 'Hide tools' : 'Show tools'}
            </button>
          </div>
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">

        {/* Tool sidebar */}
        {sidebarOpen && <ToolSidebar tools={tools} />}

        {/* Chat area */}
        <div className="flex flex-col flex-1 min-w-0">

          {/* Message list */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4 space-y-4">

            {/* Empty state */}
            {isEmpty && (
              <div className="flex flex-col items-center justify-center h-full text-center gap-6 py-16">
                <div className="w-16 h-16 rounded-2xl bg-indigo-100 flex items-center justify-center">
                  <MessageSquare className="w-8 h-8 text-indigo-500" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-800 mb-1">
                    FHIR MCP Chat
                  </h2>
                  <p className="text-sm text-gray-500 max-w-sm">
                    Ask anything about the PH-TS terminology server.
                    The AI will call FHIR tools to find real answers.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2 w-full max-w-lg">
                  {STARTER_PROMPTS.map(p => (
                    <button
                      key={p}
                      onClick={() => sendMessage(p)}
                      className="text-left text-sm text-gray-600 bg-white border border-gray-200 rounded-xl px-4 py-3 hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Messages */}
            {messages.map(msg => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}

            {/* Typing indicator */}
            {loading && (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                Calling FHIR tools…
              </div>
            )}
          </div>

          {/* Input bar */}
          <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3">
            <div className="flex items-end gap-2 max-w-4xl mx-auto">
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={input}
                  onChange={e => {
                    setInput(e.target.value);
                    // Auto-grow up to ~5 lines
                    e.target.style.height = 'auto';
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask about FHIR resources, codes, value sets… (Enter to send, Shift+Enter for newline)"
                  disabled={loading}
                  className="w-full resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent disabled:opacity-60 overflow-hidden"
                  style={{ minHeight: '44px' }}
                />
              </div>
              <button
                onClick={() => sendMessage(input)}
                disabled={!input.trim() || loading}
                className="flex-shrink-0 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl px-4 py-3 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                title="Send (Enter)"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
            <p className="text-center text-xs text-gray-400 mt-1.5">
              Tool calls are visible in each response. Shift+Enter for a new line.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
