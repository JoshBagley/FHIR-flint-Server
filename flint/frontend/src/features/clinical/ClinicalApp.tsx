import { useState } from 'react';
import {
  Users, ArrowLeft, Search, ChevronLeft, ChevronRight, ChevronDown, ChevronUp,
  Activity, FileText, Calendar, ShieldAlert, Syringe, AlertCircle, X,
  Pill, Scissors, ClipboardList, Download, CheckCircle,
} from 'lucide-react';
import { useFhirSearch } from '../../hooks/useFhirSearch';
import { useDebounce } from '../../hooks/useDebounce';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HumanName { use?: string; given?: string[]; family?: string }
interface Coding { code?: string; system?: string; display?: string }
interface CodeableConcept { text?: string; coding?: Coding[] }
interface Identifier { type?: CodeableConcept; value?: string; system?: string }

interface Patient {
  id: string;
  resourceType: 'Patient';
  name?: HumanName[];
  birthDate?: string;
  gender?: string;
  address?: Array<{ city?: string; state?: string }>;
  telecom?: Array<{ system?: string; value?: string }>;
  identifier?: Identifier[];
}

interface Observation {
  id: string;
  code?: CodeableConcept;
  effectiveDateTime?: string;
  status?: string;
  valueQuantity?: { value?: number; unit?: string };
  valueCodeableConcept?: CodeableConcept;
  valueString?: string;
  category?: Array<{ coding?: Coding[] }>;
}

interface Condition {
  id: string;
  code?: CodeableConcept;
  onsetDateTime?: string;
  recordedDate?: string;
  clinicalStatus?: CodeableConcept;
  category?: Array<{ coding?: Coding[] }>;
}

interface Encounter {
  id: string;
  type?: CodeableConcept[];
  period?: { start?: string; end?: string };
  status?: string;
  class?: Coding;
}

interface AllergyIntolerance {
  id: string;
  code?: CodeableConcept;
  clinicalStatus?: CodeableConcept;
  criticality?: string;
  recordedDate?: string;
}

interface Immunization {
  id: string;
  vaccineCode?: CodeableConcept;
  status?: string;
  occurrenceDateTime?: string;
}

interface MedicationRequest {
  id: string;
  medicationCodeableConcept?: CodeableConcept;
  authoredOn?: string;
  status?: string;
  requester?: { display?: string };
  dosageInstruction?: Array<{ text?: string }>;
}

interface Procedure {
  id: string;
  code?: CodeableConcept;
  performedPeriod?: { start?: string; end?: string };
  performedDateTime?: string;
  status?: string;
}

interface DiagnosticReport {
  id: string;
  code?: CodeableConcept;
  effectiveDateTime?: string;
  status?: string;
  category?: Array<{ coding?: Coding[] }>;
  presentedForm?: Array<{ data?: string; contentType?: string }>;
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function patientDisplayName(p: Patient): string {
  const n = p.name?.[0];
  if (!n) return p.id;
  const given = n.given?.join(' ') ?? '';
  return `${given} ${n.family ?? ''}`.trim();
}

function formatDate(iso?: string): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }); }
  catch { return iso; }
}

function patientAge(birthDate?: string): string {
  if (!birthDate) return '—';
  const years = Math.floor((Date.now() - new Date(birthDate).getTime()) / (365.25 * 24 * 3600 * 1000));
  return `${years} yrs`;
}

function mrnOf(p: Patient): string {
  return p.identifier?.find(i => i.type?.text === 'Medical Record Number')?.value?.slice(0, 8) ?? '—';
}

function obsValue(obs: Observation): string {
  if (obs.valueQuantity?.value !== undefined) {
    return `${obs.valueQuantity.value} ${obs.valueQuantity.unit ?? ''}`.trim();
  }
  if (obs.valueCodeableConcept?.text) return obs.valueCodeableConcept.text;
  if (obs.valueString) return obs.valueString;
  return '—';
}

