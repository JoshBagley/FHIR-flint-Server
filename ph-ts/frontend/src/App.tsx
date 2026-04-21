import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Search, Download, FileCode, Layers,
  GitBranch, TrendingUp, Activity, Clock, Database, AlertCircle, Loader2,
  ChevronDown, ChevronUp, Copy, Check, ExternalLink, ChevronLeft, ChevronRight, Plus, Settings, X, Filter, Pencil, Trash2,
  Archive, ScrollText, RefreshCw, MessageSquare
} from 'lucide-react';
import ValueSetBuilder from './ValueSetBuilder';
import MCPChatPage from './MCPChatPage';
import AppLogo from './components/AppLogo';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ConceptMapGroup {
  source?: string;
  target?: string;
  element: Array<{
    code: string;
    display?: string;
    target: Array<{ code?: string; display?: string; equivalence: string; comment?: string }>;
  }>;
}

interface ConceptMapSummary {
  id: string;
  name: string;
  title: string;
  status: string;
  description?: string;
  mappingCount: number;
  sources: string[];
  targets: string[];
}

interface ConceptMapFull extends ConceptMapSummary {
  group: ConceptMapGroup[];
}

interface FhirResource {
  id: string;
  resourceType: 'ValueSet' | 'CodeSystem';
  url?: string;
  name?: string;
  title?: string;
  description?: string;
  status: string;
  version?: string;
  content?: string;
  compose?: { include: Array<{ concept?: Array<{ code: string; display?: string }> }> };
  concept?: Array<{ code: string; display?: string }>;
  identifier?: Array<{ system?: string; value?: string }>;
  extension?: Array<{ url: string; valueCode?: string; [key: string]: unknown }>;
  useContext?: Array<{ code: { system?: string; code: string }; valueCodeableConcept?: { coding?: Array<{ system?: string; code?: string; display?: string }> }; valueCoding?: { system?: string; code?: string; display?: string } }>;
  _conceptCount?: number;
}

interface ApiStats {
  total_valuesets: number;
  total_codesystems: number;
  archived_resources: number;
  total_versions: number;
}

interface AuditEntry {
  id: number;
  resourceId: string;
  resourceType: string;
  action: string;
  actor?: string;
  timestamp: string;
  summary?: string;
}

interface VersionEntry {
  version: number;
  timestamp: string;
  author?: string;
  summary?: string;
}

interface ExpansionConcept {
  system?: string;
  systemName?: string;
  code: string;
  display?: string;
}

interface ConceptMatch {
  code: string;
  display: string;
  system: string;
}

interface ConceptSearchEntry {
  valueset: UiResource;
  matchedConcepts: ConceptMatch[];
  totalMatched: number;
}

interface SdoResult {
  code: string;
  display: string;
  description?: string;
  system: string;
  systemName: string;
  sourceUrl?: string;
}

interface SdoSystem {
  id: string;
  name: string;
  available: boolean;
}

interface UiResource {
  id: string;
  resourceType: 'ValueSet' | 'CodeSystem';
  url: string;
  name: string;
  title: string;
  definition: string;
  status: string;
  version: string;
  content?: string;
  source?: string;
  conceptCount: number;
  versionHistory: VersionEntry[];
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function countConcepts(resource: FhirResource): number {
  if (resource._conceptCount !== undefined) return resource._conceptCount;
  if (resource.resourceType === 'ValueSet') {
    return (resource.compose?.include ?? []).reduce(
      (sum, inc) => sum + (inc.concept?.length ?? 0), 0
    );
  }
  return resource.concept?.length ?? 0;
}

const SOURCE_EXT_URL = 'http://phts.local/StructureDefinition/source';

function toUiResource(r: FhirResource): UiResource {
  const sourceExt = r.extension?.find(e => e.url === SOURCE_EXT_URL);
  return {
    id: r.id,
    resourceType: r.resourceType,
    url: r.url ?? '',
    name: r.name ?? r.title ?? r.id,
    title: r.title ?? r.name ?? r.id,
    definition: r.description ? stripHtml(r.description) : '',
    status: r.status,
    version: r.version ?? '1',
    content: r.content,
    source: sourceExt?.valueCode,
    conceptCount: countConcepts(r),
    versionHistory: [],
  };
}

const _API_KEY = import.meta.env.VITE_ADMIN_API_KEY as string | undefined;

function _authHeaders(path: string): Record<string, string> {
  if (_API_KEY && (path.startsWith('/ai/') || path.startsWith('/admin/'))) {
    return { 'X-API-Key': _API_KEY };
  }
  return {};
}

async function apiFetch<T>(path: string): Promise<T> {
  const resp = await fetch(path, { headers: { Accept: 'application/fhir+json', ..._authHeaders(path) } });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText} — ${path}`);
  return resp.json() as Promise<T>;
}

async function fetchStats(): Promise<ApiStats> {
  return apiFetch<ApiStats>('/analytics/summary');
}

async function fetchResources(
  resourceType: 'ValueSet' | 'CodeSystem',
  search: string,
  status?: string,
  content?: string,
  contextValueCode?: string,
  source?: string,
  archivedOnly = false,
): Promise<UiResource[]> {
  const params = new URLSearchParams();
  if (search.trim()) params.set('name', search.trim());
  if (status) params.set('status', status);
  if (content) params.set('content', content);
  if (contextValueCode) params.set('context-value-code', contextValueCode);
  if (source) params.set('source', source);
  if (archivedOnly) params.set('_archived', 'true');
  params.set('_summary', 'true');
  const bundle = await apiFetch<{ entry?: Array<{ resource: FhirResource }> }>(
    `/${resourceType}?${params}`
  );
  return (bundle.entry ?? [])
    .map(e => e.resource)
    .filter(Boolean)
    .map(toUiResource);
}

async function fetchConceptMaps(search: string): Promise<ConceptMapSummary[]> {
  const params = new URLSearchParams({ _summary: 'true' });
  if (search.trim()) params.set('name', search.trim());
  const bundle = await apiFetch<{
    entry?: Array<{ resource: {
      id: string; name?: string; title?: string; status: string; description?: string;
      version?: string; group?: ConceptMapGroup[];
    } }>
  }>(`/ConceptMap?${params}`);
  return (bundle.entry ?? []).map(e => {
    const r = e.resource;
    const groups: ConceptMapGroup[] = r.group ?? [];
    const mappingCount = groups.reduce((n, g) => n + (g.element?.length ?? 0), 0);
    const sources = [...new Set(groups.map(g => g.source).filter(Boolean))] as string[];
    const targets = [...new Set(groups.map(g => g.target).filter(Boolean))] as string[];
    return { id: r.id, name: r.name ?? r.id, title: r.title ?? r.name ?? r.id, status: r.status, description: r.description, mappingCount, sources, targets };
  });
}

async function fetchConceptMapFull(id: string): Promise<ConceptMapFull> {
  const r = await apiFetch<{
    id: string; name?: string; title?: string; status: string; description?: string; group?: ConceptMapGroup[];
  }>(`/ConceptMap/${id}`);
  const groups: ConceptMapGroup[] = r.group ?? [];
  const mappingCount = groups.reduce((n, g) => n + (g.element?.length ?? 0), 0);
  const sources = [...new Set(groups.map(g => g.source).filter(Boolean))] as string[];
  const targets = [...new Set(groups.map(g => g.target).filter(Boolean))] as string[];
  return { id: r.id, name: r.name ?? r.id, title: r.title ?? r.name ?? r.id, status: r.status, description: r.description, mappingCount, sources, targets, group: groups };
}

interface DiseaseView {
  id: string;
  display: string;
  system: string;
  code: string;
  description: string;
  count: number;
}

async function fetchDiseaseViews(): Promise<DiseaseView[]> {
  const res = await apiFetch<{ views: DiseaseView[] }>('/ValueSet/$views');
  return res.views ?? [];
}

async function tagValueSetView(resourceId: string, viewId: string, remove = false): Promise<void> {
  const resp = await fetch(`/ValueSet/$tag-view?resource_id=${encodeURIComponent(resourceId)}&view_id=${encodeURIComponent(viewId)}`, {
    method: remove ? 'DELETE' : 'POST',
  });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
}

async function fetchFullResource(resourceType: 'ValueSet' | 'CodeSystem', id: string): Promise<FhirResource> {
  return apiFetch<FhirResource>(`/${resourceType}/${id}`);
}

async function updateResource(resourceType: 'ValueSet' | 'CodeSystem', id: string, data: FhirResource): Promise<void> {
  const resp = await fetch(`/${resourceType}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/fhir+json', Accept: 'application/fhir+json' },
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
}

async function deleteResource(resourceType: 'ValueSet' | 'CodeSystem', id: string): Promise<void> {
  const resp = await fetch(`/${resourceType}/${id}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
}

async function archiveResource(id: string, restore = false): Promise<void> {
  const resp = await fetch(`/ValueSet/${id}/$archive${restore ? '?restore=true' : ''}`, { method: 'PATCH' });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
}

async function fetchAuditLog(id: string, resourceType = 'ValueSet'): Promise<AuditEntry[]> {
  const data = await apiFetch<{ entries: AuditEntry[] }>(`/${resourceType}/${id}/$audit`);
  return data.entries ?? [];
}

async function fetchExpansion(url: string): Promise<ExpansionConcept[]> {
  const data = await apiFetch<{ expansion?: { contains?: ExpansionConcept[] } }>(
    `/ValueSet/$expand?url=${encodeURIComponent(url)}&count=1000`
  );
  return data.expansion?.contains ?? [];
}

async function fetchVersionHistory(
  resourceType: 'ValueSet' | 'CodeSystem',
  id: string
): Promise<VersionEntry[]> {
  try {
    const data = await apiFetch<{ versions?: VersionEntry[] }>(
      `/${resourceType}/${id}/_history`
    );
    return data.versions ?? [];
  } catch {
    return [];
  }
}

async function fetchConceptSearch(term: string, limit = 20, ids?: string[]): Promise<ConceptSearchEntry[]> {
  let url = `/ValueSet/$concept-search?q=${encodeURIComponent(term)}&limit=${limit}`;
  if (ids && ids.length > 0) url += `&ids=${ids.join(',')}`;
  const data = await apiFetch<{
    entry?: Array<{
      resource: FhirResource & { resourceType: 'ValueSet' };
      search: { matchedConcepts: ConceptMatch[]; totalMatched: number };
    }>;
  }>(url);
  return (data.entry ?? []).map(e => ({
    valueset: toUiResource(e.resource),
    matchedConcepts: e.search?.matchedConcepts ?? [],
    totalMatched: e.search?.totalMatched ?? 0,
  }));
}

async function fetchSdoSystems(): Promise<SdoSystem[]> {
  const data = await apiFetch<{ systems: SdoSystem[] }>('/sdo/systems');
  return (data.systems ?? []).filter(s => s.available);
}

async function fetchExternalConceptSearch(
  term: string,
  systems: SdoSystem[]
): Promise<Record<string, { systemName: string; results: SdoResult[] }>> {
  const out: Record<string, { systemName: string; results: SdoResult[] }> = {};
  await Promise.all(
    systems.map(async s => {
      try {
        const data = await apiFetch<{ results: SdoResult[] }>(
          `/sdo/search?system=${s.id}&q=${encodeURIComponent(term)}&limit=10`
        );
        out[s.id] = { systemName: s.name, results: data.results ?? [] };
      } catch {
        out[s.id] = { systemName: s.name, results: [] };
      }
    })
  );
  return out;
}

// ---------------------------------------------------------------------------
// Custom hook: debounced value
// ---------------------------------------------------------------------------

function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const StatusBadge = ({ status }: { status: string }) => {
  const colours: Record<string, string> = {
    active: 'bg-green-100 text-green-700',
    draft: 'bg-yellow-100 text-yellow-700',
    retired: 'bg-gray-100 text-gray-500',
    unknown: 'bg-red-100 text-red-600',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colours[status] ?? colours.unknown}`}>
      {status}
    </span>
  );
};

