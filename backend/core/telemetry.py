"""
OpenTelemetry Tracing Configuration

This module provides comprehensive distributed tracing setup for the Analyst Augmentation Agent.
It instruments the entire stack including FastAPI, external APIs, databases, and agent workflows.

Features:
- Auto-instrumentation for FastAPI, httpx, PostgreSQL, Redis
- Custom spans for business logic (fraud detection, graph analysis)
- OTLP exporters for Jaeger/Grafana integration
- Context propagation across async workflows
- Performance monitoring with detailed timing

Usage:
    from backend.core.telemetry import init_telemetry, tracer
    
    # Initialize in main.py
    init_telemetry()
    
    # Use in code
    with tracer.start_as_current_span("custom_operation") as span:
        span.set_attribute("operation.type", "fraud_detection")
        result = await some_operation()

Generated by Factory Droid on 2025-06-28 following "cook & push to GitHub" motto
"""

import logging
import os
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Optional, Union

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.util.http import get_excluded_urls

# Configure module logger
logger = logging.getLogger(__name__)

# Global tracer instance
tracer: Optional[trace.Tracer] = None

# Service information
SERVICE_NAME = "analyst-droid"
SERVICE_VERSION = "1.9.0-beta"
SERVICE_NAMESPACE = "blockchain-analysis"

# Span names and attributes
class SpanNames:
    """Standard span names for consistent tracing."""
    
    # External API calls
    API_CALL = "external_api_call"
    SIM_API_CALL = "sim_api_call"
    COVALENT_API_CALL = "covalent_api_call"
    MORALIS_API_CALL = "moralis_api_call"
    GEMINI_API_CALL = "gemini_api_call"
    
    # Database operations
    NEO4J_QUERY = "neo4j_query"
    NEO4J_INGEST = "neo4j_ingest"
    POSTGRES_QUERY = "postgres_query"
    REDIS_OPERATION = "redis_operation"
    
    # Agent workflows
    CREW_EXECUTION = "crew_execution"
    AGENT_TASK = "agent_task"
    TOOL_EXECUTION = "tool_execution"
    
    # Business logic
    FRAUD_DETECTION = "fraud_detection"
    GRAPH_ANALYSIS = "graph_analysis"
    RAG_QUERY = "rag_query"
    EVIDENCE_PROCESSING = "evidence_processing"

class SpanAttributes:
    """Standard span attributes for consistent metadata."""
    
    # Service attributes
    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"
    SERVICE_NAMESPACE = "service.namespace"
    
    # External API attributes
    API_PROVIDER = "api.provider"
    API_ENDPOINT = "api.endpoint"
    API_METHOD = "api.method"
    API_STATUS_CODE = "api.status_code"
    API_COST_USD = "api.cost_usd"
    API_RATE_LIMITED = "api.rate_limited"
    
    # Database attributes
    DB_SYSTEM = "db.system"
    DB_NAME = "db.name"
    DB_OPERATION = "db.operation"
    DB_QUERY = "db.statement"
    DB_ROWS_AFFECTED = "db.rows_affected"
    
    # Agent attributes
    CREW_NAME = "crew.name"
    AGENT_NAME = "agent.name"
    TASK_TYPE = "task.type"
    TOOL_NAME = "tool.name"
    
    # Business logic attributes
    WALLET_ADDRESS = "blockchain.wallet_address"
    CHAIN_ID = "blockchain.chain_id"
    TOKEN_ADDRESS = "blockchain.token_address"
    FRAUD_SCORE = "fraud.score"
    FRAUD_TYPE = "fraud.type"

def init_telemetry(
    otlp_endpoint: Optional[str] = None,
    console_export: bool = False,
    excluded_urls: Optional[str] = None
) -> None:
    """
    Initialize OpenTelemetry tracing for the application.
    
    Args:
        otlp_endpoint: OTLP exporter endpoint (defaults to env var or console)
        console_export: Whether to export to console for debugging
        excluded_urls: Comma-separated URLs to exclude from tracing
    """
    global tracer
    
    # Create resource with service information
    resource = Resource.create({
        SpanAttributes.SERVICE_NAME: SERVICE_NAME,
        SpanAttributes.SERVICE_VERSION: SERVICE_VERSION,
        SpanAttributes.SERVICE_NAMESPACE: SERVICE_NAMESPACE,
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })
    
    # Set up tracer provider
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer = trace.get_tracer(__name__, SERVICE_VERSION)
    
    # Configure span processors and exporters
    _setup_exporters(otlp_endpoint, console_export)
    
    # Set up auto-instrumentation
    _setup_auto_instrumentation(excluded_urls)
    
    # Configure propagators for distributed tracing
    set_global_textmap(B3MultiFormat())
    
    logger.info(f"OpenTelemetry initialized for {SERVICE_NAME} v{SERVICE_VERSION}")

