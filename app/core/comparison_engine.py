"""Comparison engine for data source alignment and diff analysis."""

import hashlib
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core.query_engine import QueryEngine, QueryResult
from app.core.source_registry import SourceRegistry


class DiffStatus(StrEnum):
    """Classification of difference magnitude."""

    MATCH = "match"
    MINOR_DIFF = "minor_diff"
    MAJOR_DIFF = "major_diff"


@dataclass
class RowComparison:
    """Comparison result for a single aligned row."""

    key: dict[str, Any]
    source_a_value: float | None
    source_b_value: float | None
    absolute_diff: float
    percentage_diff: float | None
    status: DiffStatus


@dataclass
class ComparisonResult:
    """Result of comparing two data sources."""

    source_a: str
    source_b: str
    measure: str
    align_on: list[str]
    rows: list[RowComparison]
    summary: dict[str, Any]
    cache_key: str
    timestamp: float = field(default_factory=time.time)

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def match_count(self) -> int:
        return sum(1 for r in self.rows if r.status == DiffStatus.MATCH)

    @property
    def diff_count(self) -> int:
        return sum(1 for r in self.rows if r.status != DiffStatus.MATCH)


class ComparisonCache:
    """Simple TTL cache for comparison results."""

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize cache with TTL.

        Args:
            ttl_seconds: Time-to-live for cache entries.
        """
        self._cache: dict[str, ComparisonResult] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> ComparisonResult | None:
        """Get cached result if not expired."""
        if key not in self._cache:
            return None

        result = self._cache[key]
        if time.time() - result.timestamp > self._ttl:
            del self._cache[key]
            return None

        return result

    def set(self, result: ComparisonResult) -> None:
        """Store result in cache."""
        self._cache[result.cache_key] = result

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def size(self) -> int:
        """Get number of cached entries."""
        return len(self._cache)


class ComparisonEngine:
    """Engine for comparing data between sources."""

    def __init__(
        self,
        registry: SourceRegistry,
        query_engine: QueryEngine,
        cache: ComparisonCache | None = None,
    ):
        """Initialize comparison engine.

        Args:
            registry: Source registry for definitions.
            query_engine: Query engine for data retrieval.
            cache: Optional cache for results.
        """
        self._registry = registry
        self._query_engine = query_engine
        self._cache = cache or ComparisonCache(
            registry.comparison_config.cache_ttl_seconds
            if registry.comparison_config
            else 3600
        )

    async def compare(
        self,
        source_a_name: str,
        source_b_name: str,
        measure: str,
        align_on: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ComparisonResult:
        """Compare measure between two sources.

        Args:
            source_a_name: First source name.
            source_b_name: Second source name.
            measure: Measure to compare.
            align_on: Dimensions to align on (uses defaults if None).
            filters: Filter conditions to apply to both sources.
            use_cache: Whether to use cached results.

        Returns:
            ComparisonResult with row-by-row comparison.
        """
        # Generate cache key
        cache_key = self._generate_cache_key(
            source_a_name, source_b_name, measure, align_on, filters
        )

        # Check cache
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached:
                return cached

        # Get source definitions
        source_a = self._registry.get(source_a_name)
        source_b = self._registry.get(source_b_name)

        # Determine alignment dimensions
        if align_on is None:
            config = self._registry.comparison_config
            align_on = (
                config.default_align_on if config else ["company", "period"]
            )

        # Validate measure exists in both sources
        if measure not in source_a.measures:
            raise ValueError(f"Measure '{measure}' not found in {source_a_name}")
        if measure not in source_b.measures:
            raise ValueError(f"Measure '{measure}' not found in {source_b_name}")

        # Query both sources
        result_a = await self._query_engine.query(
            source_a, dimensions=align_on, measures=[measure], filters=filters
        )
        result_b = await self._query_engine.query(
            source_b, dimensions=align_on, measures=[measure], filters=filters
        )

        # Align and compare
        rows = self._align_and_compare(result_a, result_b, align_on, measure)

        # Calculate summary
        summary = self._calculate_summary(rows, measure)

        # Create result
        result = ComparisonResult(
            source_a=source_a_name,
            source_b=source_b_name,
            measure=measure,
            align_on=align_on,
            rows=rows,
            summary=summary,
            cache_key=cache_key,
        )

        # Cache result
        self._cache.set(result)

        return result

    def get_cached(self, cache_key: str) -> ComparisonResult | None:
        """Retrieve cached comparison result.

        Args:
            cache_key: Cache key from previous comparison.

        Returns:
            Cached result or None.
        """
        return self._cache.get(cache_key)

    def _generate_cache_key(
        self,
        source_a: str,
        source_b: str,
        measure: str,
        align_on: list[str] | None,
        filters: dict[str, Any] | None,
    ) -> str:
        """Generate deterministic cache key."""
        key_parts = [
            source_a,
            source_b,
            measure,
            str(sorted(align_on) if align_on else []),
            str(sorted(filters.items()) if filters else []),
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()[:16]

    def _align_and_compare(
        self,
        result_a: QueryResult,
        result_b: QueryResult,
        align_on: list[str],
        measure: str,
    ) -> list[RowComparison]:
        """Align rows by key dimensions and compare values."""
        # Build lookup from result_a
        lookup_a: dict[tuple, float] = {}
        for row in result_a.rows:
            key = tuple(row.get(dim) for dim in align_on)
            lookup_a[key] = row.get(measure, 0) or 0

        # Build lookup from result_b
        lookup_b: dict[tuple, float] = {}
        for row in result_b.rows:
            key = tuple(row.get(dim) for dim in align_on)
            lookup_b[key] = row.get(measure, 0) or 0

        # Get all unique keys
        all_keys = set(lookup_a.keys()) | set(lookup_b.keys())

        # Get thresholds
        config = self._registry.comparison_config
        match_threshold = config.thresholds.get("match") if config else None
        minor_threshold = config.thresholds.get("minor_diff") if config else None

        # Compare each key
        comparisons = []
        for key in sorted(all_keys):
            value_a = lookup_a.get(key)
            value_b = lookup_b.get(key)

            abs_diff = abs((value_a or 0) - (value_b or 0))

            # Calculate percentage diff
            pct_diff = None
            if value_a and value_a != 0:
                pct_diff = (abs_diff / abs(value_a)) * 100

            # Determine status
            status = self._classify_diff(abs_diff, pct_diff, match_threshold, minor_threshold)

            # Build key dict
            key_dict = dict(zip(align_on, key, strict=False))

            comparisons.append(
                RowComparison(
                    key=key_dict,
                    source_a_value=value_a,
                    source_b_value=value_b,
                    absolute_diff=abs_diff,
                    percentage_diff=pct_diff,
                    status=status,
                )
            )

        return comparisons

    def _classify_diff(
        self,
        abs_diff: float,
        pct_diff: float | None,
        match_threshold: Any | None,
        minor_threshold: Any | None,
    ) -> DiffStatus:
        """Classify difference magnitude based on thresholds."""
        # Check match threshold
        if match_threshold:
            abs_ok = abs_diff <= match_threshold.absolute
            pct_ok = pct_diff is None or pct_diff <= match_threshold.percentage
            if abs_ok and pct_ok:
                return DiffStatus.MATCH

        # Check minor threshold
        if minor_threshold:
            abs_ok = abs_diff <= minor_threshold.absolute
            pct_ok = pct_diff is None or pct_diff <= minor_threshold.percentage
            if abs_ok and pct_ok:
                return DiffStatus.MINOR_DIFF

        return DiffStatus.MAJOR_DIFF

    def _calculate_summary(
        self, rows: list[RowComparison], measure: str
    ) -> dict[str, Any]:
        """Calculate summary statistics for comparison."""
        total_a = sum(r.source_a_value or 0 for r in rows)
        total_b = sum(r.source_b_value or 0 for r in rows)
        total_diff = abs(total_a - total_b)

        match_count = sum(1 for r in rows if r.status == DiffStatus.MATCH)
        minor_count = sum(1 for r in rows if r.status == DiffStatus.MINOR_DIFF)
        major_count = sum(1 for r in rows if r.status == DiffStatus.MAJOR_DIFF)

        return {
            "measure": measure,
            "total_rows": len(rows),
            "total_source_a": total_a,
            "total_source_b": total_b,
            "total_absolute_diff": total_diff,
            "total_percentage_diff": (
                (total_diff / abs(total_a)) * 100 if total_a != 0 else None
            ),
            "match_count": match_count,
            "minor_diff_count": minor_count,
            "major_diff_count": major_count,
        }