const ContentBadge = ({ content }: { content?: string }) => {
  const colours: Record<string, string> = {
    complete:    'bg-purple-100 text-purple-700',
    fragment:    'bg-blue-100 text-blue-700',
    'not-present': 'bg-gray-100 text-gray-500',
    example:     'bg-orange-100 text-orange-700',
    supplement:  'bg-teal-100 text-teal-700',
  };
  const label = content ?? 'complete';
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colours[label] ?? 'bg-gray-100 text-gray-500'}`}>
      {label}
    </span>
  );
};

const SOURCE_LABELS: Record<string, string> = {
  phinvads: 'PHIN VADS',
  vsac:     'VSAC',
  hl7:      'HL7',
  hl7v2:    'HL7 v2',
  icd9cm:   'ICD-9-CM',
  icd10cm:  'ICD-10-CM',
  internal: 'PHTS',
};

const SOURCE_COLOURS: Record<string, string> = {
  phinvads: 'bg-orange-100 text-orange-700',
  vsac:     'bg-teal-100 text-teal-700',
  hl7:      'bg-indigo-100 text-indigo-700',
  hl7v2:    'bg-violet-100 text-violet-700',
  icd9cm:   'bg-gray-100 text-gray-600',
  icd10cm:  'bg-gray-100 text-gray-600',
  internal: 'bg-blue-50 text-blue-600',
};

const SourceBadge = ({ source }: { source?: string }) => {
  const key = source ?? 'internal';
  const label = SOURCE_LABELS[key] ?? key;
  const colour = SOURCE_COLOURS[key] ?? 'bg-gray-100 text-gray-500';
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colour}`}>
      {label}
    </span>
  );
};

const LoadingSpinner = ({ message = 'Loading…' }: { message?: string }) => (
  <div className="flex flex-col items-center justify-center py-24 gap-3 text-gray-500">
    <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
    <p className="text-sm">{message}</p>
  </div>
);

const ErrorBanner = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
    <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
    <div className="flex-1 min-w-0">
      <p className="text-sm font-medium text-red-800">Failed to load data</p>
      <p className="text-xs text-red-600 mt-1 font-mono break-all">{message}</p>
    </div>
    <button
      onClick={onRetry}
      className="text-xs text-red-700 underline hover:no-underline flex-shrink-0"
    >
      Retry
    </button>
  </div>
);

// ---------------------------------------------------------------------------
// Expansion page
// ---------------------------------------------------------------------------