def _setup_exporters(otlp_endpoint: Optional[str], console_export: bool) -> None:
    """Set up span exporters."""
    tracer_provider = trace.get_tracer_provider()
    
    # OTLP exporter (for Jaeger, Grafana, etc.)
    effective_otlp_endpoint = otlp_endpoint or os.getenv("OTLP_EXPORTER_ENDPOINT")
    if effective_otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(
            endpoint=effective_otlp_endpoint,
            headers={"Authorization": f"Bearer {os.getenv('OTLP_AUTH_TOKEN', '')}"}
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info(f"OTLP exporter configured for endpoint: {effective_otlp_endpoint}")
    
    # Console exporter (for development/debugging)
    if console_export or os.getenv("OTEL_TRACE_CONSOLE", "false").lower() == "true":
        console_exporter = ConsoleSpanExporter()
        tracer_provider.add_span_processor(BatchSpanProcessor(console_exporter))
        logger.info("Console trace exporter enabled")

def _setup_auto_instrumentation(excluded_urls_str: Optional[str]) -> None:
    """Set up automatic instrumentation for common libraries."""
    
    # Determine excluded URLs
    excluded_urls = get_excluded_urls("OTEL_PYTHON_EXCLUDED_URLS")
    if excluded_urls_str:
        excluded_urls.extend(excluded_urls_str.split(","))
    
    # FastAPI instrumentation is handled explicitly in `backend.main`
    
    # HTTP client instrumentation
    try:
        HTTPXClientInstrumentor().instrument(
            request_hook=_httpx_request_hook,
            response_hook=_httpx_response_hook
        )
        RequestsInstrumentor().instrument()
        logger.info("HTTP client auto-instrumentation enabled")
    except Exception as e:
        logger.warning(f"HTTP client instrumentation failed: {e}")
    
    # Database instrumentation
    try:
        Psycopg2Instrumentor().instrument()
        RedisInstrumentor().instrument()
        logger.info("Database auto-instrumentation enabled")
    except Exception as e:
        logger.warning(f"Database instrumentation failed: {e}")
    
    # Logging instrumentation
    try:
        LoggingInstrumentor().instrument()
        logger.info("Logging auto-instrumentation enabled")
    except Exception as e:
        logger.warning(f"Logging instrumentation failed: {e}")

def _fastapi_request_hook(span: trace.Span, scope: Dict[str, Any]) -> None:
    """Hook for FastAPI request instrumentation."""
    if span and span.is_recording():
        # Add custom request attributes
        span.set_attribute("http.route", scope.get("route", {}).get("path", "unknown"))
        span.set_attribute("fastapi.version", "0.104.1")

def _fastapi_response_hook(span: trace.Span, message: Dict[str, Any]) -> None:
    """Hook for FastAPI response instrumentation."""
    if span and span.is_recording():
        # Add response metadata
        if "status" in message:
            span.set_attribute("http.status_code", message["status"])

def _httpx_request_hook(span: trace.Span, request) -> None:
    """Hook for HTTP client request instrumentation."""
    if span and span.is_recording():
        # Detect provider from URL
        url = str(request.url)
        provider = _detect_api_provider(url)
        if provider:
            span.set_attribute(SpanAttributes.API_PROVIDER, provider)
            span.update_name(f"{provider}_api_call")

def _httpx_response_hook(span: trace.Span, response) -> None:
    """Hook for HTTP client response instrumentation."""
    if span and span.is_recording():
        span.set_attribute(SpanAttributes.API_STATUS_CODE, response.status_code)
        
        # Add rate limiting information
        if response.status_code == 429:
            span.set_attribute(SpanAttributes.API_RATE_LIMITED, True)
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                span.set_attribute("api.retry_after", retry_after)

def _detect_api_provider(url: str) -> Optional[str]:
    """Detect API provider from URL."""
    if "api.sim.dune.com" in url:
        return "sim"
    elif "api.covalenthq.com" in url:
        return "covalent"
    elif "deep-index.moralis.io" in url:
        return "moralis"
    elif "generativelanguage.googleapis.com" in url:
        return "gemini"
    return None

# Decorators for manual instrumentation

def trace_function(
    span_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
) -> Callable:
    """
    Decorator to trace function execution.
    
    Args:
        span_name: Custom span name (defaults to function name)
        attributes: Additional span attributes
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            name = span_name or f"{func.__module__}.{func.__name__}"
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            name = span_name or f"{func.__module__}.{func.__name__}"
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                
                try:
                    result = func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        
        # Check if the function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator

@contextmanager
def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL
):
    """
    Context manager for creating custom spans.
    
    Args:
        name: Span name
        attributes: Span attributes
        kind: Span kind (INTERNAL, CLIENT, SERVER, PRODUCER, CONSUMER)
    """
    with tracer.start_as_current_span(name, kind=kind) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        
        try:
            yield span
            span.set_status(trace.Status(trace.StatusCode.OK))
        except Exception as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise

# Utility functions

def get_current_span() -> Optional[trace.Span]:
    """Get the current active span."""
    return trace.get_current_span()

def add_span_attribute(key: str, value: Any) -> None:
    """Add attribute to current span if active."""
    span = get_current_span()
    if span and span.is_recording():
        span.set_attribute(key, value)

def add_span_event(name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """Add event to current span if active."""
    span = get_current_span()
    if span and span.is_recording():
        span.add_event(name, attributes or {})

def set_span_error(error: Exception) -> None:
    """Mark current span as error and record exception."""
    span = get_current_span()
    if span and span.is_recording():
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(error)))
        span.record_exception(error)

# Business logic helpers

def trace_api_call(
    provider: str,
    endpoint: str,
    method: str = "GET"
) -> Callable:
    """Decorator for tracing external API calls."""
    return trace_function(
        span_name=f"{provider}_api_call",
        attributes={
            SpanAttributes.API_PROVIDER: provider,
            SpanAttributes.API_ENDPOINT: endpoint,
            SpanAttributes.API_METHOD: method
        }
    )

def trace_db_operation(
    system: str,
    operation: str,
    db_name: Optional[str] = None
) -> Callable:
    """Decorator for tracing database operations."""
    attributes = {
        SpanAttributes.DB_SYSTEM: system,
        SpanAttributes.DB_OPERATION: operation
    }
    if db_name:
        attributes[SpanAttributes.DB_NAME] = db_name
    
    return trace_function(
        span_name=f"{system}_{operation}",
        attributes=attributes
    )

def trace_agent_task(
    crew_name: str,
    agent_name: str,
    task_type: str
) -> Callable:
    """Decorator for tracing agent task execution."""
    return trace_function(
        span_name=SpanNames.AGENT_TASK,
        attributes={
            SpanAttributes.CREW_NAME: crew_name,
            SpanAttributes.AGENT_NAME: agent_name,
            SpanAttributes.TASK_TYPE: task_type
        }
    )

def trace_fraud_detection(
    detection_type: str,
    wallet_address: Optional[str] = None
) -> Callable:
    """Decorator for tracing fraud detection operations."""
    attributes = {SpanAttributes.FRAUD_TYPE: detection_type}
    if wallet_address:
        attributes[SpanAttributes.WALLET_ADDRESS] = wallet_address
    
    return trace_function(
        span_name=SpanNames.FRAUD_DETECTION,
        attributes=attributes
    )

# Module initialization
if not tracer:
    # Auto-initialize if environment variables are set
    if os.getenv("OTEL_TRACE_ENABLED", "false").lower() == "true":
        init_telemetry(
            otlp_endpoint=os.getenv("OTLP_EXPORTER_ENDPOINT"),
            console_export=os.getenv("OTEL_TRACE_CONSOLE", "false").lower() == "true"
        )
