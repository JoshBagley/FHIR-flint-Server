import { useState, useEffect, useRef } from 'react';
import {
  Server, CheckCircle, XCircle, Loader2, ChevronDown, ChevronUp,
  ExternalLink, Database, Search, Layers, Activity, Download, Package,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ServiceHealth { database: string; search: string; cache: string }
interface ReadyResponse { status: string; git_sha?: string; services: ServiceHealth }

interface SearchParam { name: string; type: string }
interface Interaction { code: string }
interface CapResource {
  type: string;
  interaction?: Interaction[];
  searchParam?: SearchParam[];
  supportedProfile?: string[];
  operation?: Array<{ name: string }>;
}
interface CapabilityStatement {
  fhirVersion?: string;
  software?: { name?: string; version?: string };
  date?: string;
  rest?: Array<{ resource?: CapResource[] }>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RESOURCE_CATEGORY: Record<string, string> = {
  Patient: 'Clinical', Observation: 'Clinical', Condition: 'Clinical',
  Encounter: 'Clinical', AllergyIntolerance: 'Clinical', Immunization: 'Clinical',
  Organization: 'Administrative', Practitioner: 'Administrative',
  PractitionerRole: 'Administrative', Location: 'Administrative',
  MedicationRequest: 'Medications', Procedure: 'Medications', DiagnosticReport: 'Medications',
  ValueSet: 'Terminology', CodeSystem: 'Terminology', ConceptMap: 'Terminology',
  StructureDefinition: 'Terminology', TerminologyCapabilities: 'Terminology',
};

const CATEGORY_COLOUR: Record<string, string> = {
  Clinical:       'bg-blue-50 text-blue-700',
  Administrative: 'bg-purple-50 text-purple-700',
  Medications:    'bg-green-50 text-green-700',
  Terminology:    'bg-amber-50 text-amber-700',
};

const PARAM_TYPE_COLOUR: Record<string, string> = {
  string: 'bg-sky-50 text-sky-700',
  token:  'bg-violet-50 text-violet-700',
  date:   'bg-teal-50 text-teal-700',
  reference: 'bg-rose-50 text-rose-700',
  number: 'bg-gray-100 text-gray-600',
};

function profileShortName(url: string): string {
  return url.split('/').pop() ?? url;
}

function serviceIcon(s: string) {
  if (s === 'healthy') return <CheckCircle className="w-4 h-4 text-green-500" />;
  if (s === 'loading') return <Loader2 className="w-4 h-4 text-gray-400 animate-spin" />;
  return <XCircle className="w-4 h-4 text-red-500" />;
}

// ---------------------------------------------------------------------------
// Status card
// ---------------------------------------------------------------------------

function StatusCard({ ready }: { ready: ReadyResponse | null; loading: boolean }) {
  const svc = ready?.services;
  const overall = ready?.status;

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Server className="w-5 h-5 text-gray-400" />
          <div>
            <p className="text-sm font-semibold text-gray-900">Server Health</p>
            <p className="text-xs text-gray-400">GET /ready</p>
          </div>
        </div>
        {!ready
          ? <Loader2 className="w-4 h-4 text-gray-400 animate-spin" />
          : overall === 'ready'
          ? <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">Ready</span>
          : <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">Degraded</span>
        }
      </div>
      <div className="grid grid-cols-3 gap-3 pt-1">
        {([
          ['Database', 'database', Database],
          ['Search',   'search',   Search],
          ['Cache',    'cache',    Layers],
        ] as const).map(([label, key, Icon]) => (
          <div key={key} className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2.5">
            <Icon className="w-4 h-4 text-gray-400 flex-shrink-0" />
            <div className="min-w-0">
              <p className="text-xs text-gray-500">{label}</p>
              <div className="flex items-center gap-1 mt-0.5">
                {svc ? serviceIcon(svc[key]) : <Loader2 className="w-3.5 h-3.5 text-gray-300 animate-spin" />}
                <span className="text-xs font-medium text-gray-700 capitalize">{svc?.[key] ?? '…'}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quick links
// ---------------------------------------------------------------------------

function QuickLinks({ meta }: { meta: CapabilityStatement | null }) {
  const version = meta?.fhirVersion ?? '—';
  const software = meta?.software?.name ?? 'Flint';
  const swVersion = meta?.software?.version;

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 space-y-4">
      <div className="flex items-center gap-2.5">
        <Activity className="w-5 h-5 text-gray-400" />
        <div>
          <p className="text-sm font-semibold text-gray-900">{software}</p>
          <p className="text-xs text-gray-400">
            FHIR R4 · {version}{swVersion && swVersion !== 'unknown' ? ` · v${swVersion}` : ''}
          </p>
        </div>
      </div>
      <div className="space-y-2">
        {[
          { label: 'Interactive API Docs',      href: '/docs',     desc: 'Swagger UI — try any endpoint' },
          { label: 'CapabilityStatement (JSON)', href: '/metadata', desc: 'Raw FHIR R4 /metadata resource' },
          { label: 'Grafana Dashboards',         href: 'http://localhost:3001', desc: 'Metrics · Logs · Traces' },
        ].map(({ label, href, desc }) => (
          <a key={href} href={href} target="_blank" rel="noreferrer"
            className="flex items-center justify-between p-3 rounded-lg border border-gray-100 hover:border-blue-200 hover:bg-blue-50 transition-colors group">
            <div>
              <p className="text-sm font-medium text-gray-800 group-hover:text-blue-700">{label}</p>
              <p className="text-xs text-gray-400">{desc}</p>
            </div>
            <ExternalLink className="w-4 h-4 text-gray-300 group-hover:text-blue-500 flex-shrink-0" />
          </a>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bulk Export Panel
// ---------------------------------------------------------------------------

const SYSTEM_TYPES = [
  'Patient', 'Observation', 'Condition', 'Encounter', 'AllergyIntolerance', 'Immunization',
  'MedicationRequest', 'Procedure', 'DiagnosticReport', 'Organization', 'Practitioner',
  'PractitionerRole', 'Location', 'ValueSet', 'CodeSystem', 'ConceptMap', 'StructureDefinition',
];
const PATIENT_TYPES = [
  'Patient', 'Observation', 'Condition', 'Encounter', 'AllergyIntolerance', 'Immunization',
  'MedicationRequest', 'Procedure', 'DiagnosticReport',
];

interface ExportJob {
  status: 'in-progress' | 'complete' | 'failed' | 'cancelled';
  createdAt: string;
  output: Array<{ type: string; url: string; count: number }>;
  error: unknown[];
}

function BulkExportPanel() {
  const [mode, setMode] = useState<'system' | 'patient'>('system');
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set());
  const [since, setSince] = useState('');
  const [kicking, setKicking] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [kickError, setKickError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!jobId || job?.status !== 'in-progress') {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`/jobs/${jobId}`);
        if (r.status === 202) return;
        if (r.status === 200) { setJob(await r.json()); }
        else { setJob(prev => prev ? { ...prev, status: 'failed' } : null); }
      } catch { /* retry on next tick */ }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [jobId, job?.status]);

  const allTypes = mode === 'system' ? SYSTEM_TYPES : PATIENT_TYPES;

  const toggleType = (t: string) => setTypeFilter(prev => {
    const next = new Set(prev);
    if (next.has(t)) next.delete(t); else next.add(t);
    return next;
  });

  const switchMode = (m: 'system' | 'patient') => {
    setMode(m); setTypeFilter(new Set()); setJob(null); setJobId(null); setKickError(null);
  };

  const startExport = async () => {
    setKicking(true); setKickError(null); setJob(null); setJobId(null);
    try {
      const p = new URLSearchParams();
      if (typeFilter.size > 0) p.set('_type', [...typeFilter].join(','));
      if (since) p.set('_since', since);
      const endpoint = mode === 'system' ? '/$export' : '/Patient/$export';
      const qs = p.toString();
      const r = await fetch(qs ? `${endpoint}?${qs}` : endpoint, { headers: { Prefer: 'respond-async' } });
      if (r.status !== 202) {
        setKickError(`HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
        return;
      }
      const loc = r.headers.get('Content-Location') ?? '';
      const id = loc.split('/').pop() ?? '';
      setJobId(id);
      setJob({ status: 'in-progress', createdAt: new Date().toISOString(), output: [], error: [] });
    } catch (e) {
      setKickError(String(e));
    } finally {
      setKicking(false);
    }
  };

  const cancelExport = async () => {
    if (!jobId) return;
    await fetch(`/jobs/${jobId}`, { method: 'DELETE' });
    setJob(prev => prev ? { ...prev, status: 'cancelled' } : null);
  };

  const STATUS_STYLE: Record<string, string> = {
    'in-progress': 'bg-yellow-100 text-yellow-700',
    'complete':    'bg-green-100 text-green-700',
    'failed':      'bg-red-100 text-red-700',
    'cancelled':   'bg-gray-100 text-gray-600',
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 space-y-4">
      <div className="flex items-center gap-2.5">
        <Download className="w-5 h-5 text-gray-400" />
        <div>
          <p className="text-sm font-semibold text-gray-900">Bulk Data Export</p>
          <p className="text-xs text-gray-400">FHIR Bulk Data IG v2 · NDJSON output · jobs expire after 24 h</p>
        </div>
      </div>

      {/* Mode toggle */}
      <div className="flex rounded-lg border border-gray-200 overflow-hidden w-fit text-xs">
        {([['system', 'System  /$export', 'All resource types'] as const,
           ['patient', 'Patient  /Patient/$export', 'Patient compartment only'] as const]).map(([m, label, sub]) => (
          <button key={m} onClick={() => switchMode(m)}
            className={`px-4 py-2.5 font-medium transition-colors text-left ${mode === m ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>
            <span className="font-mono">{label.split('  ')[1]}</span>
            <span className="block text-[10px] opacity-70 font-normal">{sub}</span>
          </button>
        ))}
      </div>

      {/* Type filter */}
      <div>
        <p className="text-xs font-medium text-gray-600 mb-2">
          Resource Types <span className="text-gray-400 font-normal">— leave blank to include all</span>
        </p>
        <div className="flex flex-wrap gap-1.5">
          {allTypes.map(t => (
            <button key={t} onClick={() => toggleType(t)}
              className={`px-2.5 py-0.5 rounded-full text-xs font-medium border transition-colors ${
                typeFilter.has(t)
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-blue-300 hover:text-blue-600'
              }`}>{t}</button>
          ))}
        </div>
      </div>

      {/* Since + actions */}
      <div className="flex items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Since <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <input type="date" value={since} onChange={e => setSince(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
        </div>
        <button onClick={startExport} disabled={kicking || job?.status === 'in-progress'}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
          {kicking ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
          Start Export
        </button>
        {job?.status === 'in-progress' && (
          <button onClick={cancelExport}
            className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-700 border border-red-200 rounded-lg text-sm font-medium hover:bg-red-100 transition-colors">
            <XCircle className="w-3.5 h-3.5" /> Cancel
          </button>
        )}
      </div>

      {kickError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{kickError}</div>
      )}

      {/* Job status */}
      {job && jobId && (
        <div className="border border-gray-100 rounded-lg p-4 bg-gray-50 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium text-gray-800 font-mono">Job {jobId.slice(0, 8)}…</p>
              <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[job.status] ?? 'bg-gray-100 text-gray-600'}`}>
                {job.status === 'in-progress' && <Loader2 className="w-3 h-3 animate-spin" />}
                {job.status}
              </span>
            </div>
            <p className="text-xs text-gray-400">{new Date(job.createdAt).toLocaleString()}</p>
          </div>

          {job.status === 'in-progress' && (
            <p className="text-xs text-gray-500">Exporting resources — polling every 3 s…</p>
          )}

          {job.status === 'complete' && job.output.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Output Files</p>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-200">
                    <th className="text-left pb-1.5 font-medium">Resource Type</th>
                    <th className="text-right pb-1.5 font-medium">Records</th>
                    <th className="text-right pb-1.5 font-medium">Download</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {job.output.map(f => (
                    <tr key={f.type}>
                      <td className="py-1.5 text-gray-700 font-medium">{f.type}</td>
                      <td className="py-1.5 text-right text-gray-500">{f.count.toLocaleString()}</td>
                      <td className="py-1.5 text-right">
                        <a href={f.url} download
                          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 transition-colors">
                          <Download className="w-3 h-3" /> .ndjson
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {job.status === 'complete' && job.output.length === 0 && (
            <p className="text-xs text-gray-400">No resources matched the export criteria.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bundle Submission Panel
// ---------------------------------------------------------------------------

const DEFAULT_BUNDLE = JSON.stringify({
  resourceType: 'Bundle',
  type: 'batch',
  entry: [],
}, null, 2);

interface BundleEntry { response?: { status?: string; location?: string } }
interface BundleResponse { entry?: BundleEntry[] }

function BundlePanel() {
  const [bundleJson, setBundleJson] = useState(DEFAULT_BUNDLE);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; data: unknown } | null>(null);

  let bundleType = '';
  try { bundleType = (JSON.parse(bundleJson) as { type?: string }).type ?? ''; } catch { /* invalid json */ }

  const submit = async () => {
    setSubmitting(true);
    setResult(null);
    try {
      let body: unknown;
      try { body = JSON.parse(bundleJson); }
      catch { setResult({ ok: false, data: { error: 'Invalid JSON — check the bundle syntax' } }); return; }
      const r = await fetch('/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/fhir+json', Accept: 'application/fhir+json' },
        body: JSON.stringify(body),
      });
      setResult({ ok: r.ok, data: await r.json() });
    } catch (e) {
      setResult({ ok: false, data: { error: String(e) } });
    } finally {
      setSubmitting(false);
    }
  };

  const entries = result?.ok ? (result.data as BundleResponse).entry ?? [] : [];

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 space-y-4">
      <div className="flex items-center gap-2.5">
        <Package className="w-5 h-5 text-gray-400" />
        <div>
          <p className="text-sm font-semibold text-gray-900">Bundle Submission</p>
          <p className="text-xs text-gray-400">POST / · batch (per-entry errors allowed) or transaction (atomic rollback)</p>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-medium text-gray-600">Bundle JSON</label>
          {bundleType && (
            <span className={`text-xs px-2 py-0.5 rounded-full font-mono font-medium ${
              bundleType === 'transaction' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'
            }`}>{bundleType}</span>
          )}
        </div>
        <textarea value={bundleJson} onChange={e => setBundleJson(e.target.value)} rows={10}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
      </div>

      <button onClick={submit} disabled={submitting}
        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
        {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Package className="w-3.5 h-3.5" />}
        Submit Bundle
      </button>

      {result && (
        <div className={`rounded-lg border p-4 space-y-3 ${result.ok ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
          <p className={`text-xs font-semibold ${result.ok ? 'text-green-700' : 'text-red-700'}`}>
            {result.ok
              ? `✓ ${entries.length} entr${entries.length !== 1 ? 'ies' : 'y'} processed`
              : '✗ Error'}
          </p>
          {result.ok && entries.length > 0 ? (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-green-200">
                  <th className="text-left pb-1.5 font-medium w-8">#</th>
                  <th className="text-left pb-1.5 font-medium w-32">Status</th>
                  <th className="text-left pb-1.5 font-medium">Location</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-green-100">
                {entries.map((e, i) => {
                  const status = e.response?.status ?? '—';
                  const isErr = status.startsWith('4') || status.startsWith('5');
                  return (
                    <tr key={i}>
                      <td className="py-1.5 text-gray-400">{i + 1}</td>
                      <td className={`py-1.5 font-medium ${isErr ? 'text-red-600' : 'text-green-700'}`}>{status}</td>
                      <td className="py-1.5 text-gray-500 font-mono text-xs truncate">{e.response?.location ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <pre className="text-xs overflow-auto max-h-48 whitespace-pre-wrap font-mono text-red-700">{JSON.stringify(result.data, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CapabilityStatement resource table
// ---------------------------------------------------------------------------

function ResourceRow({ res }: { res: CapResource }) {
  const [open, setOpen] = useState(false);
  const cat = RESOURCE_CATEGORY[res.type] ?? 'Other';
  const catColour = CATEGORY_COLOUR[cat] ?? 'bg-gray-100 text-gray-600';
  const interactions = (res.interaction ?? []).map(i => i.code).filter(c => !c.startsWith('history'));
  const searchParams = (res.searchParam ?? []).filter(p => !['_count', '_offset', '_sort', '_include', '_revinclude'].includes(p.name));
  const profiles = res.supportedProfile ?? [];

  return (
    <>
      <tr className="hover:bg-gray-50 transition-colors">
        <td className="px-4 py-3">
          <button onClick={() => setOpen(o => !o)}
            className="flex items-center gap-2 text-sm font-medium text-gray-900 hover:text-blue-700 transition-colors">
            {open ? <ChevronUp className="w-3.5 h-3.5 text-gray-400" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-400" />}
            {res.type}
          </button>
        </td>
        <td className="px-4 py-3">
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${catColour}`}>{cat}</span>
        </td>
        <td className="px-4 py-3 text-sm text-gray-500">{searchParams.length}</td>
        <td className="px-4 py-3">
          <div className="flex flex-wrap gap-1">
            {interactions.map(i => (
              <span key={i} className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 font-mono">{i}</span>
            ))}
          </div>
        </td>
        <td className="px-4 py-3 text-sm text-gray-500">{profiles.length > 0 ? profiles.length : '—'}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} className="px-4 pb-4 bg-gray-50">
            <div className="grid grid-cols-2 gap-4 pt-2">
              {/* Search params */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Search Parameters</p>
                {searchParams.length === 0
                  ? <p className="text-xs text-gray-400">None</p>
                  : <div className="flex flex-wrap gap-1.5">
                      {searchParams.map(p => (
                        <span key={p.name}
                          className={`px-2 py-0.5 rounded-full text-xs font-medium ${PARAM_TYPE_COLOUR[p.type] ?? 'bg-gray-100 text-gray-600'}`}>
                          {p.name} <span className="opacity-60">({p.type})</span>
                        </span>
                      ))}
                    </div>
                }
              </div>
              {/* Supported profiles */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">US Core Profiles</p>
                {profiles.length === 0
                  ? <p className="text-xs text-gray-400">None declared</p>
                  : <div className="space-y-1">
                      {profiles.map(p => (
                        <p key={p} className="text-xs text-blue-600 font-mono" title={p}>
                          {profileShortName(p)}
                        </p>
                      ))}
                    </div>
                }
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function CapabilityTable({ meta }: { meta: CapabilityStatement | null }) {
  const resources = meta?.rest?.[0]?.resource ?? [];

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <div>
          <p className="text-sm font-semibold text-gray-900">Capability Statement</p>
          <p className="text-xs text-gray-400 mt-0.5">{resources.length} resource types · click a row to expand</p>
        </div>
        <a href="/metadata" target="_blank" rel="noreferrer"
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-blue-600 transition-colors">
          <ExternalLink className="w-3.5 h-3.5" /> View raw
        </a>
      </div>
      {!meta
        ? <div className="flex justify-center py-12"><Loader2 className="w-5 h-5 text-gray-400 animate-spin" /></div>
        : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-3 text-left font-medium">Resource Type</th>
                <th className="px-4 py-3 text-left font-medium">Category</th>
                <th className="px-4 py-3 text-left font-medium">Search Params</th>
                <th className="px-4 py-3 text-left font-medium">Interactions</th>
                <th className="px-4 py-3 text-left font-medium">Profiles</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {resources.map(res => <ResourceRow key={res.type} res={res} />)}
            </tbody>
          </table>
        )
      }
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function SystemApp() {
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [meta, setMeta] = useState<CapabilityStatement | null>(null);

  useEffect(() => {
    fetch('/ready')
      .then(r => r.json() as Promise<ReadyResponse>)
      .then(setReady)
      .catch(() => setReady({ status: 'error', services: { database: 'unknown', search: 'unknown', cache: 'unknown' } }));

    fetch('/metadata', { headers: { Accept: 'application/fhir+json' } })
      .then(r => r.json() as Promise<CapabilityStatement>)
      .then(setMeta)
      .catch(() => {});
  }, []);

  return (
    <div className="bg-gray-50 min-h-full">
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <h2 className="text-lg font-semibold text-gray-900">System</h2>
          <p className="text-xs text-gray-400 mt-0.5">Health · Bulk Export · Bundle · Capability Statement · API</p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <StatusCard ready={ready} loading={!ready} />
          <QuickLinks meta={meta} />
        </div>
        <BulkExportPanel />
        <BundlePanel />
        <CapabilityTable meta={meta} />
      </div>
    </div>
  );
}
