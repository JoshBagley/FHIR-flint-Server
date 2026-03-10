import { useState, useEffect, useCallback } from 'react';
import {
  Search, Download, FileCode, Layers, Grid, List,
  GitBranch, Users, TrendingUp, Activity, Clock, Database, AlertCircle, Loader2
} from 'lucide-react';

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
    definition: r.description ?? '',
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
// Main component
// ---------------------------------------------------------------------------

const ModernPHINVADS = () => {
  const [activeTab, setActiveTab] = useState<'ValueSet' | 'CodeSystem'>('ValueSet');
  const [activeView, setActiveView] = useState('browse');
  const [viewMode, setViewMode] = useState('grid');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedResource, setSelectedResource] = useState<UiResource | null>(null);

  const [resources, setResources] = useState<UiResource[]>([]);
  const [stats, setStats] = useState<ApiStats>({ total_valuesets: 0, total_codesystems: 0, total_versions: 0 });
  const [loadingResources, setLoadingResources] = useState(true);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [errorResources, setErrorResources] = useState<string | null>(null);
  const [errorStats, setErrorStats] = useState<string | null>(null);

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
  const DetailPanel = ({ resource }: { resource: UiResource }) => (
    <div className="fixed inset-y-0 right-0 w-[32rem] bg-white shadow-2xl border-l border-gray-200 z-50 overflow-y-auto">
      <div className="sticky top-0 bg-white border-b border-gray-200 p-4 flex items-center justify-between">
        <h2 className="font-semibold text-gray-900">Resource Details</h2>
        <button onClick={() => setSelectedResource(null)} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
      </div>
      <div className="p-6 space-y-6">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <StatusBadge status={resource.status} />
            <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">
              v{resource.version}
            </span>
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

        <div className="pt-4 border-t border-gray-200 space-y-2">
          <a
            href={`/${resource.resourceType}/${resource.id}/$expand`}
            target="_blank"
            rel="noreferrer"
            className="w-full bg-blue-600 text-white py-3 px-4 rounded-lg hover:bg-blue-700 transition-colors font-medium flex items-center justify-center gap-2"
          >
            <FileCode className="w-4 h-4" /> View Expansion ($expand)
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
              <div className="flex gap-4 mb-4">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
                  <input
                    type="text"
                    placeholder="Search by name…"
                    className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                  />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex gap-2">
                  {([['ValueSet', 'Value Sets', 'bg-blue-600'], ['CodeSystem', 'Code Systems', 'bg-purple-600']] as const).map(([id, label, active]) => (
                    <button key={id} onClick={() => setActiveTab(id)}
                      className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                        activeTab === id ? `${active} text-white` : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}>{label}</button>
                  ))}
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

            {/* Results */}
            {errorResources ? (
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
            )}
          </>
        )}
      </div>

      {selectedResource && <DetailPanel resource={selectedResource} />}
    </div>
  );
};

export default ModernPHINVADS;
