"""
Simple metrics collection — tracks counters, gauges, histograms.
Phase 4: Permissions + Polish (Observability)
"""

import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)

@dataclass
class MetricValue:
    """A single metric value with timestamp"""
    timestamp: float
    value: float
    tags: Dict[str, str] = field(default_factory=dict)

class MetricsCollector:
    """
    Simple in-memory metrics collector.
    Supports: counters, gauges, histograms.
    Exposes /metrics endpoint in simple format.
    """

    def __init__(self):
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()

        self._histogram_summary: Dict[str, Dict[str, float]] = defaultdict(dict)

        logger.info("MetricsCollector initialized")

    def inc_counter(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None):
        """Increment a counter"""
        key = self._tagged_key(name, tags)
        with self._lock:
            self._counters[key] += value

    def get_counter(self, name: str, tags: Optional[Dict[str, str]] = None) -> float:
        """Get counter value"""
        key = self._tagged_key(name, tags)
        with self._lock:
            return self._counters.get(key, 0.0)

    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Set a gauge value"""
        key = self._tagged_key(name, tags)
        with self._lock:
            self._gauges[key] = value

    def get_gauge(self, name: str, tags: Optional[Dict[str, str]] = None) -> float:
        """Get gauge value"""
        key = self._tagged_key(name, tags)
        with self._lock:
            return self._gauges.get(key, 0.0)

    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record a histogram observation"""
        key = self._tagged_key(name, tags)
        with self._lock:
            self._histograms[key].append(value)

            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]

    def get_histogram_summary(
        self,
        name: str,
        tags: Optional[Dict[str, str]] = None,
        percentiles: List[float] = None
    ) -> Dict[str, float]:
        """
        Get histogram summary (count, sum, avg, p50, p95, p99).

        Args:
            name: Metric name
            tags: Optional tags
            percentiles: Which percentiles to compute (default [50, 95, 99])

        Returns:
            Dict with summary statistics
        """
        if percentiles is None:
            percentiles = [50, 95, 99]

        key = self._tagged_key(name, tags)
        with self._lock:
            values = self._histograms.get(key, [])

        if not values:
            return {"count": 0, "sum": 0.0, "avg": 0.0}

        import numpy as np
        arr = np.array(values)
        summary = {
            "count": len(values),
            "sum": float(arr.sum()),
            "avg": float(arr.mean()),
        }

        for p in percentiles:
            summary[f"p{p}"] = float(np.percentile(arr, p))

        return summary

    def _tagged_key(self, name: str, tags: Optional[Dict[str, str]]) -> str:
        """Build key with tags"""
        if not tags:
            return name

        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{ {tag_str} }}"

    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus text format.
        Simple implementation without full client library.
        """
        lines = []

        for key, value in sorted(self._counters.items()):
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {value}")

        for key, value in sorted(self._gauges.items()):
            lines.append(f"# TYPE {key.split('{')[0]} gauge")
            lines.append(f"{key} {value}")

        for key, values in sorted(self._histograms.items()):
            if not values:
                continue
            metric_name = key.split('{')[0]
            summary = self.get_histogram_summary(metric_name, tags=self._extract_tags(key))
            lines.append(f"# TYPE {metric_name} summary")
            lines.append(f"{key}_count {summary['count']}")
            lines.append(f"{key}_sum {summary['sum']}")
            lines.append(f"{key}_avg {summary['avg']}")

        return "\n".join(lines)

    def _extract_tags(self, key: str) -> Dict[str, str]:
        """Extract tags from key string"""
        if "{" not in key or "}" not in key:
            return {}
        tag_part = key.split("{", 1)[1].rsplit("}", 1)[0]
        tags = {}
        for pair in tag_part.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                tags[k.strip()] = v.strip()
        return tags

    def clear(self):
        """Reset all metrics (useful for testing)"""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

metrics = MetricsCollector()

def get_metrics() -> MetricsCollector:
    """Get the global metrics collector"""
    return metrics

def _coerce_tags(tags_kw, kwargs):
    if tags_kw and isinstance(tags_kw, dict):
        merged = dict(tags_kw)
        merged.update(kwargs)
        return merged
    return kwargs or None

def increment_counter(name: str, value: float = 1.0, tags=None, **kwargs):
    """Increment a counter with tags"""
    metrics.inc_counter(name, value, _coerce_tags(tags, kwargs))

def set_gauge(name: str, value: float, tags=None, **kwargs):
    """Set a gauge value with tags"""
    metrics.set_gauge(name, value, _coerce_tags(tags, kwargs))

def record_histogram(name: str, value: float, tags=None, **kwargs):
    """Record histogram observation with tags"""
    metrics.record_histogram(name, value, _coerce_tags(tags, kwargs))

class MetricNames:
    """Standard metric names"""

    AGENTIC_REQUESTS = "agentic_requests_total"
    AGENTIC_REQUEST_DURATION = "agentic_request_duration_seconds"
    AGENTIC_TURNS = "agentic_turns_total"
    AGENTIC_COST = "agentic_cost_usd_total"
    AGENTIC_ERRORS = "agentic_errors_total"

    COORDINATOR_SESSIONS = "coordinator_sessions_total"
    COORDINATOR_SESSION_COST = "coordinator_session_cost_usd"
    COORDINATOR_WORKERS_SPAWNED = "coordinator_workers_spawned_total"
    COORDINATOR_WORKERS_ACTIVE = "coordinator_workers_active"
    COORDINATOR_WORKERS_COMPLETED = "coordinator_workers_completed_total"
    COORDINATOR_WORKERS_FAILED = "coordinator_workers_failed_total"
    COORDINATOR_WORKER_DURATION = "coordinator_worker_duration_seconds"
    COORDINATOR_BUDGET_EXCEEDED = "coordinator_budget_exceeded_total"

    TOOL_EXECUTIONS = "tool_executions_total"
    TOOL_DURATION = "tool_duration_seconds"

    BILLING_COST = "billing_cost_usd_total"
    BILLING_BUDGET_EXCEEDED = "billing_budget_exceeded_total"

    ACTIVE_SESSIONS = "active_sessions"
    TRANSCRIPT_QUEUE_SIZE = "transcript_queue_size"

def track_request_latency(func):
    """Decorator to track request latency"""
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            increment_counter(MetricNames.AGENTIC_REQUESTS, tags={"status": "success"})
            record_histogram(MetricNames.AGENTIC_REQUEST_DURATION, duration)
            return result
        except Exception as e:
            duration = time.time() - start_time
            increment_counter(MetricNames.AGENTIC_ERRORS, tags={"error": type(e).__name__})
            record_histogram(MetricNames.AGENTIC_REQUEST_DURATION, duration)
            raise

    return wrapper