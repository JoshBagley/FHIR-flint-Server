import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../lib/api';

interface FhirBundle<T> {
  total?: number;
  entry?: Array<{ resource: T }>;
  link?: Array<{ relation: string; url: string }>;
}

interface SearchState<T> {
  data: T[];
  total: number;
  loading: boolean;
  error: string | null;
}

interface UseFhirSearchOptions {
  params?: Record<string, string | number | undefined>;
  enabled?: boolean;
  pageSize?: number;
}

export function useFhirSearch<T>(
  resourceType: string,
  options: UseFhirSearchOptions = {},
) {
  const { params = {}, enabled = true, pageSize = 20 } = options;

  const [state, setState] = useState<SearchState<T>>({
    data: [],
    total: 0,
    loading: false,
    error: null,
  });
  const [offset, setOffset] = useState(0);

  const buildUrl = useCallback(() => {
    const qs = new URLSearchParams();
    qs.set('_count', String(pageSize));
    qs.set('_offset', String(offset));
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') qs.set(k, String(v));
    }
    return `/${resourceType}?${qs.toString()}`;
  }, [resourceType, offset, pageSize, JSON.stringify(params)]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState(s => ({ ...s, loading: true, error: null }));
    apiFetch<FhirBundle<T>>(buildUrl())
      .then(bundle => {
        if (!cancelled) {
          setState({
            data: (bundle.entry ?? []).map(e => e.resource),
            total: bundle.total ?? 0,
            loading: false,
            error: null,
          });
        }
      })
      .catch(err => {
        if (!cancelled) {
          setState(s => ({ ...s, loading: false, error: String(err) }));
        }
      });
    return () => { cancelled = true; };
  }, [buildUrl, enabled]);

  const goToPage = useCallback((page: number) => {
    setOffset(page * pageSize);
  }, [pageSize]);

  const page = Math.floor(offset / pageSize);
  const totalPages = Math.ceil(state.total / pageSize);

  return { ...state, page, totalPages, goToPage };
}
