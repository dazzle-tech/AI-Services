"""HTTP client utilities for service-to-service communication."""
import time
import logging
import requests
from typing import Dict, Any, Tuple, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


def post_json_raw(url: str, payload: Dict[str, Any], timeout: Optional[int] = None) -> Tuple[bool, Dict[str, Any], str, Optional[int], int]:
    """
    Make a POST request and return result with latency tracking.
    
    Args:
        url: Target URL
        payload: JSON payload
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (success, response_body, error_message, status_code, latency_ms)
    """
    timeout = timeout or settings.http_timeout_secs
    start = time.perf_counter()
    
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        latency_ms = int((time.perf_counter() - start) * 1000)
        
        if r.status_code >= 400:
            return False, {}, f"HTTP {r.status_code}: {r.text}", r.status_code, latency_ms
        
        return True, r.json(), "", r.status_code, latency_ms
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return False, {}, str(e), None, latency_ms


def post_json_logged(
    interaction_id: Optional[int],
    service: str,
    url: str,
    payload: Dict[str, Any],
    audit_service: Optional[Any] = None,
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Make a POST request with audit logging.
    
    Args:
        interaction_id: Interaction ID for audit logging
        service: Service name (e.g., "sql_generator")
        url: Target URL
        payload: JSON payload
        audit_service: Audit service instance (optional, for dependency injection)
        
    Returns:
        Tuple of (success, response_body, error_message)
    """
    ok, body, err, status_code, latency_ms = post_json_raw(url, payload)
    
    if interaction_id is not None and audit_service is not None:
        audit_service.insert_service_call(
            interaction_id=interaction_id,
            service=service,
            url=url,
            ok=ok,
            status_code=status_code,
            latency_ms=latency_ms,
            request_json=payload,
            response_json=body if ok else {"error": err},
            error=err,
        )
    
    return ok, body, err



