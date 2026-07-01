import { useState } from 'react';
import {
  Building2, Search, ChevronLeft, ChevronRight, AlertCircle, X,
  Stethoscope, MapPin, Users,
} from 'lucide-react';
import { useFhirSearch } from '../../hooks/useFhirSearch';
import { useDebounce } from '../../hooks/useDebounce';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Coding { code?: string; system?: string; display?: string }
interface CodeableConcept { text?: string; coding?: Coding[] }
interface Telecom { system?: string; value?: string; use?: string }
interface Address {
  line?: string[]; city?: string; state?: string; postalCode?: string; country?: string;
}

interface Organization {
  id: string;
  name?: string;
  active?: boolean;
  type?: CodeableConcept[];
  address?: Address[];
  telecom?: Telecom[];
  identifier?: Array<{ value?: string; system?: string }>;
}

interface Practitioner {
  id: string;
  name?: Array<{ given?: string[]; family?: string; prefix?: string[] }>;
  active?: boolean;
  gender?: string;
  address?: Address[];
  telecom?: Telecom[];
  identifier?: Array<{ value?: string; system?: string }>;
}

interface PractitionerRole {
  id: string;
  practitioner?: { display?: string };
  organization?: { display?: string };
  code?: CodeableConcept[];
  specialty?: CodeableConcept[];
  location?: Array<{ display?: string }>;
  telecom?: Telecom[];
}

interface Location {
  id: string;
  name?: string;
  status?: string;
  address?: Address;
  telecom?: Telecom[];
  managingOrganization?: { display?: string };
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function formatAddress(a?: Address | null): string {
  if (!a) return '—';
  return [a.city, a.state].filter(Boolean).join(', ') || '—';
}

function phone(telecom?: Telecom[]): string {
  return telecom?.find(t => t.system === 'phone')?.value ?? '—';
}

function npi(identifiers?: Array<{ value?: string; system?: string }>): string {
  return identifiers?.find(i => i.system === 'http://hl7.org/fhir/sid/us-npi')?.value ?? '—';
}

function practitionerName(p: Practitioner): string {
  const n = p.name?.[0];
  if (!n) return p.id;
  const prefix = n.prefix?.[0] ? `${n.prefix[0]} ` : '';
  const given = n.given?.join(' ') ?? '';
  return `${prefix}${given} ${n.family ?? ''}`.trim();
}

function capitalize(s?: string) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : '—';
}

// ---------------------------------------------------------------------------
// Shared sub-components (mirrors ClinicalApp pattern)
// ---------------------------------------------------------------------------

