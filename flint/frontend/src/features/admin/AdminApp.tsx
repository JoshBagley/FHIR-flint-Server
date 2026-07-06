import { useState, useEffect, useCallback } from 'react';
import {
  Building2, Search, ChevronLeft, ChevronRight, AlertCircle, X,
  Stethoscope, MapPin, Users, UserPlus, ToggleLeft, ToggleRight, ShieldCheck,
} from 'lucide-react';
import { useFhirSearch } from '../../hooks/useFhirSearch';
import { useDebounce } from '../../hooks/useDebounce';
import { apiFetch, apiFetchMut } from '../../lib/api';

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
// Users tab
// ---------------------------------------------------------------------------

interface KcUser {
  id: string;
  username?: string;
  email?: string;
  firstName?: string;
  lastName?: string;
  enabled?: boolean;
  createdTimestamp?: number;
  fhirUser?: string;
  roles?: string[];
}

interface ClinicianFormData {
  firstName: string; lastName: string; email: string; username: string; password: string;
  prefix: string; gender: string; organization_id: string; specialty: string;
}
interface PatientFormData {
  firstName: string; lastName: string; email: string; username: string;
  birthDate: string; gender: string; phone: string;
}

function ClinicianModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState<ClinicianFormData>({
    firstName: '', lastName: '', email: '', username: '', password: '',
    prefix: '', gender: '', organization_id: '', specialty: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof ClinicianFormData) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError(null);
    try {
      await apiFetchMut('POST', '/admin/users/clinician', {
        ...form,
        prefix: form.prefix || undefined,
        gender: form.gender || undefined,
        organization_id: form.organization_id || undefined,
        specialty: form.specialty || undefined,
      });
      onCreated();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <Stethoscope className="w-4 h-4 text-purple-500" /> New Clinician
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
        </div>
        <form onSubmit={submit} className="px-5 py-4 space-y-3">
          {error && <div className="flex items-start gap-2 text-red-600 text-sm bg-red-50 rounded-lg p-3"><AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />{error}</div>}
          <div className="grid grid-cols-2 gap-3">
            <Field label="First name *" value={form.firstName} onChange={set('firstName')} required />
            <Field label="Last name *" value={form.lastName} onChange={set('lastName')} required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Prefix" value={form.prefix} onChange={set('prefix')} placeholder="Dr." />
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Gender</label>
              <select value={form.gender} onChange={set('gender')} className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-purple-500">
                <option value="">Unknown</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>
          <Field label="Email *" type="email" value={form.email} onChange={set('email')} required />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Username *" value={form.username} onChange={set('username')} required />
            <Field label="Temporary password *" type="password" value={form.password} onChange={set('password')} required />
          </div>
          <Field label="Organization ID" value={form.organization_id} onChange={set('organization_id')} placeholder="FHIR Organization resource ID" />
          <Field label="Specialty" value={form.specialty} onChange={set('specialty')} placeholder="e.g. Family Medicine" />
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 disabled:opacity-50">
              {saving ? 'Creating…' : 'Create Clinician'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PatientPortalModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState<PatientFormData>({
    firstName: '', lastName: '', email: '', username: '',
    birthDate: '', gender: '', phone: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof PatientFormData) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError(null);
    try {
      await apiFetchMut('POST', '/admin/users/patient', {
        ...form,
        birthDate: form.birthDate || undefined,
        gender: form.gender || undefined,
        phone: form.phone || undefined,
      });
      onCreated();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-500" /> New Patient Portal Account
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
        </div>
        <form onSubmit={submit} className="px-5 py-4 space-y-3">
          {error && <div className="flex items-start gap-2 text-red-600 text-sm bg-red-50 rounded-lg p-3"><AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />{error}</div>}
          <div className="grid grid-cols-2 gap-3">
            <Field label="First name *" value={form.firstName} onChange={set('firstName')} required />
            <Field label="Last name *" value={form.lastName} onChange={set('lastName')} required />
          </div>
          <Field label="Email *" type="email" value={form.email} onChange={set('email')} required />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Username *" value={form.username} onChange={set('username')} required />
            <Field label="Date of birth" type="date" value={form.birthDate} onChange={set('birthDate')} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Gender</label>
              <select value={form.gender} onChange={set('gender')} className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500">
                <option value="">Unknown</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
            <Field label="Phone" type="tel" value={form.phone} onChange={set('phone')} placeholder="+1 555 000 0000" />
          </div>
          <p className="text-xs text-gray-400">A temporary password "ChangeMe123!" will be assigned — patient must change on first login.</p>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
              {saving ? 'Creating…' : 'Create Account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface AdminFormData {
  firstName: string; lastName: string; email: string; username: string; password: string;
}

function AdminModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState<AdminFormData>({
    firstName: '', lastName: '', email: '', username: '', password: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof AdminFormData) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError(null);
    try {
      await apiFetchMut('POST', '/admin/users/admin', form);
      onCreated();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-red-500" /> New Admin Account
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
        </div>
        <form onSubmit={submit} className="px-5 py-4 space-y-3">
          {error && <div className="flex items-start gap-2 text-red-600 text-sm bg-red-50 rounded-lg p-3"><AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />{error}</div>}
          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
            Admin accounts have full access to all resources and user management. Grant with care.
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="First name *" value={form.firstName} onChange={set('firstName')} required />
            <Field label="Last name *" value={form.lastName} onChange={set('lastName')} required />
          </div>
          <Field label="Email *" type="email" value={form.email} onChange={set('email')} required />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Username *" value={form.username} onChange={set('username')} required />
            <Field label="Temporary password *" type="password" value={form.password} onChange={set('password')} required />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50">
              {saving ? 'Creating…' : 'Create Admin'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label, value, onChange, required, type = 'text', placeholder,
}: {
  label: string; value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  required?: boolean; type?: string; placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      <input type={type} value={value} onChange={onChange} required={required} placeholder={placeholder}
        className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-purple-500 focus:border-purple-500" />
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState<KcUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 350);
  const [showAdmin, setShowAdmin] = useState(false);
  const [showClinician, setShowClinician] = useState(false);
  const [showPatient, setShowPatient] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const qs = debouncedSearch ? `?search=${encodeURIComponent(debouncedSearch)}` : '';
      const data = await apiFetch<{ users: KcUser[]; total: number }>(`/admin/users${qs}`);
      setUsers(data.users);
      setTotal(data.total);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch]);

  useEffect(() => { load(); }, [load]);

  const toggleEnabled = async (user: KcUser) => {
    setTogglingId(user.id);
    try {
      await apiFetchMut('PATCH', `/admin/users/${user.id}/status`, { enabled: !user.enabled });
      setUsers(prev => prev.map(u => u.id === user.id ? { ...u, enabled: !u.enabled } : u));
    } catch (err) {
      setError(String(err));
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <div>
      {showAdmin && <AdminModal onClose={() => setShowAdmin(false)} onCreated={() => { setShowAdmin(false); load(); }} />}
      {showClinician && <ClinicianModal onClose={() => setShowClinician(false)} onCreated={() => { setShowClinician(false); load(); }} />}
      {showPatient && <PatientPortalModal onClose={() => setShowPatient(false)} onCreated={() => { setShowPatient(false); load(); }} />}

      <div className="p-4 border-b border-gray-100 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by name or email…"
            className="w-full pl-9 pr-8 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500" />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <span className="text-xs text-gray-400 whitespace-nowrap">
          {loading ? '' : `${total.toLocaleString()} user${total !== 1 ? 's' : ''}`}
        </span>
        <div className="flex gap-2 ml-auto">
          <button onClick={() => setShowAdmin(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700">
            <ShieldCheck className="w-3.5 h-3.5" /> New Admin
          </button>
          <button onClick={() => setShowClinician(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700">
            <UserPlus className="w-3.5 h-3.5" /> New Clinician
          </button>
          <button onClick={() => setShowPatient(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700">
            <UserPlus className="w-3.5 h-3.5" /> New Patient Account
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 text-red-600 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Name</th>
          <th className="px-4 py-3 text-left font-medium">Username / Email</th>
          <th className="px-4 py-3 text-left font-medium">Roles</th>
          <th className="px-4 py-3 text-left font-medium">FHIR Resource</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={5} /> : error ? null
            : users.length === 0
            ? <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">No users found</td></tr>
            : users.map(user => (
              <tr key={user.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 font-medium text-gray-900">
                  {[user.firstName, user.lastName].filter(Boolean).join(' ') || '—'}
                </td>
                <td className="px-4 py-3">
                  <div className="text-gray-700 text-xs font-mono">{user.username}</div>
                  <div className="text-gray-400 text-xs">{user.email}</div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {(user.roles ?? []).map(r => (
                      <span key={r} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-purple-50 text-purple-700">
                        <ShieldCheck className="w-3 h-3" />{r.replace('fhir-', '')}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-gray-400 font-mono">{user.fhirUser ?? '—'}</td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => toggleEnabled(user)}
                    disabled={togglingId === user.id}
                    title={user.enabled ? 'Deactivate user' : 'Activate user'}
                    className="flex items-center gap-1.5 text-xs disabled:opacity-50">
                    {user.enabled
                      ? <><ToggleRight className="w-5 h-5 text-green-500" /><span className="text-green-600">Active</span></>
                      : <><ToggleLeft className="w-5 h-5 text-gray-400" /><span className="text-gray-400">Inactive</span></>
                    }
                  </button>
                </td>
              </tr>
            ))
          }
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

const TABS = [
  { id: 'users',               label: 'Users',              icon: UserPlus },
  { id: 'organizations',       label: 'Organizations',      icon: Building2 },
  { id: 'practitioners',       label: 'Practitioners',      icon: Stethoscope },
  { id: 'practitioner-roles',  label: 'Roles',              icon: Users },
  { id: 'locations',           label: 'Locations',          icon: MapPin },
] as const;

type AdminTab = typeof TABS[number]['id'];

export default function AdminApp() {
  const [activeTab, setActiveTab] = useState<AdminTab>('users');

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
          {activeTab === 'users'              && <UsersTab />}
          {activeTab === 'organizations'      && <OrganizationsTab />}
          {activeTab === 'practitioners'      && <PractitionersTab />}
          {activeTab === 'practitioner-roles' && <PractitionerRolesTab />}
          {activeTab === 'locations'          && <LocationsTab />}
        </div>
      </div>
    </div>
  );
}
