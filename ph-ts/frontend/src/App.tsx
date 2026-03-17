import { useState, useEffect, useCallback } from 'react';
import {
  Search, Download, FileCode, Layers, Grid, List,
  GitBranch, Users, TrendingUp, Activity, Clock, Database, AlertCircle, Loader2,
  ChevronDown, ChevronUp, Copy, Check, ExternalLink, ChevronLeft, Plus, Settings, X
} from 'lucide-react';
import ValueSetBuilder from './ValueSetBuilder';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FhirResource {
  id: string;
  resourceType: 'ValueSet' | 'CodeSystem';
  url?: string;
  name?: string;
  title?: string;
  description?: string;
  status: string;
  version?: string;
  compose?: { include: Array<{ concept?: Array<{ code: string; display?: string }> }> };
  concept?: Array<{ code: string; display?: string }>;
  identifier?: Array<{ system?: string; value?: string }>;
}

interface ApiStats {
  total_valuesets: number;
  total_codesystems: number;
  total_versions: number;
}

interface VersionEntry {
  version: number;
  timestamp: string;
  author?: string;
  summary?: string;
}

interface ExpansionConcept {
  system?: string;
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
  if (resource.resourceType === 'ValueSet') {
    return (resource.compose?.include ?? []).reduce(
      (sum, inc) => sum + (inc.concept?.length ?? 0), 0
    );
  }
  return resource.concept?.length ?? 0;
}

function toUiResource(r: FhirResource): UiResource {
  return {
    id: r.id,
    resourceType: r.resourceType,
    url: r.url ?? '',
    name: r.name ?? r.title ?? r.id,
    title: r.title ?? r.name ?? r.id,
    definition: r.description ? stripHtml(r.description) : '',
    status: r.status,
    version: r.version ?? '1',
    conceptCount: countConcepts(r),
    versionHistory: [],
  };
}

