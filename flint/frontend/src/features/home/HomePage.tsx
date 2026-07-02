import { useState, useEffect } from 'react';
import { getHeaders } from '../../lib/api';
import { Link } from 'react-router-dom';
import {
  Users, Building2, Layers, MessageSquare, Server,
  CheckCircle, XCircle, Loader2, ExternalLink, Shield, Zap, ArrowRight,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Health { status: string }
interface AiInfo { provider: string; model: string; configured: boolean }
interface SmartConfig {
  auth_required: boolean;
  scopes_supported?: string[];
  grant_types_supported?: string[];
  capabilities?: string[];
  authorization_endpoint?: string;
}

// ---------------------------------------------------------------------------
// Section definitions
// ---------------------------------------------------------------------------

type Accent = 'blue' | 'purple' | 'amber' | 'green' | 'slate';

interface Section {
  to: string;
  label: string;
  icon: React.ElementType;
  accent: Accent;
  description: string;
  resources?: string[];
}

const SECTIONS: Section[] = [
  {
    to: '/clinical',
    label: 'Clinical',
    icon: Users,
    accent: 'blue',
    description: 'Patient records, observations, diagnoses, encounters, medications, and procedures',
    resources: ['Patient', 'Observation', 'Condition', 'Encounter', 'AllergyIntolerance', 'Immunization', 'MedicationRequest', 'Procedure', 'DiagnosticReport'],
  },
  {
    to: '/admin',
    label: 'Administrative',
    icon: Building2,
    accent: 'purple',
    description: 'Healthcare organizations, practitioners, roles, and physical locations',
    resources: ['Organization', 'Practitioner', 'PractitionerRole', 'Location'],
  },
  {
    to: '/terminology',
    label: 'Terminology',
    icon: Layers,
    accent: 'amber',
    description: 'ValueSets, CodeSystems, ConceptMaps, and FHIR operations ($expand, $lookup, $translate, $validate-code)',
    resources: ['ValueSet', 'CodeSystem', 'ConceptMap'],
  },
  {
    to: '/mcp-chat',
    label: 'MCP Chat',
    icon: MessageSquare,
    accent: 'green',
    description: 'AI-powered FHIR assistant with live tool-calling across all 16 resource types',
  },
  {
    to: '/system',
    label: 'System',
    icon: Server,
    accent: 'slate',
    description: 'Server health, Bulk Data Export, Bundle submission, and Capability Statement',
  },
];

// Full Tailwind class strings (dynamic construction defeats purge)
const ICON_TEXT: Record<Accent, string> = {
  blue: 'text-blue-600', purple: 'text-purple-600',
  amber: 'text-amber-600', green: 'text-green-600', slate: 'text-slate-600',
};
const ICON_BG: Record<Accent, string> = {
  blue: 'bg-blue-50', purple: 'bg-purple-50',
  amber: 'bg-amber-50', green: 'bg-green-50', slate: 'bg-slate-100',
};
const CARD_HOVER: Record<Accent, string> = {
  blue: 'hover:border-blue-300', purple: 'hover:border-purple-300',
  amber: 'hover:border-amber-300', green: 'hover:border-green-300', slate: 'hover:border-slate-400',
};
const PILL: Record<Accent, string> = {
  blue: 'bg-blue-50 text-blue-700', purple: 'bg-purple-50 text-purple-700',
  amber: 'bg-amber-50 text-amber-700', green: 'bg-green-50 text-green-700',
  slate: 'bg-slate-100 text-slate-600',
};

// ---------------------------------------------------------------------------
// Section card
// ---------------------------------------------------------------------------

function SectionCard({ section }: { section: Section }) {
  const { to, label, icon: Icon, accent, description, resources } = section;
  return (
    <Link
      to={to}
      className={`group bg-white border border-gray-200 rounded-lg shadow-sm p-5 flex flex-col gap-3 transition-all ${CARD_HOVER[accent]} hover:shadow-md`}
    >
      <div className="flex items-start justify-between">
        <div className={`w-9 h-9 rounded-lg ${ICON_BG[accent]} flex items-center justify-center flex-shrink-0`}>
          <Icon className={`w-5 h-5 ${ICON_TEXT[accent]}`} />
        </div>
        <ArrowRight className="w-4 h-4 text-gray-300 group-hover:text-gray-500 transition-colors mt-0.5" />
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-900">{label}</p>
        <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{description}</p>
      </div>
      {resources && (
        <div className="flex flex-wrap gap-1 mt-auto pt-1">
          {resources.slice(0, 5).map(r => (
            <span key={r} className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${PILL[accent]}`}>{r}</span>
          ))}
          {resources.length > 5 && (
            <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-gray-100 text-gray-500">
              +{resources.length - 5} more
            </span>
          )}
        </div>
      )}
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Info cards
// ---------------------------------------------------------------------------

function AiCard({ info }: { info: AiInfo | null }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
      <div className="flex items-center gap-2 mb-3">
        <Zap className="w-4 h-4 text-gray-400" />
        <p className="text-sm font-semibold text-gray-900">AI Provider</p>
      </div>
      {!info ? (
        <Loader2 className="w-4 h-4 text-gray-400 animate-spin" />
      ) : (
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-xs text-gray-500">Provider</span>
            <span className="text-xs font-medium text-gray-800 capitalize">{info.provider}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-gray-500">Model</span>
            <span className="text-xs font-mono text-gray-700">{info.model}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-gray-500">API key</span>
            {info.configured
              ? <span className="flex items-center gap-1 text-xs text-green-700"><CheckCircle className="w-3 h-3" />Configured</span>
              : <span className="flex items-center gap-1 text-xs text-red-600"><XCircle className="w-3 h-3" />Missing</span>
            }
          </div>
        </div>
      )}
    </div>
  );
}

function SmartCard({ config }: { config: SmartConfig | null | 'error' }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
      <div className="flex items-center gap-2 mb-3">
        <Shield className="w-4 h-4 text-gray-400" />
        <p className="text-sm font-semibold text-gray-900">SMART on FHIR</p>
      </div>
      {config === null && <Loader2 className="w-4 h-4 text-gray-400 animate-spin" />}
      {config === 'error' && (
        <p className="text-xs text-amber-600">Discovery endpoint unreachable</p>
      )}
      {config && config !== 'error' && (
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-xs text-gray-500">Auth</span>
            {config.auth_required
              ? <span className="flex items-center gap-1 text-xs text-green-700"><CheckCircle className="w-3 h-3" />Enabled</span>
              : <span className="text-xs font-medium text-amber-600">Disabled (dev)</span>
            }
          </div>
          {config.grant_types_supported && (
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500">Grant types</span>
              <span className="text-xs text-gray-700">{config.grant_types_supported.join(', ')}</span>
            </div>
          )}
          {config.scopes_supported && (
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500">Scopes</span>
              <span className="text-xs text-gray-500">{config.scopes_supported.length} supported</span>
            </div>
          )}
          <a href="/.well-known/smart-configuration" target="_blank" rel="noreferrer"
            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 transition-colors pt-0.5">
            <ExternalLink className="w-3 h-3" />Discovery document
          </a>
        </div>
      )}
    </div>
  );
}

function QuickLinksCard() {
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
      <div className="flex items-center gap-2 mb-3">
        <ExternalLink className="w-4 h-4 text-gray-400" />
        <p className="text-sm font-semibold text-gray-900">Quick Links</p>
      </div>
      <div className="space-y-1.5">
        {[
          { label: 'Interactive API Docs', href: '/docs' },
          { label: 'Capability Statement', href: '/metadata' },
          { label: 'SMART Discovery', href: '/.well-known/smart-configuration' },
          { label: 'Grafana Dashboards', href: 'http://localhost:3001' },
        ].map(({ label, href }) => (
          <a key={href} href={href} target="_blank" rel="noreferrer"
            className="flex items-center justify-between text-xs text-gray-600 hover:text-blue-600 transition-colors py-0.5">
            <span>{label}</span>
            <ExternalLink className="w-3 h-3 opacity-40 flex-shrink-0" />
          </a>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function HomePage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [aiInfo, setAiInfo] = useState<AiInfo | null>(null);
  const [smart, setSmart] = useState<SmartConfig | null | 'error'>(null);

  useEffect(() => {
    fetch('/ready')
      .then(r => r.json() as Promise<Health>)
      .then(setHealth)
      .catch(() => setHealth({ status: 'error' }));

    fetch('/ai/provider', { headers: getHeaders('/ai/provider') })
      .then(r => r.json() as Promise<AiInfo>)
      .then(setAiInfo)
      .catch(() => {});

    fetch('/.well-known/smart-configuration')
      .then(r => r.ok ? r.json() as Promise<SmartConfig> : Promise.reject())
      .then(setSmart)
      .catch(() => setSmart('error'));
  }, []);

  const statusStyle = !health
    ? 'bg-gray-100 text-gray-500'
    : health.status === 'ready'
    ? 'bg-green-100 text-green-700'
    : 'bg-red-100 text-red-700';

  return (
    <div className="bg-gray-50 min-h-full">
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Flint FHIR R4 Server</h2>
            <p className="text-xs text-gray-400 mt-0.5">General-purpose FHIR R4 · 16 resource types · SMART on FHIR</p>
          </div>
          <span className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${statusStyle}`}>
            {!health
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : health.status === 'ready'
              ? <CheckCircle className="w-3.5 h-3.5" />
              : <XCircle className="w-3.5 h-3.5" />
            }
            {health?.status ?? 'Checking…'}
          </span>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {SECTIONS.map(s => <SectionCard key={s.to} section={s} />)}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <AiCard info={aiInfo} />
          <SmartCard config={smart} />
          <QuickLinksCard />
        </div>
      </div>
    </div>
  );
}
