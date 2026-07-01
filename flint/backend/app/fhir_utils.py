import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
from email.utils import formatdate
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    'fhir_requests_total', 'Total FHIR requests',
    ['method', 'endpoint', 'status']
)
REQUEST_DURATION = Histogram(
    'fhir_request_duration_seconds', 'FHIR request duration',
    ['method', 'endpoint']
)
RESOURCE_COUNT = Counter(
    'fhir_resources_total', 'Total FHIR resources created/updated',
    ['resource_type', 'operation']
)
RATE_LIMIT_EXCEEDED = Counter(
    'fhir_rate_limit_exceeded_total', 'Total requests rejected by per-client rate limiter',
    ['client_type']
)


def _fhir_issue_code(status_code: int) -> str:
    return {
        400: "invalid", 401: "security", 403: "forbidden",
        404: "not-found", 405: "not-supported", 409: "conflict",
        410: "deleted", 422: "processing",
    }.get(status_code, "processing")


def _check_etag(request: Request, existing: Dict) -> None:
    if_match = request.headers.get('If-Match')
    if not if_match:
        if os.environ.get("REQUIRE_IF_MATCH", "false").lower() == "true":
            raise HTTPException(status_code=428, detail="If-Match header is required by this server")
        return
    current_vid = existing.get('meta', {}).get('versionId', '')
    client_vid = if_match.strip().strip('"').lstrip('W/').strip('"')
    if client_vid != str(current_vid):
        raise HTTPException(status_code=412, detail=f"Version conflict: server has version {current_vid}, client sent {if_match}")


def _bundle_links(request: Request, total: int, count: int, offset: int) -> List[Dict]:
    base = str(request.url).split('?')[0]
    params = dict(request.query_params)
    params.pop('_offset', None)

    def link(rel: str, off: int) -> Dict:
        p = {**params, '_count': str(count), '_offset': str(off)}
        qs = '&'.join(f"{k}={v}" for k, v in p.items())
        return {'relation': rel, 'url': f"{base}?{qs}"}

    links = [link('self', offset)]
    if offset > 0:
        links.append(link('prev', max(0, offset - count)))
        links.append(link('first', 0))
    if offset + count < total:
        links.append(link('next', offset + count))
    return links


def _fhir_response(resource: Dict, status_code: int = 200, extra_headers: Optional[Dict] = None, request: Optional[Request] = None) -> JSONResponse:
    headers: Dict[str, str] = {"Content-Type": "application/fhir+json"}
    meta = resource.get('meta', {})
    if vid := meta.get('versionId'):
        headers['ETag'] = f'W/"{vid}"'
    if lu := meta.get('lastUpdated'):
        try:
            dt = datetime.strptime(lu, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
            headers['Last-Modified'] = formatdate(dt.timestamp(), usegmt=True)
        except ValueError:
            pass
    if extra_headers:
        headers.update(extra_headers)

    if request:
        prefer = request.headers.get('Prefer', '')
        if 'return=minimal' in prefer:
            return JSONResponse(content=None, status_code=status_code, headers=headers)
        if 'return=OperationOutcome' in prefer and status_code < 300:
            return JSONResponse(content={
                "resourceType": "OperationOutcome",
                "issue": [{"severity": "information", "code": "informational",
                           "diagnostics": "Operation completed successfully"}]
            }, status_code=status_code, headers=headers)

    return JSONResponse(content=resource, status_code=status_code, headers=headers)
