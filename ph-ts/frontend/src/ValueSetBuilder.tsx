import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Search, Plus, Trash2, Save, Sparkles, ChevronLeft, Loader2,
  AlertCircle, CheckCircle, BookOpen, ArrowRightLeft, Info, X,
  RefreshCw, ChevronDown,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SdoSystem {
  id: string;
  name: string;
  url: string;
  description: string;
  available: boolean;
  requires_key: boolean;
  category: string;
}

interface SdoResult {
  code: string;
  display: string;
  system: string;
  systemName: string;
}

interface SelectedCode extends SdoResult {
  key: string; // code + system for uniqueness
}

interface AiSuggestion extends SdoResult {
  rationale: string;
  confidence: 'high' | 'medium' | 'low';
  caveats?: string | null;
}

interface AiSuggestResponse {
  suggestions: AiSuggestion[];
  additional_search_terms: string[];
  notes?: string;
}

interface AiDescribeResponse {
  name?: string;
  title?: string;
  description?: string;
  purpose?: string;
  suggested_url?: string;
  notes?: string;
}

interface AiMapResponse {
  mappings: Array<{
    source_code: string;
    source_display: string;
    target_code: string | null;
    target_display: string | null;
    target_system: string;
    equivalence: string;
    rationale: string;
  }>;
  notes?: string;
}

interface BuilderMetadata {
  name: string;
  title: string;
  url: string;
  status: 'draft' | 'active' | 'retired';
  version: string;
  description: string;
  purpose: string;
}

