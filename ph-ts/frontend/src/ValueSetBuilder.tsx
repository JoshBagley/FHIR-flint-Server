import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Search, Plus, Trash2, Save, Sparkles, ChevronLeft, Loader2,
  AlertCircle, CheckCircle, BookOpen, ArrowRightLeft, Info, X,
  RefreshCw, ChevronDown, MessageSquare, Send, GitBranch, Map, ChevronRight, BookmarkPlus, ExternalLink,
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

/** Unified entry for both external SDO connectors and locally stored CodeSystems. */
interface UnifiedSystem {
  /** Selector key — SDO short-id (e.g. "snomed") or local resource id (UUID). */
  id: string;
  source: 'sdo' | 'local';
  name: string;
  url: string;
  description: string;
  available: boolean;
  /** SDO-only fields */
  category?: string;
  /** Local CodeSystem fields */
  content?: string;
  conceptCount?: number;
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


interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  suggested_codes?: SdoResult[];
}

interface ChatResponse {
  reply: string;
  suggested_codes: SdoResult[];
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

interface TranslateResult {
  sourceCode: string;
  sourceDisplay: string;
  targetCode: string | null;
  targetDisplay: string | null;
  targetSystem: string | null;
  equivalence: string;
  found: boolean;
}

interface LoincProperty {
  code: string;
  value: string;
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
  // Systems — unified list of external SDOs + local CodeSystems
  const [systems, setSystems] = useState<UnifiedSystem[]>([]);
  const [selectedSystem, setSelectedSystem] = useState('__local_all__');

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

  // Chat SME panel (right panel)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const [describeLoading, setDescribeLoading] = useState(false);

  // Map panel
  const [mapTarget, setMapTarget] = useState('icd10cm');
  const [mapLoading, setMapLoading] = useState(false);
  const [mapResults, setMapResults] = useState<AiMapResponse | null>(null);
  const [mapOpen, setMapOpen] = useState(false);

  // SNOMED hierarchy expand
  const [snomedMode, setSnomedMode] = useState<'search' | 'hierarchy'>('search');
  const [snomedEdition, setSnomedEdition] = useState<'international' | 'us'>('international');
  const [eclConceptId, setEclConceptId] = useState('');
  const [eclResults, setEclResults] = useState<SdoResult[]>([]);
  const [eclLoading, setEclLoading] = useState(false);
  const [eclError, setEclError] = useState<string | null>(null);
  const [eclTotal, setEclTotal] = useState<number | null>(null);

  // ConceptMap $translate in mapping panel
  const [mapMode, setMapMode] = useState<'ai' | 'conceptmap'>('ai');
  const [translateResults, setTranslateResults] = useState<TranslateResult[] | null>(null);
  const [translateLoading, setTranslateLoading] = useState(false);

  // Save AI mapping as ConceptMap
  const [mapSaveOpen, setMapSaveOpen] = useState(false);
  const [mapSaveName, setMapSaveName] = useState('');
  const [mapSaveTitle, setMapSaveTitle] = useState('');
  const [mapSaving, setMapSaving] = useState(false);
  const [mapSavedId, setMapSavedId] = useState<string | null>(null);
  const [mapSourceUrl, setMapSourceUrl] = useState('');

  // SNOMED hierarchy tree view
  type TreeChild = { code: string; display: string };
  type TreeNodeData = {
    conceptId: string; display: string;
    children: TreeChild[]; childCount: number;
    parent: TreeChild | null; edition: string;
  };
  const [snomedHierarchyView, setSnomedHierarchyView] = useState<'flat' | 'tree'>('flat');
  const [treeData, setTreeData] = useState<Record<string, TreeNodeData>>({});
  const [treeRootId, setTreeRootId] = useState<string | null>(null);
  const [treeExpandedIds, setTreeExpandedIds] = useState<Set<string>>(new Set());
  const [treeLoadingIds, setTreeLoadingIds] = useState<Set<string>>(new Set());
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState<string | null>(null);

