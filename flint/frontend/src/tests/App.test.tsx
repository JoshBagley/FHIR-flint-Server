import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';

// ---------------------------------------------------------------------------
// Fetch mock helpers
// ---------------------------------------------------------------------------

const EMPTY_BUNDLE = { resourceType: 'Bundle', type: 'searchset', total: 0, entry: [] };

const SAMPLE_BUNDLE = {
  resourceType: 'Bundle',
  type: 'searchset',
  total: 2,
  entry: [
    {
      resource: {
        id: 'vs-1',
        resourceType: 'ValueSet',
        url: 'http://example.com/vs/gender',
        name: 'AdministrativeGender',
        title: 'Administrative Gender',
        status: 'active',
        version: '1.0',
        description: 'Gender codes for administrative use',
        compose: { include: [{ concept: [{ code: 'male' }, { code: 'female' }] }] },
      },
    },
    {
      resource: {
        id: 'vs-2',
        resourceType: 'ValueSet',
        url: 'http://example.com/vs/country',
        name: 'CountryCodes',
        title: 'Country Codes',
        status: 'active',
        version: '2.0',
        description: 'ISO 3166-1 country codes',
        compose: { include: [{ concept: [] }] },
      },
    },
  ],
};

const STATS = { total_valuesets: 42, total_codesystems: 7, total_versions: 120 };

function mockFetch(responses: Record<string, unknown>) {
  return vi.fn((url: string) => {
    const key = Object.keys(responses).find(k => url.includes(k));
    const body = key ? responses[key] : EMPTY_BUNDLE;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    });
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('App', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = mockFetch({
      'analytics/summary': STATS,
      'ValueSet': SAMPLE_BUNDLE,
      'CodeSystem': EMPTY_BUNDLE,
    });
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the page header', () => {
    render(<App />);
    expect(screen.getByText('Flint-FHIR')).toBeInTheDocument();
    expect(screen.getByText('FHIR R4 Terminology Server')).toBeInTheDocument();
  });

  it('shows loading state initially', () => {
    render(<App />);
    expect(screen.getByText(/Loading ValueSets/i)).toBeInTheDocument();
  });

  it('renders resource cards after fetch', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Administrative Gender')).toBeInTheDocument();
      expect(screen.getByText('Country Codes')).toBeInTheDocument();
    });
  });

  it('shows stats in header after load', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('42 ValueSets')).toBeInTheDocument();
      expect(screen.getByText('7 CodeSystems')).toBeInTheDocument();
    });
  });

  it('switches to CodeSystem tab', async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => screen.getByText('Administrative Gender'));

    const csTab = screen.getByRole('button', { name: /Code Systems/i });
    await user.click(csTab);

    await waitFor(() => {
      expect(screen.getByText(/No CodeSystems found/i)).toBeInTheDocument();
    });
  });

  it('shows empty state when server has no data', async () => {
    vi.stubGlobal('fetch', mockFetch({
      'analytics/summary': STATS,
      'ValueSet': EMPTY_BUNDLE,
      'CodeSystem': EMPTY_BUNDLE,
    }));
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/No ValueSets found/i)).toBeInTheDocument();
    });
  });

  it('opens detail panel when a resource card is clicked', async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => screen.getByText('Administrative Gender'));

    await user.click(screen.getByText('Administrative Gender'));
    expect(screen.getByText('Resource Details')).toBeInTheDocument();
  });

  it('closes detail panel when × is clicked', async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => screen.getByText('Administrative Gender'));

    await user.click(screen.getByText('Administrative Gender'));
    expect(screen.getByText('Resource Details')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '×' }));
    expect(screen.queryByText('Resource Details')).not.toBeInTheDocument();
  });

  it('navigates to Analytics tab', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('button', { name: /Analytics/i }));
    expect(screen.getByText('Value Sets')).toBeInTheDocument();
    expect(screen.getByText('Code Systems')).toBeInTheDocument();
  });

  it('shows error banner when API fails', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))));
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Failed to load data')).toBeInTheDocument();
    });
  });

  it('debounces search input before fetching', async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => screen.getByText('Administrative Gender'));

    const searchBox = screen.getByPlaceholderText(/Search by name/i);
    await user.type(searchBox, 'gender');

    // fetch should not be called immediately for each keystroke
    const callCountAfterTyping = fetchSpy.mock.calls.length;
    // after debounce settles, one more call should be made
    await waitFor(() => {
      expect(fetchSpy.mock.calls.length).toBeGreaterThan(callCountAfterTyping);
    }, { timeout: 1000 });
  });
});
