import { useEffect, useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { apiFetch } from '../../lib/api';

type FhirBundle = { entry?: { resource: Record<string, unknown> }[]; total?: number };
type FhirResource = Record<string, unknown>;

function codeDisplay(cc: unknown): string {
  if (!cc || typeof cc !== 'object') return '—';
  const c = cc as Record<string, unknown>;
  if (typeof c.text === 'string' && c.text) return c.text;
  const codings = c.coding as Record<string, unknown>[] | undefined;
  return (codings?.[0]?.display as string) || (codings?.[0]?.code as string) || '—';
}

function bundleEntries(b: FhirBundle): FhirResource[] {
  return (b.entry || []).map(e => e.resource);
}

function Section({ title, items, empty, renderItem }: {
  title: string;
  items: FhirResource[];
  empty: string;
  renderItem: (item: FhirResource) => React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="font-semibold text-gray-800 mb-3">{title}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-gray-400">{empty}</p>
      ) : (
        <div className="divide-y divide-gray-100">
          {items.map((item, i) => (
            <div key={(item.id as string) || i} className="py-2 first:pt-0 last:pb-0">
              {renderItem(item)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PatientPortalPage() {
  const { fhirUser } = useAuth();
  const patientId = typeof fhirUser === 'string' && fhirUser.startsWith('Patient/')
    ? fhirUser.slice(8)
    : null;

  const [patient, setPatient] = useState<FhirResource | null>(null);
  const [conditions, setConditions] = useState<FhirResource[]>([]);
  const [medications, setMedications] = useState<FhirResource[]>([]);
  const [observations, setObservations] = useState<FhirResource[]>([]);
  const [allergies, setAllergies] = useState<FhirResource[]>([]);
  const [immunizations, setImmunizations] = useState<FhirResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!patientId) { setLoading(false); return; }
    Promise.all([
      apiFetch<FhirResource>(`/Patient/${patientId}`),
      apiFetch<FhirBundle>('/Condition'),
      apiFetch<FhirBundle>('/MedicationRequest'),
      apiFetch<FhirBundle>('/Observation'),
      apiFetch<FhirBundle>('/AllergyIntolerance'),
      apiFetch<FhirBundle>('/Immunization'),
    ])
      .then(([p, cond, med, obs, allergy, imm]) => {
        setPatient(p);
        setConditions(bundleEntries(cond));
        setMedications(bundleEntries(med));
        setObservations(bundleEntries(obs));
        setAllergies(bundleEntries(allergy));
        setImmunizations(bundleEntries(imm));
      })
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [patientId]);

  if (loading) {
    return <div className="p-8 text-gray-500">Loading your health records...</div>;
  }
  if (error) {
    return <div className="p-8 text-red-600">Error loading records: {error}</div>;
  }
  if (!patientId) {
    return <div className="p-8 text-gray-500">No patient record is linked to your account.</div>;
  }

  const nameObj = patient?.name as Record<string, unknown>[] | undefined;
  const first = nameObj?.[0];
  const given = (first?.given as string[] | undefined)?.join(' ') ?? '';
  const family = (first?.family as string | undefined) ?? '';
  const displayName = [given, family].filter(Boolean).join(' ') || 'Unknown Patient';

  return (
    <div className="p-6 max-w-3xl space-y-5">
      {/* Patient header */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h1 className="text-2xl font-bold text-gray-900">{displayName}</h1>
        <div className="mt-1 flex gap-4 text-sm text-gray-500">
          {patient?.birthDate && <span>Born: {patient.birthDate as string}</span>}
          {patient?.gender && <span className="capitalize">Gender: {patient.gender as string}</span>}
        </div>
      </div>

      <Section
        title="Active Conditions"
        items={conditions}
        empty="No conditions on record."
        renderItem={c => (
          <div className="flex justify-between text-sm">
            <span className="text-gray-800">{codeDisplay(c.code)}</span>
            <span className="text-gray-400">
              {codeDisplay((c.clinicalStatus as Record<string, unknown> | undefined)?.coding?.[0] as unknown
                ?? c.clinicalStatus)}
            </span>
          </div>
        )}
      />

      <Section
        title="Medications"
        items={medications}
        empty="No medications on record."
        renderItem={m => (
          <div className="flex justify-between text-sm">
            <span className="text-gray-800">{codeDisplay(m.medicationCodeableConcept)}</span>
            <span className="text-gray-400">{m.status as string}</span>
          </div>
        )}
      />

      <Section
        title="Recent Observations"
        items={observations}
        empty="No observations on record."
        renderItem={o => {
          const vq = o.valueQuantity as Record<string, unknown> | undefined;
          const value = vq
            ? `${vq.value} ${vq.unit ?? ''}`
            : codeDisplay(o.valueCodeableConcept);
          return (
            <div className="flex justify-between text-sm">
              <span className="text-gray-800">{codeDisplay(o.code)}</span>
              <span className="text-gray-400">{value}</span>
            </div>
          );
        }}
      />

      <Section
        title="Allergies & Intolerances"
        items={allergies}
        empty="No allergies on record."
        renderItem={a => (
          <div className="flex justify-between text-sm">
            <span className="text-gray-800">{codeDisplay(a.code)}</span>
            <span className="text-gray-400">{a.criticality as string}</span>
          </div>
        )}
      />

      <Section
        title="Immunizations"
        items={immunizations}
        empty="No immunizations on record."
        renderItem={i => (
          <div className="flex justify-between text-sm">
            <span className="text-gray-800">{codeDisplay(i.vaccineCode)}</span>
            <span className="text-gray-400">
              {typeof i.occurrenceDateTime === 'string'
                ? i.occurrenceDateTime.slice(0, 10)
                : (i.status as string)}
            </span>
          </div>
        )}
      />
    </div>
  );
}