function capitalize(s?: string): string {
  if (!s) return '—';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ value, green, yellow }: { value?: string; green?: string[]; yellow?: string[] }) {
  const v = value ?? '';
  const colour = green?.includes(v)
    ? 'bg-green-100 text-green-700'
    : yellow?.includes(v)
    ? 'bg-yellow-100 text-yellow-700'
    : 'bg-gray-100 text-gray-600';
  return <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${colour}`}>{v || '—'}</span>;
}

function Pagination({ page, totalPages, goToPage }: { page: number; totalPages: number; goToPage: (p: number) => void }) {
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

function EmptyState({ message }: { message: string }) {
  return <p className="text-sm text-gray-400 py-8 text-center">{message}</p>;
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

// ---------------------------------------------------------------------------
// Patient list
// ---------------------------------------------------------------------------

function PatientList({ onSelect }: { onSelect: (p: Patient) => void }) {
  const [nameSearch, setNameSearch] = useState('');
  const [genderFilter, setGenderFilter] = useState('');
  const debouncedName = useDebounce(nameSearch, 350);

  const { data, total, loading, error, page, totalPages, goToPage } = useFhirSearch<Patient>('Patient', {
    params: {
      name: debouncedName || undefined,
      gender: genderFilter || undefined,
      _sort: 'family',
    },
    pageSize: 20,
  });

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
      {/* Toolbar */}
      <div className="p-4 border-b border-gray-100 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={nameSearch}
            onChange={e => { setNameSearch(e.target.value); goToPage(0); }}
            placeholder="Search by name…"
            className="w-full pl-9 pr-8 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          {nameSearch && (
            <button onClick={() => setNameSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <select value={genderFilter} onChange={e => { setGenderFilter(e.target.value); goToPage(0); }}
          className="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500">
          <option value="">All genders</option>
          <option value="male">Male</option>
          <option value="female">Female</option>
          <option value="other">Other</option>
          <option value="unknown">Unknown</option>
        </select>
        <span className="text-xs text-gray-400 ml-auto">{loading ? '' : `${total} patient${total !== 1 ? 's' : ''}`}</span>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 text-red-600 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
            <th className="px-4 py-3 text-left font-medium">Name</th>
            <th className="px-4 py-3 text-left font-medium">DOB / Age</th>
            <th className="px-4 py-3 text-left font-medium">Gender</th>
            <th className="px-4 py-3 text-left font-medium">MRN</th>
            <th className="px-4 py-3 text-left font-medium">Location</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={5} /> : data.map(p => (
            <tr key={p.id} onClick={() => onSelect(p)}
              className="hover:bg-blue-50 cursor-pointer transition-colors">
              <td className="px-4 py-3 font-medium text-blue-700">{patientDisplayName(p)}</td>
              <td className="px-4 py-3 text-gray-600">{formatDate(p.birthDate)} <span className="text-gray-400">· {patientAge(p.birthDate)}</span></td>
              <td className="px-4 py-3 text-gray-600">{capitalize(p.gender)}</td>
              <td className="px-4 py-3 text-gray-400 font-mono text-xs">{mrnOf(p)}</td>
              <td className="px-4 py-3 text-gray-600">{[p.address?.[0]?.city, p.address?.[0]?.state].filter(Boolean).join(', ') || '—'}</td>
            </tr>
          ))}
          {!loading && data.length === 0 && (
            <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">No patients found</td></tr>
          )}
        </tbody>
      </table>

      <div className="px-4 py-3">
        <Pagination page={page} totalPages={totalPages} goToPage={goToPage} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Clinical resource tabs
// ---------------------------------------------------------------------------

function ObservationsTab({ patientId }: { patientId: string }) {
  const { data, loading, page, totalPages, goToPage } = useFhirSearch<Observation>('Observation', {
    params: { patient: `Patient/${patientId}`, _sort: '-date' },
    pageSize: 20,
  });
  return (
    <div>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Observation</th>
          <th className="px-4 py-3 text-left font-medium">Value</th>
          <th className="px-4 py-3 text-left font-medium">Date</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={4} /> : data.map(obs => (
            <tr key={obs.id}>
              <td className="px-4 py-3 text-gray-900">{obs.code?.text ?? '—'}</td>
              <td className="px-4 py-3 text-gray-600">{obsValue(obs)}</td>
              <td className="px-4 py-3 text-gray-500 text-xs">{formatDate(obs.effectiveDateTime)}</td>
              <td className="px-4 py-3"><StatusBadge value={obs.status} green={['final', 'amended']} /></td>
            </tr>
          ))}
          {!loading && data.length === 0 && <tr><td colSpan={4}><EmptyState message="No observations" /></td></tr>}
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

function ConditionsTab({ patientId }: { patientId: string }) {
  const { data, loading, page, totalPages, goToPage } = useFhirSearch<Condition>('Condition', {
    params: { patient: `Patient/${patientId}` },
    pageSize: 20,
  });
  return (
    <div>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Condition</th>
          <th className="px-4 py-3 text-left font-medium">Onset</th>
          <th className="px-4 py-3 text-left font-medium">Recorded</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={4} /> : data.map(c => (
            <tr key={c.id}>
              <td className="px-4 py-3 text-gray-900">{c.code?.text ?? '—'}</td>
              <td className="px-4 py-3 text-gray-500 text-xs">{formatDate(c.onsetDateTime)}</td>
              <td className="px-4 py-3 text-gray-500 text-xs">{formatDate(c.recordedDate)}</td>
              <td className="px-4 py-3"><StatusBadge value={c.clinicalStatus?.coding?.[0]?.code} green={['resolved', 'inactive']} yellow={['active']} /></td>
            </tr>
          ))}
          {!loading && data.length === 0 && <tr><td colSpan={4}><EmptyState message="No conditions" /></td></tr>}
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

function EncountersTab({ patientId }: { patientId: string }) {
  const { data, loading, page, totalPages, goToPage } = useFhirSearch<Encounter>('Encounter', {
    params: { patient: `Patient/${patientId}`, _sort: '-date' },
    pageSize: 20,
  });
  return (
    <div>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Type</th>
          <th className="px-4 py-3 text-left font-medium">Class</th>
          <th className="px-4 py-3 text-left font-medium">Start</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={4} /> : data.map(enc => (
            <tr key={enc.id}>
              <td className="px-4 py-3 text-gray-900">{enc.type?.[0]?.text ?? '—'}</td>
              <td className="px-4 py-3 text-gray-500 text-xs uppercase">{enc.class?.code ?? '—'}</td>
              <td className="px-4 py-3 text-gray-500 text-xs">{formatDate(enc.period?.start)}</td>
              <td className="px-4 py-3"><StatusBadge value={enc.status} green={['finished']} yellow={['in-progress']} /></td>
            </tr>
          ))}
          {!loading && data.length === 0 && <tr><td colSpan={4}><EmptyState message="No encounters" /></td></tr>}
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

function AllergiesTab({ patientId }: { patientId: string }) {
  const { data, loading, page, totalPages, goToPage } = useFhirSearch<AllergyIntolerance>('AllergyIntolerance', {
    params: { patient: `Patient/${patientId}` },
    pageSize: 20,
  });
  return (
    <div>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Substance</th>
          <th className="px-4 py-3 text-left font-medium">Criticality</th>
          <th className="px-4 py-3 text-left font-medium">Recorded</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={4} /> : data.map(a => (
            <tr key={a.id}>
              <td className="px-4 py-3 text-gray-900">{a.code?.text ?? '—'}</td>
              <td className="px-4 py-3"><StatusBadge value={a.criticality} yellow={['high']} /></td>
              <td className="px-4 py-3 text-gray-500 text-xs">{formatDate(a.recordedDate)}</td>
              <td className="px-4 py-3"><StatusBadge value={a.clinicalStatus?.coding?.[0]?.code} green={['resolved', 'inactive']} yellow={['active']} /></td>
            </tr>
          ))}
          {!loading && data.length === 0 && <tr><td colSpan={4}><EmptyState message="No allergies recorded" /></td></tr>}
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

function ImmunizationsTab({ patientId }: { patientId: string }) {
  const { data, loading, page, totalPages, goToPage } = useFhirSearch<Immunization>('Immunization', {
    params: { patient: `Patient/${patientId}`, _sort: '-date' },
    pageSize: 20,
  });
  return (
    <div>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Vaccine</th>
          <th className="px-4 py-3 text-left font-medium">Date</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={3} /> : data.map(imm => (
            <tr key={imm.id}>
              <td className="px-4 py-3 text-gray-900">{imm.vaccineCode?.text ?? '—'}</td>
              <td className="px-4 py-3 text-gray-500 text-xs">{formatDate(imm.occurrenceDateTime)}</td>
              <td className="px-4 py-3"><StatusBadge value={imm.status} green={['completed']} yellow={['not-done']} /></td>
            </tr>
          ))}
          {!loading && data.length === 0 && <tr><td colSpan={3}><EmptyState message="No immunizations recorded" /></td></tr>}
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

function MedicationsTab({ patientId }: { patientId: string }) {
  const { data, loading, page, totalPages, goToPage } = useFhirSearch<MedicationRequest>('MedicationRequest', {
    params: { patient: `Patient/${patientId}`, _sort: '-authoredon' },
    pageSize: 20,
  });
  return (
    <div>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Medication</th>
          <th className="px-4 py-3 text-left font-medium">Dosage</th>
          <th className="px-4 py-3 text-left font-medium">Prescribed</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={4} /> : data.map(med => (
            <tr key={med.id}>
              <td className="px-4 py-3 text-gray-900">{med.medicationCodeableConcept?.text ?? '—'}</td>
              <td className="px-4 py-3 text-gray-500 text-xs">{med.dosageInstruction?.[0]?.text ?? '—'}</td>
              <td className="px-4 py-3 text-gray-500 text-xs">{formatDate(med.authoredOn)}</td>
              <td className="px-4 py-3">
                <StatusBadge value={med.status} green={['active', 'completed']} yellow={['on-hold', 'draft']} />
              </td>
            </tr>
          ))}
          {!loading && data.length === 0 && <tr><td colSpan={4}><EmptyState message="No medications recorded" /></td></tr>}
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

function ProceduresTab({ patientId }: { patientId: string }) {
  const { data, loading, page, totalPages, goToPage } = useFhirSearch<Procedure>('Procedure', {
    params: { patient: `Patient/${patientId}`, _sort: '-date' },
    pageSize: 20,
  });
  return (
    <div>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Procedure</th>
          <th className="px-4 py-3 text-left font-medium">Performed</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={3} /> : data.map(proc => (
            <tr key={proc.id}>
              <td className="px-4 py-3 text-gray-900">{proc.code?.text ?? '—'}</td>
              <td className="px-4 py-3 text-gray-500 text-xs">
                {formatDate(proc.performedPeriod?.start ?? proc.performedDateTime)}
              </td>
              <td className="px-4 py-3">
                <StatusBadge value={proc.status} green={['completed']} yellow={['in-progress']} />
              </td>
            </tr>
          ))}
          {!loading && data.length === 0 && <tr><td colSpan={3}><EmptyState message="No procedures recorded" /></td></tr>}
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

function DiagnosticReportsTab({ patientId }: { patientId: string }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data, loading, page, totalPages, goToPage } = useFhirSearch<DiagnosticReport>('DiagnosticReport', {
    params: { patient: `Patient/${patientId}`, _sort: '-date' },
    pageSize: 20,
  });

  function decodeNote(b64?: string): string {
    if (!b64) return '';
    try { return atob(b64); } catch { return '(unable to decode)'; }
  }

  return (
    <div>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
          <th className="px-4 py-3 text-left font-medium">Report</th>
          <th className="px-4 py-3 text-left font-medium">Date</th>
          <th className="px-4 py-3 text-left font-medium">Status</th>
          <th className="px-4 py-3 text-left font-medium">Note</th>
        </tr></thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? <LoadingRows cols={4} /> : data.map(dr => {
            const title = dr.code?.coding?.[0]?.display ?? dr.code?.text ?? '—';
            const noteData = dr.presentedForm?.[0]?.data;
            const isOpen = expanded === dr.id;
            return (
              <>
                <tr key={dr.id}>
                  <td className="px-4 py-3 text-gray-900">{title}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{formatDate(dr.effectiveDateTime)}</td>
                  <td className="px-4 py-3"><StatusBadge value={dr.status} green={['final', 'amended']} /></td>
                  <td className="px-4 py-3">
                    {noteData && (
                      <button
                        onClick={() => setExpanded(isOpen ? null : dr.id)}
                        className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 transition-colors"
                      >
                        {isOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        {isOpen ? 'Hide' : 'View'}
                      </button>
                    )}
                  </td>
                </tr>
                {isOpen && noteData && (
                  <tr key={`${dr.id}-note`}>
                    <td colSpan={4} className="px-4 pb-4">
                      <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-4 whitespace-pre-wrap font-mono leading-relaxed border border-gray-100 max-h-64 overflow-y-auto">
                        {decodeNote(noteData)}
                      </pre>
                    </td>
                  </tr>
                )}
              </>
            );
          })}
          {!loading && data.length === 0 && <tr><td colSpan={4}><EmptyState message="No diagnostic reports" /></td></tr>}
        </tbody>
      </table>
      <div className="px-4 py-3"><Pagination page={page} totalPages={totalPages} goToPage={goToPage} /></div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Patient chart
// ---------------------------------------------------------------------------

const CHART_TABS = [
  { id: 'observations',       label: 'Observations',       icon: Activity },
  { id: 'conditions',         label: 'Conditions',         icon: FileText },
  { id: 'encounters',         label: 'Encounters',         icon: Calendar },
  { id: 'medications',        label: 'Medications',        icon: Pill },
  { id: 'procedures',         label: 'Procedures',         icon: Scissors },
  { id: 'diagnostic-reports', label: 'Reports',            icon: ClipboardList },
  { id: 'allergies',          label: 'Allergies',          icon: ShieldAlert },
  { id: 'immunizations',      label: 'Immunizations',      icon: Syringe },
] as const;

type ChartTab = typeof CHART_TABS[number]['id'];

function PatientChart({ patient, onBack }: { patient: Patient; onBack: () => void }) {
  const [activeTab, setActiveTab] = useState<ChartTab>('observations');
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const addr = patient.address?.[0];

  const downloadEverything = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const r = await fetch(`/Patient/${patient.id}/$everything`, { headers: { Accept: 'application/fhir+json' } });
      if (!r.ok) {
        const text = await r.text().catch(() => `HTTP ${r.status}`);
        setDownloadError(`${r.status}: ${text.slice(0, 120)}`);
        return;
      }
      const bundle = await r.json();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/fhir+json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `patient-${patient.id}-record.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setDownloadError(String(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div>
      {/* Chart header */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm mb-4 p-5">
        <button onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4" /> All Patients
        </button>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4 min-w-0">
            <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
              <span className="text-blue-700 font-bold text-lg">
                {patientDisplayName(patient).charAt(0)}
              </span>
            </div>
            <div className="min-w-0">
              <h3 className="text-lg font-semibold text-gray-900">{patientDisplayName(patient)}</h3>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-sm text-gray-500">
                <span>{formatDate(patient.birthDate)} · {patientAge(patient.birthDate)}</span>
                <span>{capitalize(patient.gender)}</span>
                {addr && <span>{[addr.city, addr.state].filter(Boolean).join(', ')}</span>}
                <span className="font-mono text-xs">MRN: {mrnOf(patient)}</span>
              </div>
            </div>
          </div>
          <div className="flex-shrink-0 text-right">
            <button onClick={downloadEverything} disabled={downloading}
              className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg hover:border-blue-300 hover:text-blue-600 disabled:opacity-50 transition-colors bg-white"
              title="Download full patient record as FHIR Bundle (Patient/$everything)">
              {downloading
                ? <><AlertCircle className="w-3.5 h-3.5 animate-pulse" /> Downloading…</>
                : <><Download className="w-3.5 h-3.5" /> Download Record</>
              }
            </button>
            {downloadError && (
              <p className="text-xs text-red-600 mt-1 max-w-xs">{downloadError}</p>
            )}
          </div>
        </div>
      </div>

      {/* Tab bar + content */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
        <div className="border-b border-gray-100 flex gap-1 px-4 overflow-x-auto">
          {CHART_TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 px-3 py-3.5 border-b-2 whitespace-nowrap transition-colors text-sm font-medium ${
                activeTab === id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-900'
              }`}>
              <Icon className="w-4 h-4" /> {label}
            </button>
          ))}
        </div>
        {activeTab === 'observations'       && <ObservationsTab      patientId={patient.id} />}
        {activeTab === 'conditions'         && <ConditionsTab        patientId={patient.id} />}
        {activeTab === 'encounters'         && <EncountersTab        patientId={patient.id} />}
        {activeTab === 'medications'        && <MedicationsTab       patientId={patient.id} />}
        {activeTab === 'procedures'         && <ProceduresTab        patientId={patient.id} />}
        {activeTab === 'diagnostic-reports' && <DiagnosticReportsTab patientId={patient.id} />}
        {activeTab === 'allergies'          && <AllergiesTab         patientId={patient.id} />}
        {activeTab === 'immunizations'      && <ImmunizationsTab     patientId={patient.id} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

type ExportNotif = { status: 'running' } | { status: 'done'; jobId: string } | { status: 'error'; msg: string };

export default function ClinicalApp() {
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [exportNotif, setExportNotif] = useState<ExportNotif | null>(null);

  const startPatientExport = async () => {
    setExportNotif({ status: 'running' });
    try {
      const r = await fetch('/Patient/$export', { headers: { Prefer: 'respond-async' } });
      if (r.status !== 202) { setExportNotif({ status: 'error', msg: `HTTP ${r.status}` }); return; }
      const loc = r.headers.get('Content-Location') ?? '';
      const jobId = loc.split('/').pop() ?? '';
      setExportNotif({ status: 'done', jobId });
    } catch (e) {
      setExportNotif({ status: 'error', msg: String(e) });
    }
  };

  return (
    <div className="bg-gray-50 min-h-full">
      {/* Section header */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Users className="w-5 h-5 text-blue-500" />
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  {selectedPatient ? patientDisplayName(selectedPatient) : 'Clinical Resources'}
                </h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  {selectedPatient
                    ? 'Patient Chart'
                    : 'Patient · Observation · Condition · Encounter · AllergyIntolerance · Immunization'}
                </p>
              </div>
            </div>
            {!selectedPatient && (
              <button onClick={startPatientExport} disabled={exportNotif?.status === 'running'}
                className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg hover:border-blue-300 hover:text-blue-600 disabled:opacity-50 transition-colors bg-white">
                <Download className="w-3.5 h-3.5" /> Export Patients
              </button>
            )}
          </div>
          {exportNotif && (
            <div className={`mt-3 flex items-center justify-between rounded-lg px-3 py-2 text-xs ${
              exportNotif.status === 'error' ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
            }`}>
              {exportNotif.status === 'running' && <span>Starting export…</span>}
              {exportNotif.status === 'done' && (
                <span className="flex items-center gap-1.5">
                  <CheckCircle className="w-3.5 h-3.5" />
                  Export started (job {exportNotif.jobId.slice(0, 8)}…) — track progress and download files in the <strong>System</strong> tab.
                </span>
              )}
              {exportNotif.status === 'error' && <span>Export failed: {exportNotif.msg}</span>}
              <button onClick={() => setExportNotif(null)} className="ml-3 opacity-60 hover:opacity-100">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {selectedPatient
          ? <PatientChart patient={selectedPatient} onBack={() => setSelectedPatient(null)} />
          : <PatientList onSelect={setSelectedPatient} />
        }
      </div>
    </div>
  );
}
