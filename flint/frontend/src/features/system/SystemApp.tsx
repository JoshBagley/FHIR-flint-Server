import { useState, useEffect } from 'react';
import {
  Server, CheckCircle, XCircle, Loader2, ChevronDown, ChevronUp,
  ExternalLink, Database, Search, Layers, Activity,
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
          <p className="text-xs text-gray-400 mt-0.5">Health · Capability Statement · API</p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <StatusCard ready={ready} loading={!ready} />
          <QuickLinks meta={meta} />
        </div>
        <CapabilityTable meta={meta} />
      </div>
    </div>
  );
}