interface Props {
  onBack: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json', Accept: 'application/fhir+json', ...options?.headers },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.text();
    let msg = `${resp.status} ${resp.statusText}`;
    try {
      const parsed = JSON.parse(body);
      msg = parsed?.detail || parsed?.issue?.[0]?.diagnostics || msg;
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  return resp.json() as Promise<T>;
}

const CONFIDENCE_COLOURS: Record<string, string> = {
  high: 'bg-green-100 text-green-700',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-gray-100 text-gray-500',
};

const EQUIV_COLOURS: Record<string, string> = {
  equivalent: 'bg-green-100 text-green-700',
  wider: 'bg-blue-100 text-blue-700',
  narrower: 'bg-purple-100 text-purple-700',
  inexact: 'bg-yellow-100 text-yellow-700',
  unmatched: 'bg-red-100 text-red-600',
};

const CATEGORY_BADGE: Record<string, string> = {
  clinical: 'bg-blue-100 text-blue-700',
  laboratory: 'bg-purple-100 text-purple-700',
  diagnosis: 'bg-red-100 text-red-700',
  medication: 'bg-orange-100 text-orange-700',
  multi: 'bg-teal-100 text-teal-700',
};

function codeKey(code: string, system: string) {
  return `${system}|${code}`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const StatusBadge = ({ status }: { status: string }) => {
  const colours: Record<string, string> = {
    active: 'bg-green-100 text-green-700',
    draft: 'bg-yellow-100 text-yellow-700',
    retired: 'bg-gray-100 text-gray-500',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colours[status] ?? 'bg-gray-100 text-gray-500'}`}>
      {status}
    </span>
  );
};

const Toast = ({ message, type, onClose }: { message: string; type: 'success' | 'error'; onClose: () => void }) => (
  <div className={`fixed bottom-6 right-6 z-50 flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg text-sm max-w-sm
    ${type === 'success' ? 'bg-green-50 border border-green-200 text-green-800' : 'bg-red-50 border border-red-200 text-red-800'}`}>
    {type === 'success'
      ? <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />
      : <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />}
    <span className="flex-1">{message}</span>
    <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
  </div>
);

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ValueSetBuilder({ onBack }: Props) {
  // Systems
  const [systems, setSystems] = useState<SdoSystem[]>([]);
  const [selectedSystem, setSelectedSystem] = useState('snomed');

  // Code search (left panel)
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SdoResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Selected codes (basket)
  const [selectedCodes, setSelectedCodes] = useState<SelectedCode[]>([]);

  // Metadata (center panel)
  const [meta, setMeta] = useState<BuilderMetadata>({
    name: '', title: '', url: '', status: 'draft', version: '1.0', description: '', purpose: '',
  });

  // Save state
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  // AI panel (right panel)
  const [aiQuery, setAiQuery] = useState('');
  const [aiSystems, setAiSystems] = useState<string[]>(['snomed', 'icd10cm']);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiSuggestions, setAiSuggestions] = useState<AiSuggestResponse | null>(null);
  const [describeLoading, setDescribeLoading] = useState(false);

  // Map panel
  const [mapTarget, setMapTarget] = useState('icd10cm');
  const [mapLoading, setMapLoading] = useState(false);
  const [mapResults, setMapResults] = useState<AiMapResponse | null>(null);
  const [mapOpen, setMapOpen] = useState(false);

  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load available systems on mount
  useEffect(() => {
    apiFetch<{ systems: SdoSystem[] }>('/sdo/systems')
      .then(d => setSystems(d.systems))
      .catch(() => {/* silently fail — systems list is non-critical */});
  }, []);

  // Debounced search
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    searchDebounceRef.current = setTimeout(() => {
      setSearchLoading(true);
      setSearchError(null);
      apiFetch<{ results: SdoResult[] }>(`/sdo/search?system=${selectedSystem}&q=${encodeURIComponent(searchQuery)}&limit=25`)
        .then(d => setSearchResults(d.results))
        .catch(e => setSearchError((e as Error).message))
        .finally(() => setSearchLoading(false));
    }, 400);
  }, [searchQuery, selectedSystem]);

  const addCode = useCallback((code: SdoResult) => {
    const k = codeKey(code.code, code.system);
    setSelectedCodes(prev => prev.some(c => c.key === k) ? prev : [...prev, { ...code, key: k }]);
  }, []);

  const removeCode = useCallback((key: string) => {
    setSelectedCodes(prev => prev.filter(c => c.key !== key));
  }, []);

  const handleSave = async () => {
    if (!meta.name.trim()) {
      setToast({ message: 'Name is required before saving.', type: 'error' });
      return;
    }
    setSaving(true);
    try {
      // Build FHIR R4 ValueSet compose from selected codes
      const bySystem: Record<string, string[]> = {};
      for (const c of selectedCodes) {
        if (!bySystem[c.system]) bySystem[c.system] = [];
        bySystem[c.system].push(c.code);
      }

      const valueSet = {
        resourceType: 'ValueSet',
        name: meta.name,
        title: meta.title || meta.name,
        url: meta.url || `http://terminology.example.org/ValueSet/${meta.name}`,
        status: meta.status,
        version: meta.version || '1.0',
        description: meta.description || undefined,
        purpose: meta.purpose || undefined,
        compose: {
          include: Object.entries(bySystem).map(([system, codes]) => ({
            system,
            concept: codes.map(code => {
              const found = selectedCodes.find(c => c.code === code && c.system === system);
              return { code, display: found?.display || '' };
            }),
          })),
        },
      };

      await apiFetch('/ValueSet', { method: 'POST', body: JSON.stringify(valueSet) });
      setToast({ message: `ValueSet "${meta.name}" saved successfully.`, type: 'success' });
      // Reset form
      setMeta({ name: '', title: '', url: '', status: 'draft', version: '1.0', description: '', purpose: '' });
      setSelectedCodes([]);
      setSearchResults([]);
      setSearchQuery('');
    } catch (e) {
      setToast({ message: `Save failed: ${(e as Error).message}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleAiSuggest = async () => {
    if (!aiQuery.trim()) return;
    setAiLoading(true);
    setAiError(null);
    setAiSuggestions(null);
    try {
      const result = await apiFetch<AiSuggestResponse>('/ai/suggest', {
        method: 'POST',
        body: JSON.stringify({ description: aiQuery, systems: aiSystems, limit: 10 }),
      });
      setAiSuggestions(result);
    } catch (e) {
      setAiError((e as Error).message);
    } finally {
      setAiLoading(false);
    }
  };

  const handleAiDescribe = async () => {
    if (selectedCodes.length === 0) {
      setToast({ message: 'Add some codes first, then generate metadata.', type: 'error' });
      return;
    }
    setDescribeLoading(true);
    try {
      const result = await apiFetch<AiDescribeResponse>('/ai/describe', {
        method: 'POST',
        body: JSON.stringify({ codes: selectedCodes, context: meta.description }),
      });
      setMeta(prev => ({
        ...prev,
        name: result.name || prev.name,
        title: result.title || prev.title,
        description: result.description || prev.description,
        purpose: result.purpose || prev.purpose,
        url: prev.url || result.suggested_url || '',
      }));
      setToast({ message: 'Metadata generated from selected codes.', type: 'success' });
    } catch (e) {
      setToast({ message: `Generate failed: ${(e as Error).message}`, type: 'error' });
    } finally {
      setDescribeLoading(false);
    }
  };

  const handleAiMap = async () => {
    if (selectedCodes.length === 0) {
      setToast({ message: 'Select some codes first to map.', type: 'error' });
      return;
    }
    setMapLoading(true);
    setMapResults(null);
    try {
      const result = await apiFetch<AiMapResponse>('/ai/map', {
        method: 'POST',
        body: JSON.stringify({
          codes: selectedCodes,
          source_system: selectedSystem,
          target_system: mapTarget,
        }),
      });
      setMapResults(result);
    } catch (e) {
      setToast({ message: `Mapping failed: ${(e as Error).message}`, type: 'error' });
    } finally {
      setMapLoading(false);
    }
  };

  const availableSystems = systems.filter(s => s.available || !s.requires_key);
  const currentSystem = systems.find(s => s.id === selectedSystem);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-20">
        <div className="max-w-screen-2xl mx-auto px-4 py-3 flex items-center gap-4">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" /> Browse
          </button>
          <div className="h-5 w-px bg-gray-300" />
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-blue-600" />
            <h1 className="font-semibold text-gray-900">Value Set Builder</h1>
          </div>
          <div className="flex-1" />
          <StatusBadge status={meta.status} />
          {meta.name && <span className="text-sm text-gray-500 font-mono">{meta.name}</span>}
          <button
            onClick={handleSave}
            disabled={saving || !meta.name.trim()}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors text-sm font-medium"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Value Set
          </button>
        </div>
      </header>

      {/* Three-panel layout */}
      <div className="flex-1 max-w-screen-2xl mx-auto w-full px-4 py-4 grid grid-cols-[320px_1fr_340px] gap-4">

        {/* ───── LEFT: Code Search ───── */}
        <div className="flex flex-col gap-3">
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <Search className="w-4 h-4 text-blue-500" /> Code System Search
            </h2>

            {/* System selector */}
            <div className="mb-3">
              <label className="text-xs font-medium text-gray-500 uppercase mb-1 block">Code System</label>
              <div className="relative">
                <select
                  value={selectedSystem}
                  onChange={e => { setSelectedSystem(e.target.value); setSearchResults([]); setSearchQuery(''); }}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 appearance-none bg-white focus:ring-2 focus:ring-blue-400 pr-8"
                >
                  {systems.length === 0
                    ? <option value="snomed">SNOMED CT</option>
                    : systems.map(s => (
                      <option key={s.id} value={s.id} disabled={s.requires_key && !s.available}>
                        {s.name}{s.requires_key && !s.available ? ' (key required)' : ''}
                      </option>
                    ))
                  }
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
              {currentSystem && (
                <p className="text-xs text-gray-400 mt-1 line-clamp-2">{currentSystem.description}</p>
              )}
            </div>

            {/* Search input */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search concepts…"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-400"
              />
              {searchLoading && (
                <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-blue-500 animate-spin" />
              )}
            </div>
          </div>

          {/* Search results */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm flex-1 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 280px)' }}>
            {searchError && (
              <div className="p-3 flex items-start gap-2 text-red-600 text-xs">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{searchError}</span>
              </div>
            )}
            {!searchLoading && !searchError && searchResults.length === 0 && searchQuery && (
              <p className="p-4 text-sm text-gray-400 text-center">No results for "{searchQuery}"</p>
            )}
            {!searchQuery && (
              <p className="p-4 text-sm text-gray-400 text-center">Type a term to search concepts</p>
            )}
            {searchResults.map((r, i) => {
              const key = codeKey(r.code, r.system);
              const added = selectedCodes.some(c => c.key === key);
              return (
                <div key={i} className="flex items-start gap-3 px-4 py-3 border-b border-gray-100 last:border-0 hover:bg-blue-50 transition-colors group">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono text-blue-600">{r.code}</p>
                    <p className="text-sm text-gray-800 line-clamp-2">{r.display}</p>
                    <p className="text-xs text-gray-400 truncate">{r.system}</p>
                  </div>
                  <button
                    onClick={() => addCode(r)}
                    disabled={added}
                    title={added ? 'Already added' : 'Add to value set'}
                    className={`flex-shrink-0 mt-0.5 p-1.5 rounded-full transition-colors ${added
                      ? 'bg-green-100 text-green-600 cursor-default'
                      : 'bg-blue-100 text-blue-600 hover:bg-blue-200'
                    }`}
                  >
                    {added ? <CheckCircle className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                  </button>
                </div>
              );
            })}
          </div>

          {/* System legend */}
          {systems.length > 0 && (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
              <p className="text-xs font-medium text-gray-500 uppercase mb-2">Available Systems</p>
              <div className="flex flex-col gap-1">
                {systems.map(s => (
                  <div key={s.id} className="flex items-center gap-2 text-xs">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.available || !s.requires_key ? 'bg-green-400' : 'bg-gray-300'}`} />
                    <span className="font-medium text-gray-700">{s.name}</span>
                    <span className={`ml-auto px-1.5 py-0.5 rounded text-xs ${CATEGORY_BADGE[s.category] ?? 'bg-gray-100 text-gray-500'}`}>
                      {s.category}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ───── CENTER: Metadata + Basket ───── */}
        <div className="flex flex-col gap-4 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 100px)' }}>

          {/* Metadata form */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
              <Info className="w-4 h-4 text-blue-500" /> Value Set Details
            </h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase block mb-1">
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  placeholder="UpperCamelCase"
                  value={meta.name}
                  onChange={e => setMeta(m => ({ ...m, name: e.target.value }))}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-400"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase block mb-1">Title</label>
                <input
                  type="text"
                  placeholder="Human readable title"
                  value={meta.title}
                  onChange={e => setMeta(m => ({ ...m, title: e.target.value }))}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-400"
                />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-gray-500 uppercase block mb-1">Canonical URL</label>
                <input
                  type="text"
                  placeholder="http://terminology.example.org/ValueSet/..."
                  value={meta.url}
                  onChange={e => setMeta(m => ({ ...m, url: e.target.value }))}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-400 font-mono"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase block mb-1">Status</label>
                <div className="relative">
                  <select
                    value={meta.status}
                    onChange={e => setMeta(m => ({ ...m, status: e.target.value as BuilderMetadata['status'] }))}
                    className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 appearance-none bg-white focus:ring-2 focus:ring-blue-400 pr-8"
                  >
                    <option value="draft">Draft</option>
                    <option value="active">Active</option>
                    <option value="retired">Retired</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase block mb-1">Version</label>
                <input
                  type="text"
                  placeholder="1.0"
                  value={meta.version}
                  onChange={e => setMeta(m => ({ ...m, version: e.target.value }))}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-400"
                />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-gray-500 uppercase block mb-1">Description</label>
                <textarea
                  rows={2}
                  placeholder="A ValueSet containing codes that represent…"
                  value={meta.description}
                  onChange={e => setMeta(m => ({ ...m, description: e.target.value }))}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-400 resize-none"
                />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-gray-500 uppercase block mb-1">Purpose</label>
                <textarea
                  rows={2}
                  placeholder="Used to identify… in the context of…"
                  value={meta.purpose}
                  onChange={e => setMeta(m => ({ ...m, purpose: e.target.value }))}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-400 resize-none"
                />
              </div>
            </div>
          </div>

          {/* Selected codes basket */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5 flex-1">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-500" />
                Selected Codes
                <span className="ml-1 bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full text-xs font-medium">
                  {selectedCodes.length}
                </span>
              </h2>
              {selectedCodes.length > 0 && (
                <button
                  onClick={() => setSelectedCodes([])}
                  className="text-xs text-gray-400 hover:text-red-500 transition-colors"
                >
                  Clear all
                </button>
              )}
            </div>

            {selectedCodes.length === 0 ? (
              <div className="text-center py-10 text-gray-400">
                <Plus className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No codes selected. Search and add codes from the left panel,
                  or use the AI assistant to get suggestions.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="text-left px-3 py-2 font-medium text-gray-500 text-xs uppercase w-32">Code</th>
                      <th className="text-left px-3 py-2 font-medium text-gray-500 text-xs uppercase">Display</th>
                      <th className="text-left px-3 py-2 font-medium text-gray-500 text-xs uppercase w-28">System</th>
                      <th className="w-10" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {selectedCodes.map(c => (
                      <tr key={c.key} className="hover:bg-gray-50 group">
                        <td className="px-3 py-2.5 font-mono text-blue-600 text-xs whitespace-nowrap">{c.code}</td>
                        <td className="px-3 py-2.5 text-gray-800">{c.display}</td>
                        <td className="px-3 py-2.5 text-gray-400 text-xs truncate max-w-[110px]">{c.systemName}</td>
                        <td className="px-2 py-2.5">
                          <button
                            onClick={() => removeCode(c.key)}
                            className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition-all"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Cross-system mapping */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
            <button
              onClick={() => setMapOpen(o => !o)}
              className="flex items-center justify-between w-full"
            >
              <span className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <ArrowRightLeft className="w-4 h-4 text-purple-500" /> Cross-System Mapping
              </span>
              <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${mapOpen ? 'rotate-180' : ''}`} />
            </button>

            {mapOpen && (
              <div className="mt-3 space-y-3">
                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <label className="text-xs font-medium text-gray-500 uppercase block mb-1">Map to System</label>
                    <div className="relative">
                      <select
                        value={mapTarget}
                        onChange={e => setMapTarget(e.target.value)}
                        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 appearance-none bg-white focus:ring-2 focus:ring-purple-400 pr-8"
                      >
                        {(systems.length > 0 ? systems : [{ id: 'icd10cm', name: 'ICD-10-CM' }, { id: 'snomed', name: 'SNOMED CT' }, { id: 'rxnorm', name: 'RxNorm' }]).map((s: any) => (
                          <option key={s.id} value={s.id}>{s.name}</option>
                        ))}
                      </select>
                      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                    </div>
                  </div>
                  <button
                    onClick={handleAiMap}
                    disabled={mapLoading || selectedCodes.length === 0}
                    className="mt-5 flex items-center gap-1.5 text-sm bg-purple-600 text-white px-3 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-40 transition-colors whitespace-nowrap"
                  >
                    {mapLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRightLeft className="w-4 h-4" />}
                    Map
                  </button>
                </div>

                {mapResults && (
                  <div className="border border-gray-200 rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 border-b border-gray-200">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium text-gray-500">Source</th>
                          <th className="text-left px-3 py-2 font-medium text-gray-500">Target</th>
                          <th className="text-left px-3 py-2 font-medium text-gray-500">Match</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {mapResults.mappings.map((m, i) => (
                          <tr key={i} className="hover:bg-gray-50">
                            <td className="px-3 py-2">
                              <p className="font-mono text-blue-600">{m.source_code}</p>
                              <p className="text-gray-600 line-clamp-1">{m.source_display}</p>
                            </td>
                            <td className="px-3 py-2">
                              {m.target_code ? (
                                <>
                                  <p className="font-mono text-purple-600">{m.target_code}</p>
                                  <p className="text-gray-600 line-clamp-1">{m.target_display}</p>
                                </>
                              ) : (
                                <span className="text-gray-400 italic">No match</span>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${EQUIV_COLOURS[m.equivalence] ?? 'bg-gray-100 text-gray-500'}`}>
                                {m.equivalence}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {mapResults.notes && (
                      <p className="px-3 py-2 text-xs text-gray-400 border-t border-gray-100">{mapResults.notes}</p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ───── RIGHT: AI Assistant ───── */}
        <div className="flex flex-col gap-3 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 100px)' }}>
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-yellow-500" /> AI Code Assistant
            </h2>
            <p className="text-xs text-gray-500 mb-3">
              Describe the clinical concept you're looking for. The AI assistant will search the selected code
              systems and rank the best matches with clinical rationale.
            </p>

            {/* AI system checkboxes */}
            <div className="mb-3">
              <label className="text-xs font-medium text-gray-500 uppercase block mb-1.5">Search in</label>
              <div className="flex flex-wrap gap-2">
                {(systems.length > 0 ? systems.filter(s => !s.requires_key || s.available) : [
                  { id: 'snomed', name: 'SNOMED CT' },
                  { id: 'icd10cm', name: 'ICD-10-CM' },
                  { id: 'rxnorm', name: 'RxNorm' },
                ]).map((s: any) => (
                  <label key={s.id} className="flex items-center gap-1.5 text-xs cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={aiSystems.includes(s.id)}
                      onChange={e => setAiSystems(prev =>
                        e.target.checked ? [...prev, s.id] : prev.filter(x => x !== s.id)
                      )}
                      className="rounded border-gray-300 text-blue-600"
                    />
                    <span className="text-gray-700">{s.name}</span>
                  </label>
                ))}
              </div>
            </div>

            <textarea
              rows={3}
              placeholder="e.g. 'codes for measuring blood pressure in outpatient settings' or 'diagnoses related to type 2 diabetes complications'"
              value={aiQuery}
              onChange={e => setAiQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) handleAiSuggest(); }}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-yellow-400 resize-none mb-2"
            />

            <button
              onClick={handleAiSuggest}
              disabled={aiLoading || !aiQuery.trim() || aiSystems.length === 0}
              className="w-full flex items-center justify-center gap-2 bg-yellow-500 text-white py-2 rounded-lg hover:bg-yellow-600 disabled:opacity-40 transition-colors text-sm font-medium"
            >
              {aiLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {aiLoading ? 'Searching & analysing…' : 'Ask AI (Ctrl+Enter)'}
            </button>

            {aiError && (
              <div className="mt-3 flex items-start gap-2 text-xs text-red-600 bg-red-50 rounded-lg p-3">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{aiError}</span>
              </div>
            )}
          </div>

          {/* AI Suggestions */}
          {aiSuggestions && (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-700">
                  {aiSuggestions.suggestions.length} Suggestions
                </h3>
                <button onClick={() => setAiSuggestions(null)} className="text-gray-300 hover:text-gray-500">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3">
                {aiSuggestions.suggestions.map((s, i) => {
                  const key = codeKey(s.code, s.system);
                  const added = selectedCodes.some(c => c.key === key);
                  return (
                    <div key={i} className="border border-gray-100 rounded-lg p-3 hover:border-blue-200 transition-colors">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-0.5">
                            <span className="font-mono text-blue-600 text-xs">{s.code}</span>
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${CONFIDENCE_COLOURS[s.confidence] ?? ''}`}>
                              {s.confidence}
                            </span>
                            <span className="text-xs text-gray-400">{s.systemName}</span>
                          </div>
                          <p className="text-sm text-gray-800 font-medium">{s.display}</p>
                        </div>
                        <button
                          onClick={() => addCode(s)}
                          disabled={added}
                          className={`flex-shrink-0 p-1.5 rounded-full transition-colors ${added
                            ? 'bg-green-100 text-green-600 cursor-default'
                            : 'bg-blue-100 text-blue-600 hover:bg-blue-200'
                          }`}
                        >
                          {added ? <CheckCircle className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">{s.rationale}</p>
                      {s.caveats && (
                        <p className="text-xs text-amber-600 mt-1 bg-amber-50 px-2 py-1 rounded">
                          ⚠ {s.caveats}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>

              {aiSuggestions.additional_search_terms?.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-100">
                  <p className="text-xs font-medium text-gray-500 mb-2">Try also searching for:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {aiSuggestions.additional_search_terms.map((term, i) => (
                      <button
                        key={i}
                        onClick={() => setSearchQuery(term)}
                        className="text-xs bg-gray-100 hover:bg-blue-100 text-gray-600 hover:text-blue-700 px-2 py-1 rounded transition-colors"
                      >
                        {term}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {aiSuggestions.notes && (
                <p className="mt-2 text-xs text-gray-400 italic">{aiSuggestions.notes}</p>
              )}
            </div>
          )}

          {/* Generate Metadata */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
              <RefreshCw className="w-4 h-4 text-blue-500" /> Generate Metadata
            </h3>
            <p className="text-xs text-gray-500 mb-3">
              Auto-fill the name, title, description, and purpose fields based on your selected codes.
            </p>
            <button
              onClick={handleAiDescribe}
              disabled={describeLoading || selectedCodes.length === 0}
              className="w-full flex items-center justify-center gap-2 bg-blue-50 text-blue-700 border border-blue-200 py-2 rounded-lg hover:bg-blue-100 disabled:opacity-40 transition-colors text-sm font-medium"
            >
              {describeLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {describeLoading ? 'Generating…' : `Generate from ${selectedCodes.length} code${selectedCodes.length !== 1 ? 's' : ''}`}
            </button>
          </div>
        </div>
      </div>

      {/* Toast notification */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}