  // LOINC property detail per search result
  const [loincDetailCode, setLoincDetailCode] = useState<string | null>(null);
  const [loincDetailCache, setLoincDetailCache] = useState<Record<string, LoincProperty[]>>({});
  const [loincDetailLoading, setLoincDetailLoading] = useState<string | null>(null);

  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load available systems on mount — merge external SDOs + local CodeSystems
  useEffect(() => {
    Promise.all([
      apiFetch<{ systems: SdoSystem[] }>('/sdo/systems').catch(() => ({ systems: [] as SdoSystem[] })),
      apiFetch<{ entry?: Array<{ resource: { id: string; url?: string; name?: string; title?: string; content?: string; concept?: unknown[] } }> }>(
        '/CodeSystem?_count=500&_summary=true'
      ).catch(() => ({ entry: [] })),
    ]).then(([sdoData, csBundle]) => {
      const sdoSystems: UnifiedSystem[] = (sdoData.systems ?? []).map(s => ({
        id: s.id,
        source: 'sdo' as const,
        name: s.name,
        url: s.url,
        description: s.description,
        available: s.available || !s.requires_key,
        category: s.category,
      }));

      const localSystems: UnifiedSystem[] = (csBundle.entry ?? [])
        .map(e => e.resource)
        .filter(r => r?.id && r.url && r.content !== 'not-present')
        .map(r => ({
          id: r.id,
          source: 'local' as const,
          name: r.title || r.name || r.url || r.id,
          url: r.url ?? '',
          description: `Local · ${r.content ?? 'complete'} · ${Array.isArray(r.concept) ? r.concept.length.toLocaleString() : '?'} concepts`,
          available: true,
          content: r.content,
          conceptCount: Array.isArray(r.concept) ? r.concept.length : undefined,
        }))
        .sort((a, b) => a.name.localeCompare(b.name));

      const allLocalSentinel: UnifiedSystem = {
        id: '__local_all__',
        source: 'local',
        name: 'All Local Code Systems',
        url: '',
        description: 'Search concepts across every locally stored code system at once',
        available: true,
      };
      const merged = [...sdoSystems, ...(localSystems.length > 0 ? [allLocalSentinel, ...localSystems] : [])];
      setSystems(merged);
      // Default to first available SDO system so external searches work out of the box
      const firstAvailableSdo = sdoSystems.find(s => s.available);
      if (firstAvailableSdo) setSelectedSystem(firstAvailableSdo.id);
    });
  }, []);