function exportCsv(concepts: ExpansionConcept[], filename: string) {
  const header = 'code,display,system\n';
  const rows = concepts
    .map(c => `${c.code},${JSON.stringify(c.display ?? '')},${c.system ?? ''}`)
    .join('\n');
  const blob = new Blob([header + rows], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const ExpansionPage = ({ resource, onBack }: { resource: UiResource; onBack: () => void }) => {
  const [concepts, setConcepts] = useState<ExpansionConcept[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const PAGE = 50;

  useEffect(() => {
    if (!resource.url) {
      setError('This value set has no canonical URL and cannot be expanded.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    fetchExpansion(resource.url)
      .then(setConcepts)
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [resource.url]);

  const handleCopy = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 1500);
  };

  const hasSystem = concepts.some(c => c.system || c.systemName);
  const filtered = concepts.filter(c => {
    const q = filter.toLowerCase();
    return !q || c.code.toLowerCase().includes(q) || (c.display ?? '').toLowerCase().includes(q);
  });
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const currentPage = Math.min(page, totalPages - 1);
  const paginated = filtered.slice(currentPage * PAGE, currentPage * PAGE + PAGE);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          <div className="h-5 w-px bg-gray-300" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="font-semibold text-gray-900 truncate">{resource.title || resource.name}</h1>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                resource.status === 'active' ? 'bg-green-100 text-green-700' :
                resource.status === 'draft'  ? 'bg-yellow-100 text-yellow-700' :
                'bg-gray-100 text-gray-500'}`}>{resource.status}</span>
              <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">v{resource.version}</span>
            </div>
            <p className="text-xs text-gray-400 font-mono truncate mt-0.5">{resource.url}</p>
          </div>
          <button
            onClick={() => exportCsv(filtered, `${resource.name}-expansion.csv`)}
            disabled={loading || filtered.length === 0}
            className="flex items-center gap-1.5 text-sm bg-blue-600 text-white px-3 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Stats bar */}
        {!loading && !error && (
          <div className="flex items-center gap-6 mb-4 text-sm text-gray-600">
            <span><span className="font-semibold text-gray-900">{concepts.length}</span> total concepts</span>
            {filter && <span><span className="font-semibold text-gray-900">{filtered.length}</span> matching</span>}
          </div>
        )}

        {/* Search */}
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-3 mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Filter by code or display…"
              value={filter}
              onChange={e => { setFilter(e.target.value); setPage(0); }}
              className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-400 focus:border-blue-400"
            />
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-32 gap-3 text-gray-400">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            <p className="text-sm">Fetching expansion…</p>
          </div>
        ) : error ? (
          <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-24 text-gray-400">
            <p className="text-sm">{filter ? `No concepts match "${filter}"` : 'This ValueSet has no concepts.'}</p>
          </div>
        ) : (
          <>
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-gray-500 uppercase text-xs tracking-wide w-44">Code</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500 uppercase text-xs tracking-wide">Display</th>
                    {hasSystem && <th className="text-left px-4 py-3 font-medium text-gray-500 uppercase text-xs tracking-wide">System</th>}
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {paginated.map((c, i) => (
                    <tr key={`${c.code}-${i}`} className="hover:bg-blue-50 group transition-colors">
                      <td className="px-4 py-3 font-mono text-blue-700 text-sm align-top whitespace-nowrap">{c.code}</td>
                      <td className="px-4 py-3 text-gray-800 align-top">{c.display ?? <span className="italic text-gray-400">—</span>}</td>
                      {hasSystem && (
                      <td className="px-4 py-3 text-gray-600 text-xs align-top truncate max-w-xs" title={c.system}>
                        {c.systemName ?? c.system}
                      </td>
                    )}
                      <td className="px-3 py-3 align-top">
                        <button
                          onClick={() => handleCopy(c.code)}
                          title="Copy code"
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-blue-600"
                        >
                          {copiedCode === c.code
                            ? <Check className="w-4 h-4 text-green-500" />
                            : <Copy className="w-4 h-4" />}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={currentPage === 0}
                  className="flex items-center gap-1 px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-4 h-4" /> Previous
                </button>
                <span className="text-gray-500">
                  Page <span className="font-semibold text-gray-900">{currentPage + 1}</span> of{' '}
                  <span className="font-semibold text-gray-900">{totalPages}</span>
                  <span className="text-gray-400 ml-2">({filtered.length} concepts)</span>
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={currentPage >= totalPages - 1}
                  className="flex items-center gap-1 px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  Next <ExternalLink className="w-4 h-4 rotate-90" />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// CodeSystem concept browser
// ---------------------------------------------------------------------------

const CodeSystemConceptsPage = ({ resource, onBack }: { resource: UiResource; onBack: () => void }) => {
  const [concepts, setConcepts] = useState<{ code: string; display?: string; definition?: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const PAGE = 50;

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`/CodeSystem/${resource.id}`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(data => setConcepts(data.concept ?? []))
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [resource.id]);

  const handleCopy = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 1500);
  };

  const hasDefinition = concepts.some(c => c.definition);
  const filtered = concepts.filter(c => {
    const q = filter.toLowerCase();
    return !q || c.code.toLowerCase().includes(q) || (c.display ?? '').toLowerCase().includes(q);
  });
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const currentPage = Math.min(page, totalPages - 1);
  const paginated = filtered.slice(currentPage * PAGE, currentPage * PAGE + PAGE);

  const exportCsvCs = () => {
    const header = hasDefinition ? 'code,display,definition\n' : 'code,display\n';
    const rows = filtered.map(c =>
      hasDefinition
        ? `${c.code},${JSON.stringify(c.display ?? '')},${JSON.stringify(c.definition ?? '')}`
        : `${c.code},${JSON.stringify(c.display ?? '')}`
    ).join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${resource.name}-concepts.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          <div className="h-5 w-px bg-gray-300" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="font-semibold text-gray-900 truncate">{resource.title || resource.name}</h1>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                resource.status === 'active' ? 'bg-green-100 text-green-700' :
                resource.status === 'draft'  ? 'bg-yellow-100 text-yellow-700' :
                'bg-gray-100 text-gray-500'}`}>{resource.status}</span>
              {resource.version && <span className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs font-medium">v{resource.version}</span>}
            </div>
            <p className="text-xs text-gray-400 font-mono truncate mt-0.5">{resource.url}</p>
          </div>
          <button
            onClick={exportCsvCs}
            disabled={loading || filtered.length === 0}
            className="flex items-center gap-1.5 text-sm bg-purple-600 text-white px-3 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-40 transition-colors"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {!loading && !error && (
          <div className="flex items-center gap-6 mb-4 text-sm text-gray-600">
            <span><span className="font-semibold text-gray-900">{concepts.length}</span> total concepts</span>
            {filter && <span><span className="font-semibold text-gray-900">{filtered.length}</span> matching</span>}
          </div>
        )}

        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-3 mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Filter by code or display…"
              value={filter}
              onChange={e => { setFilter(e.target.value); setPage(0); }}
              className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-purple-400 focus:border-purple-400"
            />
          </div>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-32 gap-3 text-gray-400">
            <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
            <p className="text-sm">Loading concepts…</p>
          </div>
        ) : error ? (
          <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-24 text-gray-400">
            <p className="text-sm">{filter ? `No concepts match "${filter}"` : 'This CodeSystem has no locally stored concepts.'}</p>
          </div>
        ) : (
          <>
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-gray-500 uppercase text-xs tracking-wide w-44">Code</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-500 uppercase text-xs tracking-wide">Display</th>
                    {hasDefinition && <th className="text-left px-4 py-3 font-medium text-gray-500 uppercase text-xs tracking-wide">Definition</th>}
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {paginated.map((c, i) => (
                    <tr key={`${c.code}-${i}`} className="hover:bg-purple-50 group transition-colors">
                      <td className="px-4 py-3 font-mono text-purple-700 text-sm align-top whitespace-nowrap">{c.code}</td>
                      <td className="px-4 py-3 text-gray-800 align-top">{c.display ?? <span className="italic text-gray-400">—</span>}</td>
                      {hasDefinition && (
                        <td className="px-4 py-3 text-gray-500 text-xs align-top">{c.definition ?? ''}</td>
                      )}
                      <td className="px-3 py-3 align-top">
                        <button
                          onClick={() => handleCopy(c.code)}
                          title="Copy code"
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-purple-600"
                        >
                          {copiedCode === c.code
                            ? <Check className="w-4 h-4 text-green-500" />
                            : <Copy className="w-4 h-4" />}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={currentPage === 0}
                  className="flex items-center gap-1 px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-4 h-4" /> Previous
                </button>
                <span className="text-gray-500">
                  Page <span className="font-semibold text-gray-900">{currentPage + 1}</span> of{' '}
                  <span className="font-semibold text-gray-900">{totalPages}</span>
                  <span className="text-gray-400 ml-2">({filtered.length} concepts)</span>
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={currentPage >= totalPages - 1}
                  className="flex items-center gap-1 px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  Next <ExternalLink className="w-4 h-4 rotate-90" />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const ModernPHINVADS = () => {
  const [activeTab, setActiveTab] = useState<'ValueSet' | 'CodeSystem' | 'ConceptMap'>('ValueSet');
  const [activeView, setActiveView] = useState('browse');
  const [mcpChatOpen, setMcpChatOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedResource, setSelectedResource] = useState<UiResource | null>(null);
  const [deepLinked, setDeepLinked] = useState(false);
  const [expansionResource, setExpansionResource] = useState<UiResource | null>(null);
  const [csConceptsResource, setCsConceptsResource] = useState<UiResource | null>(null);
  const [builderOpen, setBuilderOpen] = useState(false);

  const [resources, setResources] = useState<UiResource[]>([]);
  const [stats, setStats] = useState<ApiStats>({ total_valuesets: 0, total_codesystems: 0, archived_resources: 0, total_versions: 0 });
  const [loadingResources, setLoadingResources] = useState(true);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [errorResources, setErrorResources] = useState<string | null>(null);
  const [errorStats, setErrorStats] = useState<string | null>(null);

  // PHIN VADS sync state
  const [syncRuns, setSyncRuns] = useState<any[]>([]);
  const [syncResource, setSyncResource] = useState<'all' | 'valueset' | 'codesystem'>('all');
  const [syncTriggering, setSyncTriggering] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [showSyncOutput, setShowSyncOutput] = useState(false);

  // Concept / Code search mode
  const [searchMode, setSearchMode] = useState<'name' | 'concept'>('name');
  const [conceptEntries, setConceptEntries] = useState<ConceptSearchEntry[]>([]);
  const [externalResults, setExternalResults] = useState<Record<string, { systemName: string; results: SdoResult[] }>>({});
  const [loadingConcept, setLoadingConcept] = useState(false);
  const [loadingExternal, setLoadingExternal] = useState(false);
  const [sdoSystems, setSdoSystems] = useState<SdoSystem[]>([]);
  const [activeSdos, setActiveSdos] = useState<Set<string>>(new Set());
  const [expandedExternal, setExpandedExternal] = useState<Record<string, boolean>>({});

  // External search config
  const [showSearchConfig, setShowSearchConfig] = useState(false);
  const [externalSearchEnabled, setExternalSearchEnabled] = useState(true);

  // Edit / delete / archive / audit
  const [editingResource, setEditingResource] = useState<UiResource | null>(null);
  const [deletingResource, setDeletingResource] = useState<UiResource | null>(null);
  const [archivingResource, setArchivingResource] = useState<UiResource | null>(null);
  const [auditResource, setAuditResource] = useState<UiResource | null>(null);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  // CodeSystem table filters and pagination
  const [csStatusFilter, setCsStatusFilter] = useState('');
  const [csContentFilter, setCsContentFilter] = useState('');
  const [csPage, setCsPage] = useState(0);
  const CS_PAGE_SIZE = 25;

  // ValueSet table filters and pagination
  const [vsStatusFilter, setVsStatusFilter] = useState('');
  const [vsViewFilter, setVsViewFilter] = useState('');     // condition code
  const [vsSourceFilter, setVsSourceFilter] = useState(''); // import source
  const [vsArchivedView, setVsArchivedView] = useState(false); // show archived instead of active
  const [vsPage, setVsPage] = useState(0);
  const VS_PAGE_SIZE = 25;

  // ConceptMap browser state
  const [cmResources, setCmResources] = useState<ConceptMapSummary[]>([]);
  const [selectedCm, setSelectedCm] = useState<ConceptMapFull | null>(null);
  const [loadingCm, setLoadingCm] = useState(false);
  const [loadingCmDetail, setLoadingCmDetail] = useState(false);
  const [cmPage, setCmPage] = useState(0);
  const CM_PAGE_SIZE = 25;

  // Disease/condition views catalogue
  const [diseaseViews, setDiseaseViews] = useState<DiseaseView[]>([]);

  const debouncedSearch = useDebounce(searchTerm, 350);

  // Load stats once on mount
  const loadStats = useCallback(async () => {
    setLoadingStats(true);
    setErrorStats(null);
    try {
      setStats(await fetchStats());
    } catch (e) {
      setErrorStats((e as Error).message);
    } finally {
      setLoadingStats(false);
    }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);

  // PHIN VADS sync helpers
  const fetchSyncStatus = useCallback(async () => {
    try {
      const data = await apiFetch<{ runs: any[] }>('/admin/sync/status?limit=5');
      setSyncRuns(data.runs ?? []);
    } catch { /* silent — sync table may not exist yet on first boot */ }
  }, []);

  useEffect(() => { fetchSyncStatus(); }, [fetchSyncStatus]);

  // Poll every 5 s while a sync is running
  useEffect(() => {
    const running = syncRuns.some(r => r.status === 'running');
    if (!running) return;
    const id = setInterval(async () => {
      await fetchSyncStatus();
      await loadStats();
    }, 5000);
    return () => clearInterval(id);
  }, [syncRuns, fetchSyncStatus, loadStats]);

  const triggerSync = useCallback(async (preview = false) => {
    setSyncTriggering(true);
    setSyncError(null);
    setShowSyncOutput(false);
    try {
      const qs = new URLSearchParams({ resource: syncResource, preview: String(preview) });
      const resp = await fetch(`/admin/sync/phinvads?${qs}`, { method: 'POST' });
      if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText} — /admin/sync/phinvads`);
      await fetchSyncStatus();
    } catch (e) {
      setSyncError((e as Error).message);
    } finally {
      setSyncTriggering(false);
    }
  }, [syncResource, fetchSyncStatus]);

  // Load disease/condition views catalogue once on mount
  useEffect(() => {
    fetchDiseaseViews().then(setDiseaseViews).catch(() => {});
  }, []);

  // Load resources when tab, debounced search, or active filters change
  const loadResources = useCallback(async () => {
    if (activeTab === 'ConceptMap') return;
    setLoadingResources(true);
    setErrorResources(null);
    if (!deepLinkPending.current) setSelectedResource(null);
    try {
      const tab = activeTab as 'ValueSet' | 'CodeSystem';
      const status = tab === 'CodeSystem' ? csStatusFilter : (vsArchivedView ? '' : vsStatusFilter);
      const content = tab === 'CodeSystem' ? csContentFilter : undefined;
      const contextCode = tab === 'ValueSet' && !vsArchivedView ? vsViewFilter : undefined;
      const source = tab === 'ValueSet' ? vsSourceFilter : undefined;
      const archived = tab === 'ValueSet' ? vsArchivedView : false;
      setResources(await fetchResources(tab, debouncedSearch, status, content, contextCode, source, archived));
    } catch (e) {
      setErrorResources((e as Error).message);
    } finally {
      setLoadingResources(false);
    }
  }, [activeTab, debouncedSearch, csStatusFilter, csContentFilter, vsStatusFilter, vsViewFilter, vsSourceFilter, vsArchivedView]);

  useEffect(() => { loadResources(); }, [loadResources]);

  // Load ConceptMaps when tab is ConceptMap or search term changes
  useEffect(() => {
    if (activeTab !== 'ConceptMap') return;
    setLoadingCm(true);
    setSelectedCm(null);
    fetchConceptMaps(debouncedSearch)
      .then(setCmResources)
      .catch(() => setCmResources([]))
      .finally(() => setLoadingCm(false));
  }, [activeTab, debouncedSearch]);

  // Load available SDO systems once on mount; initialise all as active
  useEffect(() => {
    fetchSdoSystems().then(systems => {
      setSdoSystems(systems);
      setActiveSdos(new Set(systems.map(s => s.id)));
    }).catch(() => {});
  }, []);

  // deepLinkPending is true from mount until the identifier fetch resolves.
  // loadResources() checks this ref before clearing selectedResource so the
  // drawer open doesn't race with the list load clearing it.
  const deepLinkPending = useRef(
    new URLSearchParams(window.location.search).has('phts_oid')
  );

  // Deep-link handler: fires immediately on mount — no waiting for the resource list.
  useEffect(() => {
    if (!deepLinkPending.current) return;
    const params = new URLSearchParams(window.location.search);
    const oid = params.get('phts_oid');
    const type = (params.get('phts_type') ?? 'ValueSet') as 'ValueSet' | 'CodeSystem';
    window.history.replaceState({}, '', window.location.pathname);
    if (!oid) { deepLinkPending.current = false; return; }

    apiFetch<{ entry?: Array<{ resource: FhirResource }> }>(
      `/${type}?identifier=${encodeURIComponent(oid)}&_summary=true`
    ).then(bundle => {
      const first = bundle.entry?.[0]?.resource;
      if (first) {
        setActiveTab(type);
        setDeepLinked(true);
        setSelectedResource(toUiResource(first));
      }
    }).catch(() => {})
      .finally(() => { deepLinkPending.current = false; });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Concept/code search — fires when in concept mode with a debounced term
  useEffect(() => {
    if (searchMode !== 'concept' || !debouncedSearch.trim()) {
      setConceptEntries([]);
      setExternalResults({});
      return;
    }
    const term = debouncedSearch.trim();

    setLoadingConcept(true);
    fetchConceptSearch(term, 20)
      .then(setConceptEntries)
      .catch(() => setConceptEntries([]))
      .finally(() => setLoadingConcept(false));

    const activeSdoList = sdoSystems.filter(s => activeSdos.has(s.id));
    if (externalSearchEnabled && activeSdoList.length > 0) {
      setLoadingExternal(true);
      fetchExternalConceptSearch(term, activeSdoList)
        .then(setExternalResults)
        .catch(() => {})
        .finally(() => setLoadingExternal(false));
    } else {
      setExternalResults({});
    }
  }, [searchMode, debouncedSearch, sdoSystems, activeSdos, externalSearchEnabled]);

  // Fetch version history when a resource is selected
  useEffect(() => {
    if (!selectedResource) return;
    setLoadingHistory(true);
    fetchVersionHistory(selectedResource.resourceType, selectedResource.id)
      .then(history => {
        setSelectedResource((prev: UiResource | null) => prev ? { ...prev, versionHistory: history } : prev);
      })
      .finally(() => setLoadingHistory(false));
  }, [selectedResource?.id, selectedResource?.resourceType]);

  // View tags for the selected ValueSet
  const [resourceViewTags, setResourceViewTags] = useState<Set<string>>(new Set());
  const [viewTagsLoading, setViewTagsLoading] = useState(false);
  const [viewTagsOpen, setViewTagsOpen] = useState(false);

  useEffect(() => {
    setViewTagsOpen(false);
    if (!selectedResource || selectedResource.resourceType !== 'ValueSet') {
      setResourceViewTags(new Set());
      return;
    }
    setViewTagsLoading(true);
    fetchFullResource('ValueSet', selectedResource.id)
      .then(full => {
        const taggedCodes = new Set<string>(
          (full.useContext ?? []).flatMap(uc =>
            (uc.valueCodeableConcept?.coding ?? []).map((c: { code?: string }) => c.code ?? '')
          ).filter(Boolean)
        );
        setResourceViewTags(taggedCodes);
      })
      .catch(() => setResourceViewTags(new Set()))
      .finally(() => setViewTagsLoading(false));
  }, [selectedResource?.id]);

  // Download a resource as JSON
  const handleDownloadJson = useCallback((resource: UiResource) => {
    const url = `/${resource.resourceType}/${resource.id}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = `${resource.resourceType}-${resource.id}.json`;
    a.click();
  }, []);


  // Analytics dashboard
  const AnalyticsDashboard = () => (
    <div className="space-y-6">
      {errorStats && <ErrorBanner message={errorStats} onRetry={loadStats} />}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { icon: Layers, value: loadingStats ? '…' : stats.total_valuesets.toLocaleString(), label: 'Value Sets', from: 'from-blue-500', to: 'to-blue-600', muted: 'text-blue-100' },
          { icon: Database, value: loadingStats ? '…' : stats.total_codesystems.toLocaleString(), label: 'Code Systems', from: 'from-purple-500', to: 'to-purple-600', muted: 'text-purple-100' },
          { icon: Archive, value: loadingStats ? '…' : stats.archived_resources.toLocaleString(), label: 'Archived', from: 'from-amber-500', to: 'to-amber-600', muted: 'text-amber-100' },
          { icon: GitBranch, value: loadingStats ? '…' : stats.total_versions.toLocaleString(), label: 'Total Versions', from: 'from-green-500', to: 'to-green-600', muted: 'text-green-100' },
        ].map(({ icon: Icon, value, label, from, to, muted }) => (
          <div key={label} className={`bg-gradient-to-br ${from} ${to} text-white rounded-lg p-6`}>
            <div className="flex items-center justify-between mb-2">
              <Icon className="w-8 h-8 opacity-80" />
              <TrendingUp className="w-5 h-5" />
            </div>
            <p className="text-3xl font-bold mb-1">{value}</p>
            <p className={`${muted} text-sm`}>{label}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-500" /> Server Status
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            { label: 'FHIR Version', value: 'R4 (4.0.1)' },
            { label: 'API Endpoint', value: '/ValueSet, /CodeSystem' },
            { label: 'Documentation', value: 'Available at /docs' },
          ].map(({ label, value }) => (
            <div key={label} className="bg-gray-50 rounded-lg p-4">
              <p className="text-xs font-medium text-gray-500 uppercase mb-1">{label}</p>
              <p className="text-sm font-medium text-gray-900">{value}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-4 flex items-center gap-1">
          <Clock className="w-3 h-3" /> Full usage metrics available in Grafana at{' '}
          <a href={`${window.location.protocol}//${window.location.hostname}:3001`} target="_blank" rel="noreferrer" className="text-blue-500 hover:underline">
            Grafana
          </a>
        </p>
      </div>

      {/* PHIN VADS Sync Card */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <RefreshCw className="w-5 h-5 text-green-500" /> PHIN VADS Sync
        </h3>
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <select
            className="border border-gray-300 rounded px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-green-400"
            value={syncResource}
            onChange={e => setSyncResource(e.target.value as 'all' | 'valueset' | 'codesystem')}
            disabled={syncTriggering || syncRuns[0]?.status === 'running'}
          >
            <option value="all">All (ValueSets + CodeSystems)</option>
            <option value="valueset">ValueSets only</option>
            <option value="codesystem">CodeSystems only</option>
          </select>

          {/* Preview button */}
          <button
            onClick={() => triggerSync(true)}
            disabled={syncTriggering || syncRuns[0]?.status === 'running'}
            className="flex items-center gap-2 px-4 py-1.5 bg-gray-100 text-gray-700 border border-gray-300 text-sm font-medium rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title="Check what would be imported without actually importing anything"
          >
            {(syncTriggering || syncRuns[0]?.status === 'running') ? (
              <><RefreshCw className="w-4 h-4 animate-spin" /> Running…</>
            ) : (
              <><RefreshCw className="w-4 h-4" /> Preview</>
            )}
          </button>

          {/* Live import button */}
          <button
            onClick={() => triggerSync(false)}
            disabled={syncTriggering || syncRuns[0]?.status === 'running'}
            className="flex items-center gap-2 px-4 py-1.5 bg-green-600 text-white text-sm font-medium rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {(syncTriggering || syncRuns[0]?.status === 'running') ? (
              <><RefreshCw className="w-4 h-4 animate-spin" /> Sync in progress…</>
            ) : (
              <><RefreshCw className="w-4 h-4" /> Sync PHIN VADS</>
            )}
          </button>
        </div>

        <p className="text-xs text-gray-400 mb-4">
          Use <strong>Preview</strong> to see what would be imported (no changes made), then <strong>Sync PHIN VADS</strong> to commit the import.
        </p>

        {syncError && <p className="text-sm text-red-600 mb-3">{syncError}</p>}

        {syncRuns.length > 0 && (
          <div className="space-y-2">
            {syncRuns.map(run => (
              <div key={run.run_id} className={`rounded-lg p-3 text-sm border ${run.preview ? 'bg-amber-50 border-amber-200' : 'bg-gray-50 border-gray-200'}`}>
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <span className="text-gray-500 text-xs">
                    Run #{run.run_id} · {run.resource_type} ·{' '}
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                  </span>
                  <div className="flex items-center gap-2">
                    {run.preview && (
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                        PREVIEW
                      </span>
                    )}
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      run.status === 'success' ? 'bg-green-100 text-green-700' :
                      run.status === 'running'  ? 'bg-blue-100 text-blue-700' :
                                                 'bg-red-100 text-red-700'
                    }`}>
                      {run.status}
                    </span>
                  </div>
                </div>

                {run.status !== 'running' && (
                  <div className="flex gap-4 mt-1 text-xs text-gray-600">
                    <span className="text-green-600 font-medium">
                      {run.preview ? `${run.new_count} would be imported` : `+${run.new_count} imported`}
                    </span>
                    <span className="text-gray-500">{run.skipped_count} already present</span>
                    {run.error_count > 0 && <span className="text-red-500">{run.error_count} errors</span>}
                  </div>
                )}

                {/* Confirm import button shown after a completed preview */}
                {run.preview && run.status === 'success' && run.new_count > 0 && (
                  <button
                    onClick={() => triggerSync(false)}
                    disabled={syncTriggering || syncRuns[0]?.status === 'running'}
                    className="mt-2 flex items-center gap-1.5 px-3 py-1 bg-green-600 text-white text-xs font-medium rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <RefreshCw className="w-3 h-3" />
                    Confirm — import {run.new_count} new resource{run.new_count !== 1 ? 's' : ''}
                  </button>
                )}

                {run.output_tail && (
                  <div className="mt-2">
                    <button
                      onClick={() => setShowSyncOutput(v => !v)}
                      className="text-xs text-blue-500 hover:underline"
                    >
                      {showSyncOutput ? 'Hide' : 'Show'} output log
                    </button>
                    {showSyncOutput && (
                      <pre className="mt-1 bg-gray-900 text-green-300 text-xs rounded p-3 overflow-auto max-h-48 whitespace-pre-wrap">
                        {run.output_tail}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {syncRuns.length === 0 && (
          <p className="text-sm text-gray-400">No sync runs yet. Click "Preview" to check for new PHIN VADS resources.</p>
        )}
      </div>
    </div>
  );

  // Detail panel
  const DetailPanel = ({ resource, fullPage = false, onClose }: { resource: UiResource; fullPage?: boolean; onClose: () => void }) => {
    return (
      <div className={fullPage
        ? "fixed inset-0 bg-white z-50 overflow-y-auto"
        : "fixed inset-y-0 right-0 w-[36rem] bg-white shadow-2xl border-l border-gray-200 z-50 overflow-y-auto"}>
        <div className="sticky top-0 bg-white border-b border-gray-200 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {fullPage && (
              <a href="/" className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 font-medium" title="Back to PH-TS">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
                PH-TS
              </a>
            )}
            <h2 className="font-semibold text-gray-900">{fullPage ? (resource.title || resource.name || 'Resource Details') : 'Resource Details'}</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none" title="Close">×</button>
        </div>
        <div className={`p-6 space-y-6${fullPage ? ' max-w-4xl mx-auto' : ''}`}>
          <div>
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <StatusBadge status={resource.status} />
              <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">v{resource.version}</span>
              <SourceBadge source={resource.source} />
            </div>
            <h3 className="text-xl font-bold text-gray-900 mb-1">{resource.title || resource.name}</h3>
            <p className="text-sm font-mono text-gray-500 break-all">{resource.url}</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[['Concepts', resource.conceptCount], ['Resource Type', resource.resourceType]].map(([label, val]) => (
              <div key={String(label)} className="bg-gray-50 p-3 rounded-lg text-center">
                <p className="text-2xl font-bold text-gray-900">{val}</p>
                <p className="text-xs text-gray-500 mt-1">{label}</p>
              </div>
            ))}
          </div>

          <div className="space-y-4">
            {resource.definition && (
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase">Description</label>
                <p className="text-sm text-gray-700 mt-1">{resource.definition}</p>
              </div>
            )}
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase">ID</label>
              <p className="text-sm font-mono bg-gray-50 p-2 rounded mt-1 break-all">{resource.id}</p>
            </div>

            {/* Condition / Disease Views — ValueSet only */}
            {resource.resourceType === 'ValueSet' && diseaseViews.length > 0 && (() => {
              const taggedCount = diseaseViews.filter(v => resourceViewTags.has(v.code)).length;
              return (
                <div className="border border-gray-200 rounded-lg overflow-hidden">
                  {/* Collapsible header */}
                  <button
                    onClick={() => setViewTagsOpen(o => !o)}
                    className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors"
                  >
                    <span className="text-xs font-medium text-gray-600 uppercase flex items-center gap-1.5">
                      Condition Views
                      {viewTagsLoading && <Loader2 className="w-3 h-3 animate-spin" />}
                    </span>
                    <div className="flex items-center gap-2">
                      {taggedCount > 0 && (
                        <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full font-medium">
                          {taggedCount}
                        </span>
                      )}
                      <ChevronRight className={`w-3.5 h-3.5 text-gray-400 transition-transform ${viewTagsOpen ? 'rotate-90' : ''}`} />
                    </div>
                  </button>

                  {/* Expandable list */}
                  {viewTagsOpen && (
                    <div className="divide-y divide-gray-100">
                      {diseaseViews.map(v => {
                        const tagged = resourceViewTags.has(v.code);
                        return (
                          <button
                            key={v.id}
                            title={v.description}
                            onClick={() => {
                              tagValueSetView(resource.id, v.id, tagged)
                                .then(() => {
                                  setResourceViewTags(prev => {
                                    const next = new Set(prev);
                                    tagged ? next.delete(v.code) : next.add(v.code);
                                    return next;
                                  });
                                  fetchDiseaseViews().then(setDiseaseViews).catch(() => {});
                                })
                                .catch(() => {});
                            }}
                            className={`w-full flex items-center gap-2 px-3 py-2 text-left text-xs transition-colors ${
                              tagged ? 'bg-blue-50 text-blue-800' : 'bg-white text-gray-700 hover:bg-gray-50'
                            }`}
                          >
                            <span className={`w-4 h-4 flex-shrink-0 rounded border flex items-center justify-center transition-colors ${
                              tagged ? 'bg-blue-600 border-blue-600' : 'border-gray-300 bg-white'
                            }`}>
                              {tagged && (
                                <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 10 8">
                                  <path d="M1 4l3 3 5-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                </svg>
                              )}
                            </span>
                            <span className="flex-1">{v.display}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })()}

            <div>
              <label className="text-xs font-medium text-gray-500 uppercase mb-2 block">
                Version History
                {loadingHistory && <Loader2 className="w-3 h-3 inline ml-2 animate-spin" />}
              </label>
              {resource.versionHistory.length === 0 && !loadingHistory && (
                <p className="text-xs text-gray-400 italic">No version history recorded yet.</p>
              )}
              <div className="space-y-2">
                {resource.versionHistory.map(v => (
                  <div key={v.version} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                    <div className="w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-semibold text-sm flex-shrink-0">
                      v{v.version}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">{v.summary || 'Updated'}{v.author ? ` by ${v.author}` : ''}</p>
                      <p className="text-xs text-gray-500">{new Date(v.timestamp).toLocaleDateString()}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Expand button — opens full expansion page */}
          {resource.resourceType === 'ValueSet' && (
            <button
              onClick={() => { setExpansionResource(resource); setSelectedResource(null); }}
              className="w-full bg-blue-600 text-white py-3 px-4 rounded-lg hover:bg-blue-700 transition-colors font-medium flex items-center justify-center gap-2"
            >
              <FileCode className="w-4 h-4" /> View Expansion ($expand)
            </button>
          )}

          {/* Edit / Archive / Delete — ValueSet only */}
          {resource.resourceType === 'ValueSet' && (
            <>
              <div className="flex gap-2">
                <button
                  onClick={() => setEditingResource(resource)}
                  className="flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg border border-blue-300 text-blue-700 text-sm font-medium hover:bg-blue-50 transition-colors"
                >
                  <Pencil className="w-4 h-4" /> Edit
                </button>
                <button
                  onClick={() => setArchivingResource(resource)}
                  className="flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg border border-amber-300 text-amber-700 text-sm font-medium hover:bg-amber-50 transition-colors"
                >
                  <Archive className="w-4 h-4" /> Archive
                </button>
              </div>
              <button
                onClick={() => setDeletingResource(resource)}
                className="w-full flex items-center justify-center gap-2 py-1.5 px-4 rounded-lg border border-red-200 text-red-500 text-xs font-medium hover:bg-red-50 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" /> Permanently delete
              </button>
            </>
          )}

          {/* Browse Concepts + Edit — CodeSystem */}
          {resource.resourceType === 'CodeSystem' && (
            <>
              {(resource.conceptCount ?? 0) > 0 && (
                <button
                  onClick={() => { setCsConceptsResource(resource); setSelectedResource(null); }}
                  className="w-full bg-purple-600 text-white py-3 px-4 rounded-lg hover:bg-purple-700 transition-colors font-medium flex items-center justify-center gap-2"
                >
                  <FileCode className="w-4 h-4" /> Browse Concepts ({resource.conceptCount})
                </button>
              )}
              <button
                onClick={() => setEditingResource(resource)}
                className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg border border-purple-300 text-purple-700 text-sm font-medium hover:bg-purple-50 transition-colors"
              >
                <Pencil className="w-4 h-4" /> Edit Display Name / Details
              </button>
            </>
          )}

          <div className="pt-4 border-t border-gray-200 space-y-2">
            {resource.url && (
            <a
              href={resource.resourceType === 'ValueSet'
                ? `/ValueSet/$expand?url=${encodeURIComponent(resource.url)}`
                : `/CodeSystem/$lookup?system=${encodeURIComponent(resource.url)}`}
              target="_blank"
              rel="noreferrer"
              className="w-full bg-white border border-gray-300 text-gray-700 py-2 px-4 rounded-lg hover:bg-gray-50 text-sm flex items-center justify-center gap-2"
            >
              <ExternalLink className="w-4 h-4" /> Raw {resource.resourceType === 'ValueSet' ? '$expand' : '$lookup'} JSON
            </a>
            )}
            <button
              onClick={() => handleDownloadJson(resource)}
              className="w-full bg-white border border-gray-300 text-gray-700 py-2 px-4 rounded-lg hover:bg-gray-50 text-sm flex items-center justify-center gap-2"
            >
              <Download className="w-4 h-4" /> Download JSON
            </button>
            <a
              href={`/${resource.resourceType}/${resource.id}/_history`}
              target="_blank"
              rel="noreferrer"
              className="w-full bg-white border border-gray-300 text-gray-700 py-2 px-4 rounded-lg hover:bg-gray-50 text-sm flex items-center justify-center gap-2"
            >
              <GitBranch className="w-4 h-4" /> Full History (FHIR)
            </a>
            <button
              onClick={async () => {
                setAuditLoading(true);
                setAuditResource(resource);
                setAuditLog([]);
                try { setAuditLog(await fetchAuditLog(resource.id, resource.resourceType)); }
                catch { setAuditLog([]); }
                finally { setAuditLoading(false); }
              }}
              className="w-full bg-white border border-gray-300 text-gray-700 py-2 px-4 rounded-lg hover:bg-gray-50 text-sm flex items-center justify-center gap-2"
            >
              <ScrollText className="w-4 h-4" /> Audit Log
            </button>
          </div>
        </div>
      </div>
    );
  };

  // -------------------------------------------------------------------------
  // Edit ValueSet modal
  // -------------------------------------------------------------------------
  const EditValueSetModal = ({ resource, onClose, onSaved }: {
    resource: UiResource;
    onClose: () => void;
    onSaved: () => void;
  }) => {
    const [fullResource, setFullResource] = useState<FhirResource | null>(null);
    const [loadingFull, setLoadingFull] = useState(true);
    const [form, setForm] = useState({ name: resource.name, title: resource.title, description: resource.definition, status: resource.status, version: resource.version });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
      fetchFullResource('ValueSet', resource.id)
        .then(r => { setFullResource(r); setForm({ name: r.name ?? resource.name, title: r.title ?? resource.title, description: r.description ?? resource.definition, status: r.status, version: r.version ?? resource.version }); })
        .catch(e => setError((e as Error).message))
        .finally(() => setLoadingFull(false));
    }, [resource.id]);

    const handleSave = async () => {
      if (!fullResource) return;
      setSaving(true); setError(null);
      try {
        await updateResource('ValueSet', resource.id, { ...fullResource, name: form.name, title: form.title, description: form.description, status: form.status, version: form.version });
        onSaved();
      } catch (e) { setError((e as Error).message); }
      finally { setSaving(false); }
    };

    return (
      <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h2 className="text-base font-semibold text-gray-900">Edit Value Set</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
          </div>
          {loadingFull ? (
            <div className="p-8 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
          ) : (
            <div className="px-6 py-4 space-y-4">
              {error && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">{error}</p>}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Title</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Name <span className="text-gray-400 font-normal">(machine-readable)</span></label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                    <option value="active">Active</option>
                    <option value="draft">Draft</option>
                    <option value="retired">Retired</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </div>
                <div className="w-32">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Version</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" value={form.version} onChange={e => setForm(f => ({ ...f, version: e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
                <textarea rows={4} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 resize-none" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
              </div>
            </div>
          )}
          <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
            <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
            <button onClick={handleSave} disabled={saving || loadingFull} className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save Changes
            </button>
          </div>
        </div>
      </div>
    );
  };

  // -------------------------------------------------------------------------
  // Edit CodeSystem modal
  // -------------------------------------------------------------------------
  const EditCodeSystemModal = ({ resource, onClose, onSaved }: {
    resource: UiResource;
    onClose: () => void;
    onSaved: () => void;
  }) => {
    const [fullResource, setFullResource] = useState<FhirResource | null>(null);
    const [loadingFull, setLoadingFull] = useState(true);
    const [form, setForm] = useState({ name: resource.name, title: resource.title, description: resource.definition, status: resource.status, version: resource.version });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
      fetchFullResource('CodeSystem', resource.id)
        .then(r => { setFullResource(r); setForm({ name: r.name ?? resource.name, title: r.title ?? resource.title, description: r.description ?? resource.definition, status: r.status, version: r.version ?? resource.version }); })
        .catch(e => setError((e as Error).message))
        .finally(() => setLoadingFull(false));
    }, [resource.id]);

    const handleSave = async () => {
      if (!fullResource) return;
      setSaving(true); setError(null);
      try {
        await updateResource('CodeSystem', resource.id, { ...fullResource, name: form.name, title: form.title, description: form.description, status: form.status, version: form.version });
        onSaved();
      } catch (e) { setError((e as Error).message); }
      finally { setSaving(false); }
    };

    return (
      <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h2 className="text-base font-semibold text-gray-900">Edit Code System</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
          </div>
          {loadingFull ? (
            <div className="p-8 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
          ) : (
            <div className="px-6 py-4 space-y-4">
              {error && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">{error}</p>}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Display Name / Title <span className="text-gray-400 font-normal">(shown as system name in ValueSet expansions)</span>
                </label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 focus:border-purple-500" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Name <span className="text-gray-400 font-normal">(machine-readable)</span></label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-purple-500 focus:border-purple-500" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500" value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                    <option value="active">Active</option>
                    <option value="draft">Draft</option>
                    <option value="retired">Retired</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </div>
                <div className="w-32">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Version</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500" value={form.version} onChange={e => setForm(f => ({ ...f, version: e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
                <textarea rows={4} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 resize-none" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
              </div>
            </div>
          )}
          <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
            <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
            <button onClick={handleSave} disabled={saving || loadingFull} className="px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save Changes
            </button>
          </div>
        </div>
      </div>
    );
  };

  // -------------------------------------------------------------------------
  // Delete confirmation dialog
  // -------------------------------------------------------------------------
  const DeleteConfirmDialog = ({ resource, onClose, onDeleted }: {
    resource: UiResource;
    onClose: () => void;
    onDeleted: () => void;
  }) => {
    const [deleting, setDeleting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleDelete = async () => {
      setDeleting(true); setError(null);
      try {
        await deleteResource(resource.resourceType, resource.id);
        onDeleted();
      } catch (e) { setError((e as Error).message); setDeleting(false); }
    };

    return (
      <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
          <div className="p-6">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center flex-shrink-0">
                <Trash2 className="w-5 h-5 text-red-600" />
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="text-base font-semibold text-gray-900 mb-1">Delete Value Set</h2>
                <p className="text-sm text-gray-600">Are you sure you want to delete <span className="font-medium">"{resource.title || resource.name}"</span>? This will permanently remove the resource and all its version history.</p>
                {error && <p className="text-sm text-red-600 mt-3 bg-red-50 border border-red-200 rounded-lg p-2">{error}</p>}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-3 px-6 pb-5">
            <button onClick={onClose} disabled={deleting} className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50">Cancel</button>
            <button onClick={handleDelete} disabled={deleting} className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center gap-2">
              {deleting && <Loader2 className="w-4 h-4 animate-spin" />} Delete
            </button>
          </div>
        </div>
      </div>
    );
  };

  // -------------------------------------------------------------------------
  // Archive confirmation dialog
  // -------------------------------------------------------------------------
  const ArchiveConfirmDialog = ({ resource, onClose, onArchived }: {
    resource: UiResource;
    onClose: () => void;
    onArchived: () => void;
  }) => {
    const [archiving, setArchiving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleArchive = async () => {
      setArchiving(true); setError(null);
      try {
        await archiveResource(resource.id);
        onArchived();
      } catch (e) { setError((e as Error).message); setArchiving(false); }
    };

    return (
      <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
          <div className="p-6">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center flex-shrink-0">
                <Archive className="w-5 h-5 text-amber-600" />
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="text-base font-semibold text-gray-900 mb-1">Archive Value Set</h2>
                <p className="text-sm text-gray-600">Archive <span className="font-medium">"{resource.title || resource.name}"</span>? It will be hidden from search but kept in the database and can be restored later.</p>
                {error && <p className="text-sm text-red-600 mt-3 bg-red-50 border border-red-200 rounded-lg p-2">{error}</p>}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-3 px-6 pb-5">
            <button onClick={onClose} disabled={archiving} className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50">Cancel</button>
            <button onClick={handleArchive} disabled={archiving} className="px-4 py-2 text-sm bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 flex items-center gap-2">
              {archiving && <Loader2 className="w-4 h-4 animate-spin" />} Archive
            </button>
          </div>
        </div>
      </div>
    );
  };

  // -------------------------------------------------------------------------
  // Audit log modal
  // -------------------------------------------------------------------------
  const AuditLogModal = ({ resource, entries, loading, onClose }: {
    resource: UiResource;
    entries: AuditEntry[];
    loading: boolean;
    onClose: () => void;
  }) => {
    const actionColours: Record<string, string> = {
      create:    'bg-green-100 text-green-700',
      update:    'bg-blue-100 text-blue-700',
      delete:    'bg-red-100 text-red-600',
      archive:   'bg-amber-100 text-amber-700',
      unarchive: 'bg-teal-100 text-teal-700',
    };

    return (
      <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg flex flex-col max-h-[80vh]">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 flex-shrink-0">
            <div>
              <h2 className="text-base font-semibold text-gray-900">Audit Log</h2>
              <p className="text-xs text-gray-400 mt-0.5 truncate">{resource.title || resource.name}</p>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
          </div>
          <div className="overflow-y-auto flex-1 p-4">
            {loading ? (
              <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
            ) : entries.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-8 italic">No audit entries found.</p>
            ) : (
              <div className="space-y-2">
                {entries.map(entry => (
                  <div key={entry.id} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium flex-shrink-0 mt-0.5 ${actionColours[entry.action] ?? 'bg-gray-100 text-gray-600'}`}>
                      {entry.action}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-800">{entry.summary || `${entry.action} by ${entry.actor ?? 'system'}`}</p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {new Date(entry.timestamp).toLocaleString()}{entry.actor ? ` · ${entry.actor}` : ''}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  if (builderOpen) {
    return <ValueSetBuilder onBack={() => { setBuilderOpen(false); loadResources(); }} />;
  }

  if (mcpChatOpen) {
    return <MCPChatPage onBack={() => setMcpChatOpen(false)} />;
  }

  if (expansionResource) {
    return <ExpansionPage resource={expansionResource} onBack={() => setExpansionResource(null)} />;
  }

  if (csConceptsResource) {
    return <CodeSystemConceptsPage resource={csConceptsResource} onBack={() => setCsConceptsResource(null)} />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AppLogo size={40} className="rounded-xl shadow-sm flex-shrink-0" />
              <div>
                <h1 className="text-xl font-bold tracking-tight text-gray-900">PH-TS</h1>
                <p className="text-gray-400 text-xs font-medium tracking-wide uppercase">Public Health Terminology Service</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {!loadingStats && (
                <div className="hidden md:flex items-center gap-4 text-sm text-gray-500">
                  <span className="flex items-center gap-1.5"><Layers className="w-4 h-4 text-blue-500" />{stats.total_valuesets} ValueSets</span>
                  <span className="flex items-center gap-1.5"><Database className="w-4 h-4 text-purple-500" />{stats.total_codesystems} CodeSystems</span>
                </div>
              )}
              <button
                onClick={() => setBuilderOpen(true)}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors text-sm font-medium flex items-center gap-2 shadow-sm"
              >
                <Plus className="w-4 h-4" /> Create Value Set
              </button>
              <a href="/docs" target="_blank" rel="noreferrer"
                className="bg-gray-100 hover:bg-gray-200 text-gray-600 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                API Docs
              </a>
            </div>
          </div>
        </div>
      </header>

      {/* Nav tabs */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex gap-6">
            {[
              { id: 'browse', label: 'Browse Resources', icon: Layers },
              { id: 'analytics', label: 'Analytics', icon: TrendingUp },
            ].map(view => (
              <button key={view.id} onClick={() => setActiveView(view.id)}
                className={`flex items-center gap-2 px-1 py-4 border-b-2 transition-colors ${
                  activeView === view.id ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'
                }`}>
                <view.icon className="w-4 h-4" />
                <span className="font-medium text-sm">{view.label}</span>
              </button>
            ))}
            <button
              onClick={() => setMcpChatOpen(true)}
              className="flex items-center gap-2 px-1 py-4 border-b-2 border-transparent text-gray-600 hover:text-indigo-600 transition-colors"
            >
              <MessageSquare className="w-4 h-4" />
              <span className="font-medium text-sm">MCP Chat</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {activeView === 'analytics' ? <AnalyticsDashboard /> : (
          <>
            {/* Search + filters */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
              <div className="flex gap-3 mb-4">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
                  <input
                    type="text"
                    placeholder={searchMode === 'concept' ? 'Search for a concept or code across all value sets…' : 'Search by name…'}
                    className="w-full pl-10 pr-10 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                  />
                  {searchTerm && (
                    <button
                      onClick={() => setSearchTerm('')}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                      title="Clear search"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
                {/* Search mode toggle */}
                <div className="flex rounded-lg border border-gray-300 overflow-hidden flex-shrink-0">
                  {(['name', 'concept'] as const).map(mode => (
                    <button
                      key={mode}
                      onClick={() => { setSearchMode(mode); setSearchTerm(''); }}
                      className={`px-4 py-2 text-sm font-medium transition-colors ${
                        searchMode === mode
                          ? 'bg-blue-600 text-white'
                          : 'bg-white text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      {mode === 'name' ? 'Name' : 'Concept / Code'}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex gap-2">
                  {searchMode === 'name' && (
                    <>
                      {([['ValueSet', 'Value Sets', 'bg-blue-600'], ['CodeSystem', 'Code Systems', 'bg-purple-600']] as const).map(([id, label, active]) => (
                        <button key={id} onClick={() => setActiveTab(id)}
                          className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                            activeTab === id ? `${active} text-white` : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                          }`}>{label}</button>
                      ))}
                      <button onClick={() => setActiveTab('ConceptMap')}
                        className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                          activeTab === 'ConceptMap' ? 'bg-amber-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}>Concept Maps</button>
                    </>
                  )}
                  {searchMode === 'concept' && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={() => setExternalSearchEnabled(e => !e)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border font-medium transition-colors ${
                          externalSearchEnabled
                            ? 'bg-green-50 text-green-700 border-green-300 hover:bg-green-100'
                            : 'bg-gray-100 text-gray-500 border-gray-300 hover:bg-gray-200'
                        }`}
                        title="Toggle external vocabulary search"
                      >
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${externalSearchEnabled ? 'bg-green-500' : 'bg-gray-400'}`} />
                        External search {externalSearchEnabled ? 'on' : 'off'}
                      </button>
                      <button
                        onClick={() => setShowSearchConfig(true)}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                        title="Configure external code systems"
                      >
                        <Settings className="w-3.5 h-3.5" />
                        {activeSdos.size === sdoSystems.length ? 'All systems' : `${activeSdos.size} of ${sdoSystems.length} systems`}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Results — Name mode */}
            {searchMode === 'name' && (
              errorResources ? (
                <ErrorBanner message={errorResources} onRetry={loadResources} />
              ) : loadingResources ? (
                <LoadingSpinner message={`Loading ${activeTab}s…`} />
              ) : activeTab === 'CodeSystem' ? (() => {
                // --- CodeSystem table view with filters + pagination ---
                // Filtering is handled server-side; resources is already filtered
                const csTotalPages = Math.max(1, Math.ceil(resources.length / CS_PAGE_SIZE));
                const csPageClamped = Math.min(csPage, csTotalPages - 1);
                const csPaginated = resources.slice(csPageClamped * CS_PAGE_SIZE, csPageClamped * CS_PAGE_SIZE + CS_PAGE_SIZE);
                const pageWindow = Math.max(0, Math.min(csTotalPages - 5, csPageClamped - 2));

                return (
                  <>
                    {/* Filter bar */}
                    <div className="mb-4 flex flex-wrap items-center gap-3">
                      <Filter className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      <div className="flex items-center gap-1.5">
                        <label className="text-xs text-gray-500 font-medium whitespace-nowrap">Status</label>
                        <select
                          value={csStatusFilter}
                          onChange={e => { setCsStatusFilter(e.target.value); setCsPage(0); }}
                          className="text-xs border border-gray-300 rounded-md px-2 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-purple-400"
                        >
                          <option value="">All statuses</option>
                          <option value="active">Active</option>
                          <option value="draft">Draft</option>
                          <option value="retired">Retired</option>
                          <option value="unknown">Unknown</option>
                        </select>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <label className="text-xs text-gray-500 font-medium whitespace-nowrap">Content</label>
                        <select
                          value={csContentFilter}
                          onChange={e => { setCsContentFilter(e.target.value); setCsPage(0); }}
                          className="text-xs border border-gray-300 rounded-md px-2 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-purple-400"
                        >
                          <option value="">All types</option>
                          <option value="complete">Complete</option>
                          <option value="fragment">Fragment</option>
                          <option value="not-present">Not Present</option>
                          <option value="example">Example</option>
                          <option value="supplement">Supplement</option>
                        </select>
                      </div>
                      {(csStatusFilter || csContentFilter) && (
                        <button
                          onClick={() => { setCsStatusFilter(''); setCsContentFilter(''); setCsPage(0); }}
                          className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 border border-gray-300 rounded-md px-2 py-1.5 hover:bg-gray-50 transition-colors"
                        >
                          <X className="w-3 h-3" /> Clear filters
                        </button>
                      )}
                      <p className="ml-auto text-sm text-gray-600">
                        Showing <span className="font-semibold">{resources.length}</span>
                        <span className="text-gray-400"> code systems</span>
                        {debouncedSearch && <span className="text-gray-400"> matching "{debouncedSearch}"</span>}
                      </p>
                    </div>

                    {resources.length === 0 ? (
                      <div className="text-center py-20 text-gray-400">
                        <Database className="w-12 h-12 mx-auto mb-3 opacity-30" />
                        <p className="text-sm">
                          {debouncedSearch || csStatusFilter || csContentFilter
                            ? 'No code systems match the current filters.'
                            : 'No code systems found. Import data using the migration tool.'}
                        </p>
                      </div>
                    ) : (
                      <>
                        {/* Table */}
                        <div className="border border-gray-200 rounded-lg overflow-hidden">
                          <table className="w-full text-sm">
                            <thead className="bg-gray-50 border-b border-gray-200">
                              <tr>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Display Name / Title</th>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide hidden lg:table-cell">URL</th>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Status</th>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Content</th>
                                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Concepts</th>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide hidden sm:table-cell">Version</th>
                                <th className="px-4 py-3 w-16" />
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {csPaginated.map(cs => (
                                <tr
                                  key={cs.id}
                                  className="hover:bg-purple-50 cursor-pointer transition-colors group"
                                  onClick={() => setSelectedResource(cs)}
                                >
                                  <td className="px-4 py-3">
                                    <div className="font-medium text-gray-900 group-hover:text-purple-700 transition-colors line-clamp-1">
                                      {cs.title || cs.name}
                                    </div>
                                    {cs.definition && (
                                      <div className="text-xs text-gray-400 mt-0.5 line-clamp-1">{cs.definition}</div>
                                    )}
                                  </td>
                                  <td className="px-4 py-3 hidden lg:table-cell max-w-xs">
                                    <span className="text-xs font-mono text-gray-400 truncate block">{cs.url}</span>
                                  </td>
                                  <td className="px-4 py-3 whitespace-nowrap">
                                    <StatusBadge status={cs.status} />
                                  </td>
                                  <td className="px-4 py-3 whitespace-nowrap">
                                    <ContentBadge content={cs.content} />
                                  </td>
                                  <td className="px-4 py-3 text-right whitespace-nowrap">
                                    <span className="text-xs text-gray-500">{cs.conceptCount.toLocaleString()}</span>
                                  </td>
                                  <td className="px-4 py-3 hidden sm:table-cell whitespace-nowrap">
                                    {cs.version && <span className="text-xs text-purple-600 font-medium">v{cs.version}</span>}
                                  </td>
                                  <td className="px-4 py-3">
                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                      <button
                                        onClick={e => { e.stopPropagation(); setEditingResource(cs); }}
                                        title="Edit display name / details"
                                        className="text-gray-400 hover:text-purple-600"
                                      >
                                        <Pencil className="w-4 h-4" />
                                      </button>
                                      <button
                                        onClick={e => { e.stopPropagation(); handleDownloadJson(cs); }}
                                        title="Download JSON"
                                        className="text-gray-400 hover:text-purple-600"
                                      >
                                        <Download className="w-4 h-4" />
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>

                        {/* Pagination */}
                        {csTotalPages > 1 && (
                          <div className="mt-4 flex items-center justify-between gap-2 flex-wrap">
                            <p className="text-xs text-gray-500">
                              Page {csPageClamped + 1} of {csTotalPages} · {resources.length} results
                            </p>
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => setCsPage(p => Math.max(0, p - 1))}
                                disabled={csPageClamped === 0}
                                className="p-1.5 border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                              >
                                <ChevronLeft className="w-4 h-4" />
                              </button>
                              {Array.from({ length: Math.min(5, csTotalPages) }, (_, i) => {
                                const p = pageWindow + i;
                                return (
                                  <button
                                    key={p}
                                    onClick={() => setCsPage(p)}
                                    className={`px-3 py-1.5 text-xs border rounded-md transition-colors ${
                                      p === csPageClamped
                                        ? 'bg-purple-600 text-white border-purple-600'
                                        : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                                    }`}
                                  >
                                    {p + 1}
                                  </button>
                                );
                              })}
                              <button
                                onClick={() => setCsPage(p => Math.min(csTotalPages - 1, p + 1))}
                                disabled={csPageClamped >= csTotalPages - 1}
                                className="p-1.5 border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                              >
                                <ChevronRight className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </>
                );
              })() : activeTab === 'ConceptMap' ? (() => {
                // --- ConceptMap table view ---
                const cmTotalPages = Math.max(1, Math.ceil(cmResources.length / CM_PAGE_SIZE));
                const cmPageClamped = Math.min(cmPage, cmTotalPages - 1);
                const cmPaginated = cmResources.slice(cmPageClamped * CM_PAGE_SIZE, cmPageClamped * CM_PAGE_SIZE + CM_PAGE_SIZE);
                return (
                  <>
                    <p className="mb-4 text-sm text-gray-600">
                      Showing <span className="font-semibold">{cmResources.length}</span>
                      <span className="text-gray-400"> concept maps</span>
                      {debouncedSearch && <span className="text-gray-400"> matching "{debouncedSearch}"</span>}
                    </p>
                    {loadingCm ? (
                      <LoadingSpinner message="Loading concept maps…" />
                    ) : cmResources.length === 0 ? (
                      <div className="text-center py-20 text-gray-400">
                        <GitBranch className="w-12 h-12 mx-auto mb-3 opacity-30" />
                        <p className="text-sm">{debouncedSearch ? 'No concept maps match the search.' : 'No concept maps found.'}</p>
                      </div>
                    ) : (
                      <>
                        <div className="border border-gray-200 rounded-lg overflow-hidden">
                          <table className="w-full text-sm">
                            <thead className="bg-gray-50 border-b border-gray-200">
                              <tr>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Name / Title</th>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide hidden md:table-cell">Source → Target</th>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Status</th>
                                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Mappings</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {cmPaginated.map(cm => (
                                <tr key={cm.id}
                                  className="hover:bg-amber-50 cursor-pointer transition-colors group"
                                  onClick={() => {
                                    setLoadingCmDetail(true);
                                    setSelectedCm(null);
                                    fetchConceptMapFull(cm.id)
                                      .then(setSelectedCm)
                                      .catch(() => {})
                                      .finally(() => setLoadingCmDetail(false));
                                  }}
                                >
                                  <td className="px-4 py-3">
                                    <div className="font-medium text-gray-900 group-hover:text-amber-700 transition-colors line-clamp-1">{cm.title || cm.name}</div>
                                    {cm.description && <div className="text-xs text-gray-400 mt-0.5 line-clamp-1">{cm.description}</div>}
                                  </td>
                                  <td className="px-4 py-3 hidden md:table-cell">
                                    <div className="text-xs font-mono text-gray-500 space-y-0.5">
                                      {cm.sources.slice(0, 2).map((s, i) => (
                                        <div key={i} className="flex items-center gap-1 truncate max-w-xs">
                                          <span className="truncate">{s.split('/').pop() ?? s}</span>
                                          <span className="text-gray-300 mx-1">→</span>
                                          <span className="truncate">{(cm.targets[i] ?? cm.targets[0] ?? '?').split('/').pop()}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </td>
                                  <td className="px-4 py-3 whitespace-nowrap"><StatusBadge status={cm.status} /></td>
                                  <td className="px-4 py-3 text-right whitespace-nowrap">
                                    <span className="text-xs text-gray-500">{cm.mappingCount.toLocaleString()}</span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {cmTotalPages > 1 && (
                          <div className="mt-4 flex items-center justify-between gap-2 flex-wrap">
                            <p className="text-xs text-gray-500">Page {cmPageClamped + 1} of {cmTotalPages} · {cmResources.length} results</p>
                            <div className="flex items-center gap-1">
                              <button onClick={() => setCmPage(p => Math.max(0, p - 1))} disabled={cmPageClamped === 0}
                                className="p-1.5 border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                                <ChevronLeft className="w-4 h-4" />
                              </button>
                              <button onClick={() => setCmPage(p => Math.min(cmTotalPages - 1, p + 1))} disabled={cmPageClamped >= cmTotalPages - 1}
                                className="p-1.5 border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                                <ChevronRight className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                    {/* ConceptMap detail side panel */}
                    {(selectedCm || loadingCmDetail) && (
                      <div className="fixed inset-0 bg-black/40 z-40 flex items-start justify-end" onClick={() => { setSelectedCm(null); }}>
                        <div className="w-full max-w-2xl h-full bg-white shadow-2xl flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
                          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 bg-amber-50">
                            <div className="min-w-0">
                              <h2 className="font-semibold text-gray-900 truncate">{selectedCm?.title || selectedCm?.name || 'Concept Map'}</h2>
                              <div className="flex items-center gap-2 mt-1 flex-wrap">
                                {selectedCm && <StatusBadge status={selectedCm.status} />}
                                <span className="text-xs text-gray-400">{selectedCm?.mappingCount.toLocaleString()} mappings</span>
                              </div>
                            </div>
                            <button onClick={() => setSelectedCm(null)} className="text-gray-400 hover:text-gray-700 ml-4"><X className="w-5 h-5" /></button>
                          </div>
                          <div className="flex-1 overflow-y-auto p-5">
                            {loadingCmDetail ? (
                              <LoadingSpinner message="Loading mappings…" />
                            ) : selectedCm ? (
                              <>
                                {selectedCm.description && (
                                  <p className="text-sm text-gray-600 mb-4">{selectedCm.description}</p>
                                )}
                                {selectedCm.group.map((grp, gi) => (
                                  <div key={gi} className="mb-6">
                                    <div className="flex items-center gap-2 mb-2 text-xs font-mono text-gray-500">
                                      <span className="truncate">{grp.source?.split('/').pop() ?? grp.source ?? '?'}</span>
                                      <span className="text-gray-300 mx-1">→</span>
                                      <span className="truncate">{grp.target?.split('/').pop() ?? grp.target ?? '?'}</span>
                                    </div>
                                    <div className="border border-gray-200 rounded-lg overflow-hidden">
                                      <table className="w-full text-xs">
                                        <thead className="bg-gray-50 border-b border-gray-200">
                                          <tr>
                                            <th className="text-left px-3 py-2 font-semibold text-gray-600">Source Code</th>
                                            <th className="text-left px-3 py-2 font-semibold text-gray-600">Source Display</th>
                                            <th className="text-left px-3 py-2 font-semibold text-gray-600">Target Code</th>
                                            <th className="text-left px-3 py-2 font-semibold text-gray-600">Target Display</th>
                                            <th className="text-left px-3 py-2 font-semibold text-gray-600">Equivalence</th>
                                          </tr>
                                        </thead>
                                        <tbody className="divide-y divide-gray-100">
                                          {grp.element.map((el, ei) => (
                                            el.target.map((tgt, ti) => (
                                              <tr key={`${ei}-${ti}`} className="hover:bg-amber-50">
                                                <td className="px-3 py-2 font-mono text-gray-700">{el.code}</td>
                                                <td className="px-3 py-2 text-gray-600">{el.display ?? ''}</td>
                                                <td className="px-3 py-2 font-mono text-gray-700">{tgt.code ?? ''}</td>
                                                <td className="px-3 py-2 text-gray-600">{tgt.display ?? ''}</td>
                                                <td className="px-3 py-2">
                                                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                                                    tgt.equivalence === 'equivalent' ? 'bg-green-100 text-green-700' :
                                                    tgt.equivalence === 'wider' || tgt.equivalence === 'narrower' ? 'bg-blue-100 text-blue-700' :
                                                    tgt.equivalence === 'unmatched' ? 'bg-red-100 text-red-600' :
                                                    'bg-gray-100 text-gray-600'
                                                  }`}>{tgt.equivalence}</span>
                                                  {tgt.comment && <span className="ml-2 text-gray-400 italic">{tgt.comment}</span>}
                                                </td>
                                              </tr>
                                            ))
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  </div>
                                ))}
                              </>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                );
              })() : (() => {
                // --- ValueSet table view with status filter + pagination ---
                // Filtering is handled server-side; resources is already filtered
                const vsTotalPages = Math.max(1, Math.ceil(resources.length / VS_PAGE_SIZE));
                const vsPageClamped = Math.min(vsPage, vsTotalPages - 1);
                const vsPaginated = resources.slice(vsPageClamped * VS_PAGE_SIZE, vsPageClamped * VS_PAGE_SIZE + VS_PAGE_SIZE);
                const vsPageWindow = Math.max(0, Math.min(vsTotalPages - 5, vsPageClamped - 2));

                return (
                  <>
                    {/* Filter bar */}
                    <div className="mb-4 flex flex-wrap items-center gap-3">
                      <Filter className="w-4 h-4 text-gray-400 flex-shrink-0" />

                      {/* Archived toggle */}
                      <button
                        onClick={() => { setVsArchivedView(!vsArchivedView); setVsPage(0); setSelectedResource(null); }}
                        className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border transition-colors ${
                          vsArchivedView
                            ? 'bg-amber-100 text-amber-700 border-amber-300'
                            : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                        }`}
                      >
                        <Archive className="w-3.5 h-3.5" />
                        {vsArchivedView ? 'Archived' : 'Active'}
                      </button>

                      {/* Filters — hidden when viewing archived (archived items have no useful status/view) */}
                      {!vsArchivedView && (
                        <>
                          <div className="flex items-center gap-1.5">
                            <label className="text-xs text-gray-500 font-medium whitespace-nowrap">Status</label>
                            <select
                              value={vsStatusFilter}
                              onChange={e => { setVsStatusFilter(e.target.value); setVsPage(0); }}
                              className="text-xs border border-gray-300 rounded-md px-2 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
                            >
                              <option value="">All statuses</option>
                              <option value="active">Active</option>
                              <option value="draft">Draft</option>
                              <option value="retired">Retired</option>
                              <option value="unknown">Unknown</option>
                            </select>
                          </div>

                          {diseaseViews.length > 0 && (
                            <div className="flex items-center gap-1.5">
                              <label className="text-xs text-gray-500 font-medium whitespace-nowrap">Condition</label>
                              <select
                                value={vsViewFilter}
                                onChange={e => { setVsViewFilter(e.target.value); setVsPage(0); }}
                                className="text-xs border border-gray-300 rounded-md px-2 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
                              >
                                <option value="">All conditions</option>
                                {diseaseViews.map(v => (
                                  <option key={v.id} value={v.code}>
                                    {v.display}{v.count > 0 ? ` (${v.count})` : ''}
                                  </option>
                                ))}
                              </select>
                            </div>
                          )}
                        </>
                      )}

                      {/* Source filter — always visible */}
                      <div className="flex items-center gap-1.5">
                        <label className="text-xs text-gray-500 font-medium whitespace-nowrap">Source</label>
                        <select
                          value={vsSourceFilter}
                          onChange={e => { setVsSourceFilter(e.target.value); setVsPage(0); }}
                          className="text-xs border border-gray-300 rounded-md px-2 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
                        >
                          <option value="">All sources</option>
                          <option value="phinvads">PHIN VADS</option>
                          <option value="vsac">VSAC</option>
                          <option value="hl7">HL7</option>
                          <option value="hl7v2">HL7 v2</option>
                          <option value="icd9cm">ICD-9-CM</option>
                          <option value="phts">PHTS (internal)</option>
                        </select>
                      </div>

                      {(vsStatusFilter || vsViewFilter || vsSourceFilter) && !vsArchivedView && (
                        <button
                          onClick={() => { setVsStatusFilter(''); setVsViewFilter(''); setVsSourceFilter(''); setVsPage(0); }}
                          className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 border border-gray-300 rounded-md px-2 py-1.5 hover:bg-gray-50 transition-colors"
                        >
                          <X className="w-3 h-3" /> Clear filters
                        </button>
                      )}

                      <p className="ml-auto text-sm text-gray-600">
                        {vsArchivedView
                          ? <><span className="font-semibold text-amber-700">{resources.length}</span><span className="text-gray-400"> archived value sets</span></>
                          : <><span className="font-semibold">{resources.length}</span><span className="text-gray-400"> value sets</span></>
                        }
                        {debouncedSearch && <span className="text-gray-400"> matching "{debouncedSearch}"</span>}
                        {vsViewFilter && (() => { const v = diseaseViews.find(dv => dv.code === vsViewFilter); return v ? <span className="text-blue-500"> · {v.display}</span> : null; })()}
                        {vsSourceFilter && <span className="text-gray-400"> · {SOURCE_LABELS[vsSourceFilter] ?? vsSourceFilter}</span>}
                      </p>
                    </div>

                    {resources.length === 0 ? (
                      <div className="text-center py-20 text-gray-400">
                        <Layers className="w-12 h-12 mx-auto mb-3 opacity-30" />
                        <p className="text-sm">
                          {vsArchivedView
                            ? 'No archived value sets found.'
                            : (debouncedSearch || vsStatusFilter || vsViewFilter || vsSourceFilter)
                              ? 'No value sets match the current filters.'
                              : 'No value sets found. Import data using the migration tool.'}
                        </p>
                      </div>
                    ) : (
                      <>
                        {/* Table */}
                        <div className="border border-gray-200 rounded-lg overflow-hidden">
                          <table className="w-full text-sm">
                            <thead className="bg-gray-50 border-b border-gray-200">
                              <tr>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Name / Title</th>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide hidden lg:table-cell">URL</th>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Status</th>
                                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Concepts</th>
                                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide hidden sm:table-cell">Version</th>
                                <th className="px-4 py-3 w-8" />
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {vsPaginated.map(vs => (
                                <tr
                                  key={vs.id}
                                  className="hover:bg-blue-50 cursor-pointer transition-colors group"
                                  onClick={() => setSelectedResource(vs)}
                                >
                                  <td className="px-4 py-3">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="font-medium text-gray-900 group-hover:text-blue-700 transition-colors line-clamp-1">
                                        {vs.title || vs.name}
                                      </span>
                                      <SourceBadge source={vs.source} />
                                    </div>
                                    {vs.definition && (
                                      <div className="text-xs text-gray-400 mt-0.5 line-clamp-1">{vs.definition}</div>
                                    )}
                                  </td>
                                  <td className="px-4 py-3 hidden lg:table-cell max-w-xs">
                                    <span className="text-xs font-mono text-gray-400 truncate block">{vs.url}</span>
                                  </td>
                                  <td className="px-4 py-3 whitespace-nowrap">
                                    <StatusBadge status={vs.status} />
                                  </td>
                                  <td className="px-4 py-3 text-right whitespace-nowrap">
                                    <span className="text-xs text-gray-500">{vs.conceptCount.toLocaleString()}</span>
                                  </td>
                                  <td className="px-4 py-3 hidden sm:table-cell whitespace-nowrap">
                                    {vs.version && <span className="text-xs text-blue-600 font-medium">v{vs.version}</span>}
                                  </td>
                                  <td className="px-4 py-3">
                                    {vsArchivedView ? (
                                      <button
                                        className="opacity-0 group-hover:opacity-100 transition-opacity text-amber-500 hover:text-amber-700 text-xs font-medium flex items-center gap-1 whitespace-nowrap"
                                        onClick={e => {
                                          e.stopPropagation();
                                          archiveResource(vs.id, true).then(() => loadResources()).catch(() => {});
                                        }}
                                        title="Restore"
                                      >
                                        <RefreshCw className="w-3.5 h-3.5" /> Restore
                                      </button>
                                    ) : (
                                      <button
                                        className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-blue-600"
                                        onClick={e => { e.stopPropagation(); handleDownloadJson(vs); }}
                                        title="Download JSON"
                                      >
                                        <Download className="w-4 h-4" />
                                      </button>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>

                        {/* Pagination */}
                        {vsTotalPages > 1 && (
                          <div className="mt-4 flex items-center justify-between gap-2 flex-wrap">
                            <p className="text-xs text-gray-500">
                              Page {vsPageClamped + 1} of {vsTotalPages} · {resources.length} results
                            </p>
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => setVsPage(p => Math.max(0, p - 1))}
                                disabled={vsPageClamped === 0}
                                className="p-1.5 border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                              >
                                <ChevronLeft className="w-4 h-4" />
                              </button>
                              {Array.from({ length: Math.min(5, vsTotalPages) }, (_, i) => {
                                const p = vsPageWindow + i;
                                return (
                                  <button
                                    key={p}
                                    onClick={() => setVsPage(p)}
                                    className={`px-3 py-1.5 text-xs border rounded-md transition-colors ${
                                      p === vsPageClamped
                                        ? 'bg-blue-600 text-white border-blue-600'
                                        : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                                    }`}
                                  >
                                    {p + 1}
                                  </button>
                                );
                              })}
                              <button
                                onClick={() => setVsPage(p => Math.min(vsTotalPages - 1, p + 1))}
                                disabled={vsPageClamped >= vsTotalPages - 1}
                                className="p-1.5 border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                              >
                                <ChevronRight className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </>
                );
              })()
            )}

            {/* Results — Concept/Code mode */}
            {searchMode === 'concept' && (
              <>
                {/* Server value set matches */}
                <div className="mb-6">
                  <div className="flex items-center gap-2 mb-3">
                    <h2 className="font-semibold text-gray-900">Server Value Sets</h2>
                    {loadingConcept && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
                    {!loadingConcept && debouncedSearch && (
                      <span className="text-sm text-gray-400">
                        {conceptEntries.length === 0 ? 'No matches' : `${conceptEntries.length} value set${conceptEntries.length !== 1 ? 's' : ''} contain this term`}
                      </span>
                    )}
                  </div>
                  {!debouncedSearch.trim() ? (
                    <div className="text-center py-12 text-gray-400">
                      <Search className="w-10 h-10 mx-auto mb-3 opacity-30" />
                      <p className="text-sm">Enter a concept or code to search across all value sets</p>
                    </div>
                  ) : loadingConcept ? null : conceptEntries.length === 0 ? (
                    <p className="text-sm text-gray-400 italic">No stored value sets contain "{debouncedSearch}"</p>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {conceptEntries.map(entry => (
                        <div
                          key={entry.valueset.id}
                          className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-all"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <Layers className="w-4 h-4 text-blue-600 flex-shrink-0" />
                              <StatusBadge status={entry.valueset.status} />
                            </div>
                            <button
                              onClick={() => setSelectedResource(entry.valueset)}
                              className="text-xs text-blue-600 hover:underline flex-shrink-0"
                            >
                              Details →
                            </button>
                          </div>
                          <h3 className="font-semibold text-gray-900 text-sm mb-1 line-clamp-1">
                            {entry.valueset.title || entry.valueset.name}
                          </h3>
                          <p className="text-xs text-gray-400 font-mono mb-3 truncate">{entry.valueset.url}</p>
                          <div className="space-y-1">
                            {entry.matchedConcepts.slice(0, 5).map(c => (
                              <div key={c.code} className="flex items-center gap-2 bg-blue-50 rounded px-2 py-1">
                                <span className="font-mono text-xs text-blue-700 font-medium flex-shrink-0">{c.code}</span>
                                <span className="text-xs text-gray-600 truncate">{c.display}</span>
                              </div>
                            ))}
                            {entry.totalMatched > 5 && (
                              <p className="text-xs text-gray-400 italic px-1">+{entry.totalMatched - 5} more matches</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* External vocabulary results */}
                {debouncedSearch.trim() && (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <h2 className="font-semibold text-gray-900">External Vocabulary</h2>
                      {loadingExternal && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
                    </div>
                    {!externalSearchEnabled ? (
                      <p className="text-sm text-gray-400 italic">External vocabulary search is disabled. Use the toggle above to enable it.</p>
                    ) : activeSdos.size === 0 ? (
                      <p className="text-sm text-gray-400 italic">No code systems selected. Use <Settings className="w-3 h-3 inline" /> to configure.</p>
                    ) : null}
                    <div className="space-y-2">
                      {sdoSystems.filter(sys => activeSdos.has(sys.id)).map(sys => {
                        const sysData = externalResults[sys.id];
                        const isExpanded = expandedExternal[sys.id] !== false;
                        const results = sysData?.results ?? [];
                        return (
                          <div key={sys.id} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                            <button
                              className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
                              onClick={() => setExpandedExternal(prev => ({ ...prev, [sys.id]: !isExpanded }))}
                            >
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-sm text-gray-900">{sys.name}</span>
                                {sysData && (
                                  <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                                    {results.length} result{results.length !== 1 ? 's' : ''}
                                  </span>
                                )}
                                {!sysData && loadingExternal && (
                                  <Loader2 className="w-3 h-3 animate-spin text-gray-400" />
                                )}
                              </div>
                              {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                            </button>
                            {isExpanded && sysData && (
                              results.length > 0 ? (
                                <div className="border-t border-gray-100">
                                  <table className="w-full text-sm">
                                    <tbody className="divide-y divide-gray-50">
                                      {results.map(r => (
                                        <tr key={r.code} className="hover:bg-gray-50">
                                          <td className="px-4 py-2 font-mono text-blue-700 text-xs w-40 flex-shrink-0 align-top">{r.code}</td>
                                          <td className="px-4 py-2 text-gray-700 align-top">
                                            <div>{r.display}</div>
                                            {r.description && r.description !== r.display && (
                                              <div className="text-xs text-gray-400 mt-0.5 line-clamp-2">{r.description}</div>
                                            )}
                                          </td>
                                          <td className="px-3 py-2 align-top w-8">
                                            {r.sourceUrl && (
                                              <a
                                                href={r.sourceUrl}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-gray-400 hover:text-blue-600"
                                                title={`View in ${r.systemName}`}
                                              >
                                                <ExternalLink className="w-3.5 h-3.5" />
                                              </a>
                                            )}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              ) : (
                                <p className="px-4 py-3 text-xs text-gray-400 border-t border-gray-100 italic">
                                  No results found in {sys.name}
                                </p>
                              )
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      {selectedResource && (
        <DetailPanel
          resource={selectedResource}
          fullPage={deepLinked}
          onClose={() => { setSelectedResource(null); setDeepLinked(false); }}
        />
      )}

      {editingResource && (
        editingResource.resourceType === 'CodeSystem' ? (
          <EditCodeSystemModal
            resource={editingResource}
            onClose={() => setEditingResource(null)}
            onSaved={() => { setEditingResource(null); setSelectedResource(null); loadResources(); }}
          />
        ) : (
          <EditValueSetModal
            resource={editingResource}
            onClose={() => setEditingResource(null)}
            onSaved={() => { setEditingResource(null); setSelectedResource(null); loadResources(); }}
          />
        )
      )}

      {deletingResource && (
        <DeleteConfirmDialog
          resource={deletingResource}
          onClose={() => setDeletingResource(null)}
          onDeleted={() => { setDeletingResource(null); setSelectedResource(null); loadResources(); }}
        />
      )}

      {archivingResource && (
        <ArchiveConfirmDialog
          resource={archivingResource}
          onClose={() => setArchivingResource(null)}
          onArchived={() => { setArchivingResource(null); setSelectedResource(null); loadResources(); loadStats(); }}
        />
      )}

      {auditResource && (
        <AuditLogModal
          resource={auditResource}
          entries={auditLog}
          loading={auditLoading}
          onClose={() => { setAuditResource(null); setAuditLog([]); }}
        />
      )}

      {/* External Code System Search Config Modal */}
      {showSearchConfig && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">External Code System Search</h2>
              <button onClick={() => setShowSearchConfig(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            {/* Master enable toggle */}
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-800">Enable external code search</p>
                <p className="text-xs text-gray-400 mt-0.5">Search SNOMED CT, LOINC, and other external vocabularies</p>
              </div>
              <button
                onClick={() => setExternalSearchEnabled(e => !e)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ${externalSearchEnabled ? 'bg-blue-600' : 'bg-gray-300'}`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${externalSearchEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
              </button>
            </div>
            {/* Per-system checkboxes */}
            <div className="p-3 border-b border-gray-100 flex items-center gap-2">
              <button
                onClick={() => setActiveSdos(new Set(sdoSystems.map(s => s.id)))}
                className="text-xs px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50"
              >
                Select all
              </button>
              <button
                onClick={() => setActiveSdos(new Set())}
                className="text-xs px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50"
              >
                Clear all
              </button>
              <span className="ml-auto text-xs text-gray-400">{activeSdos.size} of {sdoSystems.length} selected</span>
            </div>
            <div className="p-3 space-y-0.5">
              {sdoSystems.map(sys => (
                <label key={sys.id} className="flex items-center gap-3 px-2 py-2 rounded hover:bg-gray-50 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={activeSdos.has(sys.id)}
                    onChange={() => setActiveSdos(prev => {
                      const next = new Set(prev);
                      if (next.has(sys.id)) next.delete(sys.id);
                      else next.add(sys.id);
                      return next;
                    })}
                    className="rounded border-gray-300 text-blue-600 flex-shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-800">{sys.name}</p>
                  </div>
                </label>
              ))}
            </div>
            <div className="p-4 border-t border-gray-200">
              <button
                onClick={() => setShowSearchConfig(false)}
                className="w-full bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
              >
                Apply
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ModernPHINVADS;