async function apiFetch<T>(path: string): Promise<T> {
  const resp = await fetch(path, { headers: { Accept: 'application/fhir+json' } });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText} — ${path}`);
  return resp.json() as Promise<T>;
}

async function fetchStats(): Promise<ApiStats> {
  return apiFetch<ApiStats>('/analytics/summary');
}

async function fetchResources(
  resourceType: 'ValueSet' | 'CodeSystem',
  search: string
): Promise<UiResource[]> {
  const params = new URLSearchParams();
  if (search.trim()) params.set('name', search.trim());
  const bundle = await apiFetch<{ entry?: Array<{ resource: FhirResource }> }>(
    `/${resourceType}?${params}`
  );
  return (bundle.entry ?? [])
    .map(e => e.resource)
    .filter(Boolean)
    .map(toUiResource);
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

  const hasSystem = concepts.some(c => c.system);
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
                      {hasSystem && <td className="px-4 py-3 text-gray-400 text-xs font-mono align-top truncate max-w-xs">{c.system}</td>}
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
// Main component
// ---------------------------------------------------------------------------

const ModernPHINVADS = () => {
  const [activeTab, setActiveTab] = useState<'ValueSet' | 'CodeSystem'>('ValueSet');
  const [activeView, setActiveView] = useState('browse');
  const [viewMode, setViewMode] = useState('grid');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedResource, setSelectedResource] = useState<UiResource | null>(null);
  const [expansionResource, setExpansionResource] = useState<UiResource | null>(null);
  const [builderOpen, setBuilderOpen] = useState(false);

  const [resources, setResources] = useState<UiResource[]>([]);
  const [stats, setStats] = useState<ApiStats>({ total_valuesets: 0, total_codesystems: 0, total_versions: 0 });
  const [loadingResources, setLoadingResources] = useState(true);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [errorResources, setErrorResources] = useState<string | null>(null);
  const [errorStats, setErrorStats] = useState<string | null>(null);

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

  // Load resources when tab or debounced search changes
  const loadResources = useCallback(async () => {
    setLoadingResources(true);
    setErrorResources(null);
    setSelectedResource(null);
    try {
      setResources(await fetchResources(activeTab, debouncedSearch));
    } catch (e) {
      setErrorResources((e as Error).message);
    } finally {
      setLoadingResources(false);
    }
  }, [activeTab, debouncedSearch]);

  useEffect(() => { loadResources(); }, [loadResources]);

  // Load available SDO systems once on mount; initialise all as active
  useEffect(() => {
    fetchSdoSystems().then(systems => {
      setSdoSystems(systems);
      setActiveSdos(new Set(systems.map(s => s.id)));
    }).catch(() => {});
  }, []);

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

  // Download a resource as JSON
  const handleDownloadJson = useCallback((resource: UiResource) => {
    const url = `/${resource.resourceType}/${resource.id}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = `${resource.resourceType}-${resource.id}.json`;
    a.click();
  }, []);

  // ResourceCard
  const ResourceCard = useCallback(({ resource }: { resource: UiResource }) => (
    <div
      className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-xl transition-all cursor-pointer hover:border-blue-400 group"
      onClick={() => setSelectedResource(resource)}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <Layers className="w-5 h-5 text-blue-600" />
          <StatusBadge status={resource.status} />
        </div>
        <button
          className="text-gray-400 hover:text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={e => { e.stopPropagation(); handleDownloadJson(resource); }}
          title="Download JSON"
        >
          <Download className="w-4 h-4" />
        </button>
      </div>
      <h3 className="font-semibold text-gray-900 mb-1 text-sm group-hover:text-blue-600 transition-colors line-clamp-1">
        {resource.title || resource.name}
      </h3>
      <p className="text-xs text-gray-500 mb-2 font-mono truncate">{resource.url || resource.id}</p>
      <p className="text-xs text-gray-600 mb-3 line-clamp-2">{resource.definition || 'No description available.'}</p>
      <div className="flex items-center justify-between text-xs text-gray-500 pt-3 border-t border-gray-100">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1"><FileCode className="w-3 h-3" />{resource.conceptCount} concepts</span>
        </div>
        <span className="text-blue-600 font-medium">v{resource.version}</span>
      </div>
    </div>
  ), [handleDownloadJson]);

  // Analytics dashboard
  const AnalyticsDashboard = () => (
    <div className="space-y-6">
      {errorStats && <ErrorBanner message={errorStats} onRetry={loadStats} />}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[
          { icon: Layers, value: loadingStats ? '…' : stats.total_valuesets.toLocaleString(), label: 'Value Sets', from: 'from-blue-500', to: 'to-blue-600', muted: 'text-blue-100' },
          { icon: Database, value: loadingStats ? '…' : stats.total_codesystems.toLocaleString(), label: 'Code Systems', from: 'from-purple-500', to: 'to-purple-600', muted: 'text-purple-100' },
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
          <a href="http://localhost:3001" target="_blank" rel="noreferrer" className="text-blue-500 hover:underline">
            localhost:3001
          </a>
        </p>
      </div>
    </div>
  );

  // Detail panel
  const DetailPanel = ({ resource }: { resource: UiResource }) => {
    return (
      <div className="fixed inset-y-0 right-0 w-[36rem] bg-white shadow-2xl border-l border-gray-200 z-50 overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 p-4 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Resource Details</h2>
          <button onClick={() => setSelectedResource(null)} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
        </div>
        <div className="p-6 space-y-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <StatusBadge status={resource.status} />
              <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">v{resource.version}</span>
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

          <div className="pt-4 border-t border-gray-200 space-y-2">
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
          </div>
        </div>
      </div>
    );
  };

  if (builderOpen) {
    return <ValueSetBuilder onBack={() => { setBuilderOpen(false); loadResources(); }} />;
  }

  if (expansionResource) {
    return <ExpansionPage resource={expansionResource} onBack={() => setExpansionResource(null)} />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-blue-600 via-blue-700 to-blue-800 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">PH-TS</h1>
              <p className="text-blue-100 text-sm mt-1">Public Health Terminology Service</p>
            </div>
            <div className="flex items-center gap-3">
              {!loadingStats && (
                <div className="hidden md:flex items-center gap-4 text-sm text-blue-100">
                  <span className="flex items-center gap-1"><Layers className="w-4 h-4" />{stats.total_valuesets} ValueSets</span>
                  <span className="flex items-center gap-1"><Database className="w-4 h-4" />{stats.total_codesystems} CodeSystems</span>
                </div>
              )}
              <button
                onClick={() => setBuilderOpen(true)}
                className="bg-green-500 hover:bg-green-400 px-4 py-2 rounded transition-colors text-sm font-medium flex items-center gap-2"
              >
                <Plus className="w-4 h-4" /> Create Value Set
              </button>
              <a href="/docs" target="_blank" rel="noreferrer"
                className="bg-white/10 hover:bg-white/20 px-4 py-2 rounded transition-colors text-sm font-medium">
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
                  {searchMode === 'name' && ([['ValueSet', 'Value Sets', 'bg-blue-600'], ['CodeSystem', 'Code Systems', 'bg-purple-600']] as const).map(([id, label, active]) => (
                    <button key={id} onClick={() => setActiveTab(id)}
                      className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                        activeTab === id ? `${active} text-white` : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}>{label}</button>
                  ))}
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
                <div className="flex items-center gap-2">
                  <button onClick={() => setViewMode('grid')}
                    className={`p-2 rounded ${viewMode === 'grid' ? 'bg-blue-100 text-blue-600' : 'text-gray-400 hover:bg-gray-100'}`}>
                    <Grid className="w-5 h-5" />
                  </button>
                  <button onClick={() => setViewMode('list')}
                    className={`p-2 rounded ${viewMode === 'list' ? 'bg-blue-100 text-blue-600' : 'text-gray-400 hover:bg-gray-100'}`}>
                    <List className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>

            {/* Results — Name mode */}
            {searchMode === 'name' && (
              errorResources ? (
                <ErrorBanner message={errorResources} onRetry={loadResources} />
              ) : loadingResources ? (
                <LoadingSpinner message={`Loading ${activeTab}s…`} />
              ) : (
                <>
                  <div className="mb-4 flex items-center justify-between">
                    <p className="text-sm text-gray-600">
                      Showing <span className="font-semibold">{resources.length}</span> {activeTab}s
                      {debouncedSearch && <span className="text-gray-400"> matching "{debouncedSearch}"</span>}
                    </p>
                  </div>
                  {resources.length === 0 ? (
                    <div className="text-center py-20 text-gray-400">
                      <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
                      <p className="text-sm">
                        {debouncedSearch
                          ? `No ${activeTab}s found matching "${debouncedSearch}"`
                          : `No ${activeTab}s found. Import data using the migration tool.`}
                      </p>
                    </div>
                  ) : (
                    <div className={viewMode === 'grid'
                      ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'
                      : 'flex flex-col gap-3'
                    }>
                      {resources.map((resource: UiResource) => (
                        <ResourceCard key={resource.id} resource={resource} />
                      ))}
                    </div>
                  )}
                </>
              )
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

      {selectedResource && <DetailPanel resource={selectedResource} />}

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