  // Debounced search — routes to SDO connector or local CodeSystem based on source
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const system = systems.find(s => s.id === selectedSystem);
    searchDebounceRef.current = setTimeout(() => {
      setSearchLoading(true);
      setSearchError(null);
      const url = selectedSystem === '__local_all__'
        ? `/CodeSystem/$search-all-concepts?q=${encodeURIComponent(searchQuery)}&count=25`
        : system?.source === 'local'
          ? `/CodeSystem/$search-concepts?url=${encodeURIComponent(system.url)}&q=${encodeURIComponent(searchQuery)}&count=25`
          : `/sdo/search?system=${selectedSystem}&q=${encodeURIComponent(searchQuery)}&limit=25`;
      apiFetch<{ results: SdoResult[] }>(url)
        .then(d => setSearchResults(d.results))
        .catch(e => setSearchError((e as Error).message))
        .finally(() => setSearchLoading(false));
    }, 400);
  }, [searchQuery, selectedSystem, systems]);

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

  // Auto-scroll chat to latest message (scroll within panel, not the page)
  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [chatMessages]);

  const handleChatSend = async () => {
    const text = chatInput.trim();
    if (!text || chatLoading) return;
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: text };
    const nextMessages = [...chatMessages, userMsg];
    setChatMessages(nextMessages);
    setChatInput('');
    setChatLoading(true);
    try {
      const result = await apiFetch<ChatResponse>('/ai/chat', {
        method: 'POST',
        body: JSON.stringify({
          messages: nextMessages.map(m => ({ role: m.role, content: m.content })),
          valueset_context: {
            name: meta.name,
            title: meta.title,
            description: meta.description,
            purpose: meta.purpose,
            codes: selectedCodes,
          },
        }),
      });
      setChatMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: result.reply,
        suggested_codes: result.suggested_codes,
      }]);
    } catch (e) {
      setChatMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Error: ${(e as Error).message}`,
      }]);
    } finally {
      setChatLoading(false);
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

  // Load the root concept for the hierarchy tree
  const handleTreeLoad = async () => {
    const conceptId = eclConceptId.trim();
    if (!conceptId) return;
    setTreeLoading(true);
    setTreeError(null);
    setTreeData({});
    setTreeRootId(null);
    setTreeExpandedIds(new Set());
    try {
      const data = await apiFetch<{ conceptId: string; display: string; children: {code:string;display:string}[]; childCount: number; parent: {code:string;display:string}|null; edition: string }>(
        `/sdo/snomed/children/${encodeURIComponent(conceptId)}?edition=${snomedEdition}`
      );
      setTreeData({ [conceptId]: data });
      setTreeRootId(conceptId);
      setTreeExpandedIds(new Set([conceptId]));
    } catch (e) {
      setTreeError((e as Error).message);
    } finally {
      setTreeLoading(false);
    }
  };

  // Lazy-expand a tree node
  const handleExpandTreeNode = async (code: string) => {
    if (treeData[code]) {
      setTreeExpandedIds(prev => {
        const next = new Set(prev);
        if (next.has(code)) next.delete(code); else next.add(code);
        return next;
      });
      return;
    }
    setTreeLoadingIds(prev => new Set(prev).add(code));
    try {
      const data = await apiFetch<{ conceptId: string; display: string; children: {code:string;display:string}[]; childCount: number; parent: {code:string;display:string}|null; edition: string }>(
        `/sdo/snomed/children/${encodeURIComponent(code)}?edition=${snomedEdition}`
      );
      setTreeData(prev => ({ ...prev, [code]: data }));
      setTreeExpandedIds(prev => new Set(prev).add(code));
    } catch {
      // silently ignore per-node expansion errors
    } finally {
      setTreeLoadingIds(prev => { const next = new Set(prev); next.delete(code); return next; });
    }
  };

  // Save AI mapping results as a ConceptMap
  const handleSaveAsConceptMap = async () => {
    if (!mapResults || !mapSaveName.trim()) return;
    setMapSaving(true);
    try {
      const saved = await apiFetch<{ id: string }>('/ai/map-save', {
        method: 'POST',
        body: JSON.stringify({
          mappings: mapResults.mappings,
          source_system_url: mapSourceUrl,
          target_system: mapTarget,
          name: mapSaveName.trim(),
          title: mapSaveTitle.trim() || mapSaveName.trim(),
          status: 'draft',
        }),
      });
      setMapSavedId(saved.id);
      setMapSaveOpen(false);
      setToast({ message: `ConceptMap "${mapSaveTitle || mapSaveName}" saved as draft.`, type: 'success' });
    } catch (e) {
      setToast({ message: `Save failed: ${(e as Error).message}`, type: 'error' });
    } finally {
      setMapSaving(false);
    }
  };

  const handleAiMap = async () => {
    if (selectedCodes.length === 0) {
      setToast({ message: 'Select some codes first to map.', type: 'error' });
      return;
    }
    setMapLoading(true);
    setMapResults(null);
    setMapSavedId(null);
    setMapSaveOpen(false);
    setMapSourceUrl(selectedCodes[0]?.system ?? '');
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

  // SNOMED ECL / hierarchy expand
  const handleEclExpand = async () => {
    const conceptId = eclConceptId.trim();
    if (!conceptId) return;
    setEclLoading(true);
    setEclError(null);
    setEclResults([]);
    setEclTotal(null);
    try {
      const base = snomedEdition === 'us'
        ? 'http://snomed.info/sct/731000124108'
        : 'http://snomed.info/sct';
      const snomedUrl = `${base}?fhir_vs=isa/${encodeURIComponent(conceptId)}`;
      const data = await apiFetch<{
        expansion?: { total?: number; contains?: Array<{ system: string; code: string; display?: string }> };
      }>(`/ValueSet/$expand?url=${encodeURIComponent(snomedUrl)}&count=200`);
      const contains = data.expansion?.contains ?? [];
      setEclTotal(data.expansion?.total ?? contains.length);
      setEclResults(contains.map(c => ({
        code: c.code,
        display: c.display ?? c.code,
        system: c.system,
        systemName: snomedEdition === 'us' ? 'SNOMED CT US Edition' : 'SNOMED CT',
      })));
    } catch (e) {
      setEclError((e as Error).message);
    } finally {
      setEclLoading(false);
    }
  };

  // ConceptMap $translate for each selected code
  const handleConceptMapTranslate = async () => {
    if (selectedCodes.length === 0) {
      setToast({ message: 'Select some codes first to translate.', type: 'error' });
      return;
    }
    const targetSystem = systems.find(s => s.id === mapTarget);
    const targetUrl = targetSystem?.url ?? '';
    setTranslateLoading(true);
    setTranslateResults(null);
    try {
      const results: TranslateResult[] = await Promise.all(
        selectedCodes.map(async code => {
          try {
            const params = new URLSearchParams({ system: code.system, code: code.code });
            if (targetUrl) params.set('target', targetUrl);
            const data = await apiFetch<{
              parameter: Array<{
                name: string;
                valueBoolean?: boolean;
                part?: Array<{ name: string; valueCode?: string; valueCoding?: { system?: string; code?: string; display?: string } }>;
              }>;
            }>(`/ConceptMap/$translate?${params.toString()}`);
            const resultParam = data.parameter?.find(p => p.name === 'result');
            const found = resultParam?.valueBoolean === true;
            const matchParam = data.parameter?.find(p => p.name === 'match');
            const equivalence = matchParam?.part?.find(p => p.name === 'equivalence')?.valueCode ?? 'unmatched';
            const concept = matchParam?.part?.find(p => p.name === 'concept')?.valueCoding;
            return {
              sourceCode: code.code,
              sourceDisplay: code.display,
              targetCode: concept?.code ?? null,
              targetDisplay: concept?.display ?? null,
              targetSystem: concept?.system ?? null,
              equivalence,
              found,
            };
          } catch {
            return {
              sourceCode: code.code,
              sourceDisplay: code.display,
              targetCode: null,
              targetDisplay: null,
              targetSystem: null,
              equivalence: 'unmatched',
              found: false,
            };
          }
        })
      );
      setTranslateResults(results);
    } catch (e) {
      setToast({ message: `Translation failed: ${(e as Error).message}`, type: 'error' });
    } finally {
      setTranslateLoading(false);
    }
  };

  // LOINC property detail (toggle open / fetch on demand)
  const handleLoincDetail = async (code: string) => {
    if (loincDetailCode === code) {
      setLoincDetailCode(null);
      return;
    }
    setLoincDetailCode(code);
    if (loincDetailCache[code]) return;
    setLoincDetailLoading(code);
    try {
      const data = await apiFetch<{
        parameter: Array<{
          name: string;
          valueString?: string;
          part?: Array<{ name: string; valueCode?: string; valueString?: string }>;
        }>;
      }>(`/CodeSystem/$lookup?system=http%3A%2F%2Floinc.org&code=${encodeURIComponent(code)}&property=parent&property=COMPONENT&property=PROPERTY&property=SYSTEM&property=SCALE_TYP&property=METHOD_TYP&property=STATUS`);
      const props: LoincProperty[] = (data.parameter ?? [])
        .filter(p => p.name === 'property' && p.part)
        .map(p => {
          const namePart = p.part!.find(x => x.name === 'code');
          const valPart = p.part!.find(x => x.name === 'value');
          return {
            code: namePart?.valueCode ?? '',
            value: valPart?.valueCode ?? valPart?.valueString ?? '',
          };
        })
        .filter(p => p.code && p.value);
      setLoincDetailCache(prev => ({ ...prev, [code]: props }));
    } catch {
      setLoincDetailCache(prev => ({ ...prev, [code]: [] }));
    } finally {
      setLoincDetailLoading(null);
    }
  };

  const currentSystem = systems.find(s => s.id === selectedSystem);
  const sdoSystems = systems.filter(s => s.source === 'sdo');
  const localSystems = systems.filter(s => s.source === 'local' && s.id !== '__local_all__');

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
                    ? <option value="__local_all__">All Local Code Systems</option>
                    : <>
                      {sdoSystems.length > 0 && (
                        <optgroup label="External Vocabularies">
                          {sdoSystems.map(s => (
                            <option key={s.id} value={s.id} disabled={!s.available}>
                              {s.name}{!s.available ? ' (key required)' : ''}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {localSystems.length > 0 && (
                        <optgroup label="Local Code Systems">
                          <option value="__local_all__">All Local Code Systems</option>
                          {localSystems.map(s => (
                            <option key={s.id} value={s.id}>
                              {s.name}{s.conceptCount != null ? ` (${s.conceptCount.toLocaleString()})` : ''}
                            </option>
                          ))}
                        </optgroup>
                      )}
                    </>
                  }
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
              {currentSystem && (
                <p className="text-xs text-gray-400 mt-1 line-clamp-2">{currentSystem.description}</p>
              )}
            </div>

            {/* SNOMED mode toggle */}
            {selectedSystem === 'snomed' && (
              <div className="flex rounded-lg border border-gray-200 overflow-hidden mb-3 text-xs font-medium">
                <button
                  onClick={() => { setSnomedMode('search'); setEclResults([]); setEclError(null); }}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 transition-colors ${snomedMode === 'search' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                >
                  <Search className="w-3.5 h-3.5" /> Text Search
                </button>
                <button
                  onClick={() => { setSnomedMode('hierarchy'); setSearchResults([]); setSearchQuery(''); }}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 transition-colors ${snomedMode === 'hierarchy' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                >
                  <GitBranch className="w-3.5 h-3.5" /> Hierarchy
                </button>
              </div>
            )}

            {/* ECL / hierarchy expand input (SNOMED only) */}
            {selectedSystem === 'snomed' && snomedMode === 'hierarchy' ? (
              <div className="space-y-2">
                {/* Edition toggle */}
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase block mb-1">Edition</label>
                  <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
                    <button
                      onClick={() => { setSnomedEdition('international'); setEclResults([]); setEclError(null); }}
                      className={`flex-1 py-1.5 transition-colors ${snomedEdition === 'international' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                    >
                      International
                    </button>
                    <button
                      onClick={() => { setSnomedEdition('us'); setEclResults([]); setEclError(null); }}
                      className={`flex-1 py-1.5 transition-colors ${snomedEdition === 'us' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                    >
                      US Edition
                    </button>
                  </div>
                  {snomedEdition === 'us' && (
                    <p className="text-xs text-gray-400 mt-1">US Extension preferred; falls back to International Edition if unavailable on tx.fhir.org</p>
                  )}
                </div>
                {/* Flat vs Tree view toggle */}
                <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
                  <button
                    onClick={() => { setSnomedHierarchyView('flat'); setTreeData({}); setTreeRootId(null); setTreeError(null); }}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 transition-colors ${snomedHierarchyView === 'flat' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                  >
                    <GitBranch className="w-3.5 h-3.5" /> Expand All
                  </button>
                  <button
                    onClick={() => { setSnomedHierarchyView('tree'); setEclResults([]); setEclError(null); }}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 transition-colors ${snomedHierarchyView === 'tree' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                  >
                    <ChevronRight className="w-3.5 h-3.5" /> Browse Tree
                  </button>
                </div>
                <label className="text-xs font-medium text-gray-500 uppercase block">Concept ID</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="e.g. 840539006"
                    value={eclConceptId}
                    onChange={e => setEclConceptId(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') snomedHierarchyView === 'tree' ? handleTreeLoad() : handleEclExpand(); }}
                    className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-400 font-mono"
                  />
                  <button
                    onClick={snomedHierarchyView === 'tree' ? handleTreeLoad : handleEclExpand}
                    disabled={(snomedHierarchyView === 'flat' ? eclLoading : treeLoading) || !eclConceptId.trim()}
                    className="flex items-center gap-1 text-sm bg-blue-600 text-white px-3 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors whitespace-nowrap"
                  >
                    {(snomedHierarchyView === 'flat' ? eclLoading : treeLoading)
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : snomedHierarchyView === 'tree' ? <ChevronRight className="w-4 h-4" /> : <GitBranch className="w-4 h-4" />}
                    {snomedHierarchyView === 'tree' ? 'Browse' : 'Expand'}
                  </button>
                </div>
                <p className="text-xs text-gray-400">
                  {snomedHierarchyView === 'tree'
                    ? 'Lazy tree — click nodes to expand children one level at a time.'
                    : 'Returns all descendants in a flat list (up to 200).'}
                </p>
              </div>
            ) : (
              /* Standard text search input */
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
            )}
          </div>

          {/* Search / ECL results */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm flex-1 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 280px)' }}>
            {/* ECL results (SNOMED hierarchy mode) */}
            {selectedSystem === 'snomed' && snomedMode === 'hierarchy' && (
              <>
                {/* ── Flat expand results ── */}
                {snomedHierarchyView === 'flat' && (
                  <>
                    {eclError && (
                      <div className="p-3 flex items-start gap-2 text-red-600 text-xs">
                        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                        <span>{eclError}</span>
                      </div>
                    )}
                    {eclLoading && (
                      <div className="p-4 flex items-center justify-center gap-2 text-sm text-gray-400">
                        <Loader2 className="w-4 h-4 animate-spin" /> Expanding hierarchy…
                      </div>
                    )}
                    {!eclLoading && eclResults.length === 0 && !eclError && (
                      <p className="p-4 text-sm text-gray-400 text-center">Enter a SNOMED CT concept ID and click Expand</p>
                    )}
                    {eclResults.length > 0 && (
                      <>
                        <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                          <span className="text-xs text-gray-500">
                            {eclResults.length} concept{eclResults.length !== 1 ? 's' : ''}
                            {eclTotal != null && eclTotal > eclResults.length ? ` (showing ${eclResults.length} of ${eclTotal.toLocaleString()})` : ''}
                          </span>
                          <button
                            onClick={() => eclResults.forEach(r => addCode(r))}
                            className="text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors"
                          >
                            Add all
                          </button>
                        </div>
                        {eclResults.map((r, i) => {
                          const key = codeKey(r.code, r.system);
                          const added = selectedCodes.some(c => c.key === key);
                          return (
                            <div key={i} className="flex items-start gap-3 px-4 py-3 border-b border-gray-100 last:border-0 hover:bg-blue-50 transition-colors group">
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-mono text-blue-600">{r.code}</p>
                                <p className="text-sm text-gray-800 line-clamp-2">{r.display}</p>
                              </div>
                              <button
                                onClick={() => addCode(r)}
                                disabled={added}
                                title={added ? 'Already added' : 'Add to value set'}
                                className={`flex-shrink-0 mt-0.5 p-1.5 rounded-full transition-colors ${added ? 'bg-green-100 text-green-600 cursor-default' : 'bg-blue-100 text-blue-600 hover:bg-blue-200'}`}
                              >
                                {added ? <CheckCircle className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                              </button>
                            </div>
                          );
                        })}
                      </>
                    )}
                  </>
                )}

                {/* ── Lazy tree view ── */}
                {snomedHierarchyView === 'tree' && (
                  <>
                    {treeError && (
                      <div className="p-3 flex items-start gap-2 text-red-600 text-xs">
                        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                        <span>{treeError}</span>
                      </div>
                    )}
                    {treeLoading && (
                      <div className="p-4 flex items-center justify-center gap-2 text-sm text-gray-400">
                        <Loader2 className="w-4 h-4 animate-spin" /> Loading concept…
                      </div>
                    )}
                    {!treeLoading && !treeRootId && !treeError && (
                      <p className="p-4 text-sm text-gray-400 text-center">Enter a SNOMED CT concept ID and click Browse</p>
                    )}
                    {treeRootId && treeData[treeRootId] && (() => {
                      // Recursive tree node renderer
                      const renderNode = (code: string, display: string, depth: number): React.ReactNode => {
                        const node = treeData[code];
                        const isExpanded = treeExpandedIds.has(code);
                        const isNodeLoading = treeLoadingIds.has(code);
                        const hasChildren = !node || node.childCount > 0;
                        const added = selectedCodes.some(c => c.code === code && c.system === 'http://snomed.info/sct');
                        const sysName = snomedEdition === 'us' ? 'SNOMED CT US Edition' : 'SNOMED CT';
                        return (
                          <div key={code}>
                            <div
                              className="flex items-center gap-1 py-1.5 pr-3 hover:bg-blue-50 group transition-colors"
                              style={{ paddingLeft: `${depth * 16 + 8}px` }}
                            >
                              <button
                                onClick={() => hasChildren && handleExpandTreeNode(code)}
                                className={`w-5 h-5 flex items-center justify-center flex-shrink-0 rounded ${!hasChildren ? 'invisible' : 'text-gray-400 hover:text-blue-600'}`}
                              >
                                {isNodeLoading
                                  ? <Loader2 className="w-3 h-3 animate-spin" />
                                  : <ChevronRight className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />}
                              </button>
                              <span className="font-mono text-xs text-blue-600 flex-shrink-0 w-28 truncate">{code}</span>
                              <span className="text-sm text-gray-700 flex-1 truncate">{display || node?.display || ''}</span>
                              <button
                                onClick={() => addCode({ code, display: display || node?.display || '', system: 'http://snomed.info/sct', systemName: sysName })}
                                disabled={added}
                                title={added ? 'Already added' : 'Add to value set'}
                                className={`flex-shrink-0 p-1 rounded-full opacity-0 group-hover:opacity-100 transition-all ${added ? 'opacity-100 text-green-500' : 'text-blue-500 hover:text-blue-700 hover:bg-blue-100'}`}
                              >
                                {added ? <CheckCircle className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                              </button>
                            </div>
                            {isExpanded && node?.children.map(child => renderNode(child.code, child.display, depth + 1))}
                          </div>
                        );
                      };
                      const root = treeData[treeRootId];
                      return (
                        <>
                          <div className="px-3 py-2 bg-gray-50 border-b border-gray-100 text-xs text-gray-500 flex items-center gap-1.5">
                            <GitBranch className="w-3.5 h-3.5" />
                            {root.display} — {root.childCount} direct {root.childCount === 1 ? 'child' : 'children'}
                            {root.edition !== snomedEdition && <span className="text-amber-500 ml-1">(International Edition fallback)</span>}
                          </div>
                          {renderNode(treeRootId, root.display, 0)}
                        </>
                      );
                    })()}
                  </>
                )}
              </>
            )}

            {/* Standard text search results */}
            {(selectedSystem !== 'snomed' || snomedMode === 'search') && (
              <>
                {searchError && (
                  <div className="p-3 flex items-start gap-2 text-red-600 text-xs">
                    <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <span>{searchError}</span>
                  </div>
                )}
                {!searchLoading && !searchError && searchResults.length === 0 && searchQuery && (
                  <div className="p-4 text-center space-y-1">
                    <p className="text-sm text-gray-500">No results for "{searchQuery}"</p>
                    {selectedSystem === '__local_all__' && (
                      <p className="text-xs text-gray-400">
                        "All Local Code Systems" only searches concepts stored in the local database.
                        Select a specific system like <strong>SNOMED CT</strong>, <strong>LOINC</strong>, or <strong>ICD-10-CM</strong> to search external vocabularies.
                      </p>
                    )}
                  </div>
                )}
                {!searchQuery && (
                  <p className="p-4 text-sm text-gray-400 text-center">Type a term to search concepts</p>
                )}
                {searchResults.map((r, i) => {
                  const key = codeKey(r.code, r.system);
                  const added = selectedCodes.some(c => c.key === key);
                  const isLoincSelected = selectedSystem === 'loinc';
                  const detailOpen = isLoincSelected && loincDetailCode === r.code;
                  const detailProps = loincDetailCache[r.code];
                  return (
                    <div key={i} className="border-b border-gray-100 last:border-0">
                      <div className="flex items-start gap-3 px-4 py-3 hover:bg-blue-50 transition-colors group">
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-mono text-blue-600">{r.code}</p>
                          <p className="text-sm text-gray-800 line-clamp-2">{r.display}</p>
                          <p className="text-xs text-gray-400 truncate">{r.system}</p>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0 mt-0.5">
                          {isLoincSelected && (
                            <button
                              onClick={() => handleLoincDetail(r.code)}
                              title="Show LOINC properties"
                              className={`p-1.5 rounded-full transition-colors ${detailOpen ? 'bg-purple-100 text-purple-600' : 'text-gray-300 hover:text-purple-500 hover:bg-purple-50'}`}
                            >
                              {loincDetailLoading === r.code
                                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                : <ChevronRight className={`w-3.5 h-3.5 transition-transform ${detailOpen ? 'rotate-90' : ''}`} />
                              }
                            </button>
                          )}
                          <button
                            onClick={() => addCode(r)}
                            disabled={added}
                            title={added ? 'Already added' : 'Add to value set'}
                            className={`p-1.5 rounded-full transition-colors ${added ? 'bg-green-100 text-green-600 cursor-default' : 'bg-blue-100 text-blue-600 hover:bg-blue-200'}`}
                          >
                            {added ? <CheckCircle className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>
                      {/* LOINC property detail panel */}
                      {isLoincSelected && detailOpen && (
                        <div className="px-4 pb-3 bg-purple-50 border-t border-purple-100">
                          {detailProps === undefined && <p className="text-xs text-gray-400 py-2">Loading…</p>}
                          {detailProps?.length === 0 && (
                            <p className="text-xs text-gray-400 py-2">No properties returned for this code. For parent/child hierarchy, set <span className="font-mono">LOINC_USERNAME</span> / <span className="font-mono">LOINC_PASSWORD</span> in <span className="font-mono">.env</span>.</p>
                          )}
                          {detailProps && detailProps.length > 0 && (
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1 pt-2">
                              {detailProps.map((p, pi) => (
                                <div key={pi} className="text-xs">
                                  <span className="font-medium text-purple-700">{p.code}:</span>{' '}
                                  <span className="text-gray-700 font-mono">{p.value}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </>
            )}
          </div>

          {/* System legend */}
          {systems.length > 0 && (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
              <p className="text-xs font-medium text-gray-500 uppercase mb-2">Available Systems</p>
              <div className="flex flex-col gap-1">
                {sdoSystems.map(s => (
                  <div key={s.id} className="flex items-center gap-2 text-xs">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.available ? 'bg-green-400' : 'bg-gray-300'}`} />
                    <span className="font-medium text-gray-700">{s.name}</span>
                    <span className={`ml-auto px-1.5 py-0.5 rounded text-xs ${CATEGORY_BADGE[s.category ?? ''] ?? 'bg-gray-100 text-gray-500'}`}>
                      {s.category}
                    </span>
                  </div>
                ))}
                {localSystems.length > 0 && (
                  <>
                    <div className="border-t border-gray-100 my-1" />
                    <p className="text-xs text-gray-400 font-medium mb-0.5">Local</p>
                    {localSystems.map(s => (
                      <div key={s.id} className="flex items-center gap-2 text-xs">
                        <span className="w-2 h-2 rounded-full flex-shrink-0 bg-purple-400" />
                        <span className="font-medium text-gray-700 truncate flex-1">{s.name}</span>
                        <span className="ml-auto px-1.5 py-0.5 rounded text-xs bg-purple-50 text-purple-600 flex-shrink-0">
                          {s.content ?? 'complete'}
                        </span>
                      </div>
                    ))}
                  </>
                )}
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
                {/* Mode toggle: AI vs stored ConceptMap */}
                <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
                  <button
                    onClick={() => { setMapMode('ai'); setTranslateResults(null); }}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 transition-colors ${mapMode === 'ai' ? 'bg-purple-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                  >
                    <Sparkles className="w-3.5 h-3.5" /> AI Suggest
                  </button>
                  <button
                    onClick={() => { setMapMode('conceptmap'); setMapResults(null); }}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 transition-colors ${mapMode === 'conceptmap' ? 'bg-purple-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                  >
                    <Map className="w-3.5 h-3.5" /> Stored ConceptMap
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <label className="text-xs font-medium text-gray-500 uppercase block mb-1">Map to System</label>
                    <div className="relative">
                      <select
                        value={mapTarget}
                        onChange={e => setMapTarget(e.target.value)}
                        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 appearance-none bg-white focus:ring-2 focus:ring-purple-400 pr-8"
                      >
                        {(sdoSystems.length > 0 ? sdoSystems : [{ id: 'icd10cm', name: 'ICD-10-CM' }, { id: 'snomed', name: 'SNOMED CT' }, { id: 'rxnorm', name: 'RxNorm' }]).map(s => (
                          <option key={s.id} value={s.id}>{s.name}</option>
                        ))}
                      </select>
                      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                    </div>
                  </div>
                  <button
                    onClick={mapMode === 'ai' ? handleAiMap : handleConceptMapTranslate}
                    disabled={(mapMode === 'ai' ? mapLoading : translateLoading) || selectedCodes.length === 0}
                    className="mt-5 flex items-center gap-1.5 text-sm bg-purple-600 text-white px-3 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-40 transition-colors whitespace-nowrap"
                  >
                    {(mapMode === 'ai' ? mapLoading : translateLoading)
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : mapMode === 'ai' ? <Sparkles className="w-4 h-4" /> : <Map className="w-4 h-4" />}
                    Map
                  </button>
                </div>

                {/* AI map results */}
                {mapMode === 'ai' && mapResults && (
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

                    {/* Save as ConceptMap */}
                    <div className="px-3 py-2 border-t border-gray-100 bg-gray-50">
                      {mapSavedId ? (
                        <div className="flex items-center gap-2 text-xs text-green-700">
                          <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />
                          <span>Saved as ConceptMap</span>
                          <a
                            href={`/ConceptMap/${mapSavedId}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ml-auto flex items-center gap-1 text-blue-600 hover:underline"
                          >
                            {mapSavedId} <ExternalLink className="w-3 h-3" />
                          </a>
                        </div>
                      ) : !mapSaveOpen ? (
                        <button
                          onClick={() => setMapSaveOpen(true)}
                          className="flex items-center gap-1.5 text-xs text-purple-700 hover:text-purple-900 transition-colors"
                        >
                          <BookmarkPlus className="w-3.5 h-3.5" /> Save as ConceptMap
                        </button>
                      ) : (
                        <div className="flex flex-col gap-2">
                          <div className="flex gap-2">
                            <div className="flex-1">
                              <label className="text-xs text-gray-500 block mb-0.5">Name <span className="text-red-500">*</span></label>
                              <input
                                type="text"
                                placeholder="UpperCamelCase"
                                value={mapSaveName}
                                onChange={e => setMapSaveName(e.target.value)}
                                className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:ring-1 focus:ring-purple-400"
                              />
                            </div>
                            <div className="flex-1">
                              <label className="text-xs text-gray-500 block mb-0.5">Title</label>
                              <input
                                type="text"
                                placeholder="Human-readable title"
                                value={mapSaveTitle}
                                onChange={e => setMapSaveTitle(e.target.value)}
                                className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:ring-1 focus:ring-purple-400"
                              />
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={handleSaveAsConceptMap}
                              disabled={mapSaving || !mapSaveName.trim()}
                              className="flex items-center gap-1 text-xs bg-purple-600 text-white px-2.5 py-1 rounded hover:bg-purple-700 disabled:opacity-40 transition-colors"
                            >
                              {mapSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                              Save
                            </button>
                            <button
                              onClick={() => { setMapSaveOpen(false); setMapSaveName(''); setMapSaveTitle(''); }}
                              className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* ConceptMap $translate results */}
                {mapMode === 'conceptmap' && translateResults && (
                  <div className="border border-gray-200 rounded-lg overflow-hidden">
                    <div className="px-3 py-1.5 bg-purple-50 border-b border-gray-200 text-xs text-purple-700 font-medium flex items-center gap-1.5">
                      <Map className="w-3.5 h-3.5" /> Results from stored ConceptMaps
                    </div>
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 border-b border-gray-200">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium text-gray-500">Source</th>
                          <th className="text-left px-3 py-2 font-medium text-gray-500">Target</th>
                          <th className="text-left px-3 py-2 font-medium text-gray-500">Match</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {translateResults.map((m, i) => (
                          <tr key={i} className="hover:bg-gray-50">
                            <td className="px-3 py-2">
                              <p className="font-mono text-blue-600">{m.sourceCode}</p>
                              <p className="text-gray-600 line-clamp-1">{m.sourceDisplay}</p>
                            </td>
                            <td className="px-3 py-2">
                              {m.targetCode ? (
                                <>
                                  <p className="font-mono text-purple-600">{m.targetCode}</p>
                                  <p className="text-gray-600 line-clamp-1">{m.targetDisplay}</p>
                                </>
                              ) : (
                                <span className="text-gray-400 italic">No match in ConceptMap</span>
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
                    {translateResults.every(r => !r.found) && (
                      <p className="px-3 py-2 text-xs text-gray-400 border-t border-gray-100">
                        No local ConceptMaps matched. Create a ConceptMap via <span className="font-mono">POST /ConceptMap</span> to enable deterministic translation.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ───── RIGHT: AI Assistant Chat ───── */}
        <div className="flex flex-col gap-3 sticky top-4 self-start">

          {/* Chat card */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm flex flex-col" style={{ height: chatMessages.length > 0 ? 'calc(100vh - 220px)' : '50vh', minHeight: '250px', transition: 'height 0.3s ease' }}>
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 flex-shrink-0">
              <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-yellow-500" /> Vocabulary AI Assistant
              </h2>
              {chatMessages.length > 0 && (
                <button
                  onClick={() => setChatMessages([])}
                  className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
                >
                  Clear
                </button>
              )}
            </div>

            {/* Message thread */}
            <div ref={chatScrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
              {chatMessages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center px-4">
                  <Sparkles className="w-8 h-8 mb-3 text-gray-200" />
                  <p className="text-sm font-medium text-gray-500 mb-1">Vocabulary AI Assistant</p>
                  <p className="text-xs text-gray-400">
                    Ask about code systems, ValueSet design, or public health vocabulary.
                  </p>
                </div>
              ) : (
                <>
                  {chatMessages.map(msg => (
                    <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[88%] rounded-lg px-3 py-2 text-sm ${
                        msg.role === 'user'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-800'
                      }`}>
                        <p className="whitespace-pre-wrap break-words leading-relaxed">{msg.content}</p>
                        {/* Suggested code cards */}
                        {msg.suggested_codes && msg.suggested_codes.length > 0 && (
                          <div className="mt-2 space-y-1.5">
                            {msg.suggested_codes.map((code, i) => {
                              const k = codeKey(code.code, code.system);
                              const added = selectedCodes.some(c => c.key === k);
                              return (
                                <div key={i} className="bg-white border border-gray-200 rounded-lg px-2.5 py-2 flex items-center justify-between gap-2">
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                      <span className="font-mono text-blue-600 text-xs">{code.code}</span>
                                      <span className="text-xs text-gray-400">{code.systemName}</span>
                                    </div>
                                    <p className="text-xs text-gray-700 font-medium truncate">{code.display}</p>
                                  </div>
                                  <button
                                    onClick={() => addCode(code)}
                                    disabled={added}
                                    className={`flex-shrink-0 p-1 rounded-full transition-colors ${
                                      added ? 'bg-green-100 text-green-600 cursor-default' : 'bg-blue-100 text-blue-600 hover:bg-blue-200'
                                    }`}
                                  >
                                    {added ? <CheckCircle className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="flex justify-start">
                      <div className="bg-gray-100 rounded-lg px-4 py-3">
                        <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                      </div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </>
              )}
            </div>

            {/* Input area */}
            <div className="border-t border-gray-100 p-3 flex gap-2 flex-shrink-0">
              <textarea
                rows={3}
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChatSend(); } }}
                placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
                disabled={chatLoading}
                className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-yellow-400 resize-none"
              />
              <button
                onClick={handleChatSend}
                disabled={chatLoading || !chatInput.trim()}
                className="flex-shrink-0 p-2.5 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 disabled:opacity-40 transition-colors self-end"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>

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