function StatusBadge({ value, green }: { value?: string; green?: string[] }) {
  const v = value ?? '';
  const colour = green?.includes(v) ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600';
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colour}`}>{v || '—'}</span>;
}

function LoadingRows({ cols }: { cols: number }) {
  return (
    <>
      {[0, 1, 2].map(i => (
        <tr key={i} className="animate-pulse">
          {Array.from({ length: cols }).map((_, j) => (
            <td key={j} className="px-4 py-3"><div className="h-3 bg-gray-100 rounded w-3/4" /></td>
          ))}
        </tr>
      ))}
    </>
  );
}

function Pagination({ page, totalPages, goToPage }: {
  page: number; totalPages: number; goToPage: (p: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-between border-t border-gray-100 pt-3 mt-3">
      <span className="text-xs text-gray-500">Page {page + 1} of {totalPages}</span>
      <div className="flex gap-1">
        <button disabled={page === 0} onClick={() => goToPage(page - 1)}
          className="p-1.5 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <button disabled={page >= totalPages - 1} onClick={() => goToPage(page + 1)}
          className="p-1.5 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

function SearchBar({
  value, onChange, placeholder, total, loading,
}: {
  value: string; onChange: (v: string) => void;
  placeholder: string; total: number; loading: boolean;
}) {
  return (
    <div className="p-4 border-b border-gray-100 flex items-center gap-3">
      <div className="relative flex-1 min-w-48">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input value={value} onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full pl-9 pr-8 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
        {value && (
          <button onClick={() => onChange('')}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <span className="text-xs text-gray-400 whitespace-nowrap">
        {loading ? '' : `${total.toLocaleString()} result${total !== 1 ? 's' : ''}`}
      </span>
    </div>
  );
}

function ErrorRow({ cols, msg }: { cols: number; msg: string }) {
  return (
    <tr><td colSpan={cols} className="px-4 py-4">
      <div className="flex items-center gap-2 text-red-600 text-sm">
        <AlertCircle className="w-4 h-4 flex-shrink-0" />{msg}
      </div>
    </td></tr>
  );
}

// ---------------------------------------------------------------------------
// Organizations tab
// ---------------------------------------------------------------------------

function OrganizationsTab() {
  const [search, setSearch] = useState('');
  const debounced = useDebounce(search, 350);
  const { data, total, loading, error, page, totalPages, goToPage } =
    useFhirSearch<Organization>('Organization', {
      params: { name: debounced || undefined, _sort: 'name' },
      pageSize: 20,
    });

  return (
    <div>
      <SearchBar value={search} onChange={v => { setSearch(v); goToPage(0); }}
        placeholder="Search by name…" total={total} loading={loading} />
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Name</th>
          <th className="px-4 py-3 text-left font-medium">Type</th>
          <th className="px-4 py-3 text-left font-medium">Location</th>
          <th className="px-4 py-3 text-left font-medium">Phone</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={5} /> : error
            ? <ErrorRow cols={5} msg={error} />
            : data.length === 0
            ? <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">No organizations found</td></tr>
            : data.map(org => (
              <tr key={org.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 font-medium text-gray-900">{org.name ?? '—'}</td>
                <td className="px-4 py-3 text-gray-500">{org.type?.[0]?.text ?? '—'}</td>
                <td className="px-4 py-3 text-gray-500">{formatAddress(org.address?.[0])}</td>
                <td className="px-4 py-3 text-gray-500 font-mono text-xs">{phone(org.telecom)}</td>
                <td className="px-4 py-3">
                  <StatusBadge value={org.active ? 'active' : 'inactive'} green={['active']} />
                </td>
              </tr>
            ))
          }
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Practitioners tab
// ---------------------------------------------------------------------------

function PractitionersTab() {
  const [search, setSearch] = useState('');
  const debounced = useDebounce(search, 350);
  const { data, total, loading, error, page, totalPages, goToPage } =
    useFhirSearch<Practitioner>('Practitioner', {
      params: { name: debounced || undefined, _sort: 'family' },
      pageSize: 20,
    });

  return (
    <div>
      <SearchBar value={search} onChange={v => { setSearch(v); goToPage(0); }}
        placeholder="Search by name…" total={total} loading={loading} />
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Name</th>
          <th className="px-4 py-3 text-left font-medium">NPI</th>
          <th className="px-4 py-3 text-left font-medium">Gender</th>
          <th className="px-4 py-3 text-left font-medium">Location</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={5} /> : error
            ? <ErrorRow cols={5} msg={error} />
            : data.length === 0
            ? <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">No practitioners found</td></tr>
            : data.map(prac => (
              <tr key={prac.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 font-medium text-gray-900">{practitionerName(prac)}</td>
                <td className="px-4 py-3 text-gray-400 font-mono text-xs">{npi(prac.identifier)}</td>
                <td className="px-4 py-3 text-gray-500">{capitalize(prac.gender)}</td>
                <td className="px-4 py-3 text-gray-500">{formatAddress(prac.address?.[0])}</td>
                <td className="px-4 py-3">
                  <StatusBadge value={prac.active ? 'active' : 'inactive'} green={['active']} />
                </td>
              </tr>
            ))
          }
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Practitioner Roles tab
// ---------------------------------------------------------------------------

function PractitionerRolesTab() {
  const { data, total, loading, error, page, totalPages, goToPage } =
    useFhirSearch<PractitionerRole>('PractitionerRole', { pageSize: 20 });

  return (
    <div>
      <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {loading ? '' : `${total.toLocaleString()} result${total !== 1 ? 's' : ''}`}
        </span>
      </div>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Practitioner</th>
          <th className="px-4 py-3 text-left font-medium">Role</th>
          <th className="px-4 py-3 text-left font-medium">Specialty</th>
          <th className="px-4 py-3 text-left font-medium">Organization</th>
          <th className="px-4 py-3 text-left font-medium">Location</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={5} /> : error
            ? <ErrorRow cols={5} msg={error} />
            : data.length === 0
            ? <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">No roles found</td></tr>
            : data.map(role => (
              <tr key={role.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 font-medium text-gray-900">{role.practitioner?.display ?? '—'}</td>
                <td className="px-4 py-3 text-gray-500">{role.code?.[0]?.text ?? '—'}</td>
                <td className="px-4 py-3 text-gray-500">{role.specialty?.[0]?.text ?? '—'}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{role.organization?.display ?? '—'}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{role.location?.[0]?.display ?? '—'}</td>
              </tr>
            ))
          }
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Locations tab
// ---------------------------------------------------------------------------

function LocationsTab() {
  const [search, setSearch] = useState('');
  const debounced = useDebounce(search, 350);
  const { data, total, loading, error, page, totalPages, goToPage } =
    useFhirSearch<Location>('Location', {
      params: { name: debounced || undefined, _sort: 'name' },
      pageSize: 20,
    });

  return (
    <div>
      <SearchBar value={search} onChange={v => { setSearch(v); goToPage(0); }}
        placeholder="Search by name…" total={total} loading={loading} />
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Name</th>
          <th className="px-4 py-3 text-left font-medium">Address</th>
          <th className="px-4 py-3 text-left font-medium">Phone</th>
          <th className="px-4 py-3 text-left font-medium">Organization</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={5} /> : error
            ? <ErrorRow cols={5} msg={error} />
            : data.length === 0
            ? <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">No locations found</td></tr>
            : data.map(loc => (
              <tr key={loc.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 font-medium text-gray-900">{loc.name ?? '—'}</td>
                <td className="px-4 py-3 text-gray-500">{formatAddress(loc.address)}</td>
                <td className="px-4 py-3 text-gray-500 font-mono text-xs">{phone(loc.telecom)}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{loc.managingOrganization?.display ?? '—'}</td>
                <td className="px-4 py-3">
                  <StatusBadge value={loc.status} green={['active']} />
                </td>
              </tr>
            ))
          }
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

const TABS = [
  { id: 'organizations',       label: 'Organizations',      icon: Building2 },
  { id: 'practitioners',       label: 'Practitioners',      icon: Stethoscope },
  { id: 'practitioner-roles',  label: 'Roles',              icon: Users },
  { id: 'locations',           label: 'Locations',          icon: MapPin },
] as const;

type AdminTab = typeof TABS[number]['id'];

export default function AdminApp() {
  const [activeTab, setActiveTab] = useState<AdminTab>('organizations');

  return (
    <div className="bg-gray-50 min-h-full">
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <Building2 className="w-5 h-5 text-purple-500" />
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Administrative Resources</h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Organization · Practitioner · PractitionerRole · Location
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
          <div className="border-b border-gray-100 flex gap-1 px-4">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => setActiveTab(id)}
                className={`flex items-center gap-2 px-3 py-3.5 border-b-2 whitespace-nowrap transition-colors text-sm font-medium ${
                  activeTab === id
                    ? 'border-purple-600 text-purple-600'
                    : 'border-transparent text-gray-500 hover:text-gray-900'
                }`}>
                <Icon className="w-4 h-4" /> {label}
              </button>
            ))}
          </div>
          {activeTab === 'organizations'      && <OrganizationsTab />}
          {activeTab === 'practitioners'      && <PractitionersTab />}
          {activeTab === 'practitioner-roles' && <PractitionerRolesTab />}
          {activeTab === 'locations'          && <LocationsTab />}
        </div>
      </div>
    </div>
  );
}
