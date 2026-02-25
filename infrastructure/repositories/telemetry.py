"""Telemetry repository for tracking AI usage metrics."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TelemetryRepository:
    """Repository for managing telemetry data."""

    def __init__(self, telemetry_file: Path):
        self.telemetry_file = telemetry_file
        self._metrics: List[Dict[str, Any]] = []
        self._load_telemetry()

    def _load_telemetry(self) -> None:
        """Load telemetry data from JSON file."""
        if not self.telemetry_file.exists():
            logger.info(f"Telemetry file not found, starting fresh: {self.telemetry_file}")
            self._metrics = []
            return

        try:
            with open(self.telemetry_file, "r", encoding="utf-8") as f:
                self._metrics = json.load(f)
            logger.info(f"Loaded {len(self._metrics)} telemetry records")
        except Exception:
            logger.exception("Failed to load telemetry data")
            self._metrics = []

    def _save_telemetry(self) -> None:
        """Save telemetry data to JSON file."""
        try:
            with open(self.telemetry_file, "w", encoding="utf-8") as f:
                json.dump(self._metrics, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("Failed to save telemetry data")

    def record_request(
        self,
        user_id: int,
        chat_id: int,
        model: str,
        tokens_input: int,
        tokens_output: int,
        tokens_cached: int = 0,
        latency_ms: int = 0,
        tool_calls: Optional[List[str]] = None,
        error: Optional[str] = None,
        retries: int = 0,
        cost_usd: Optional[float] = None,
    ) -> None:
        """Record a telemetry event for an AI request.

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            model: Model name
            tokens_input: Number of input tokens
            tokens_output: Number of output tokens
            tokens_cached: Number of cached tokens
            latency_ms: Request latency in milliseconds
            tool_calls: List of tool names called
            error: Error message if request failed
            retries: Number of retries attempted
            cost_usd: Cost in USD from OpenRouter usage.cost (1 credit = $1 USD)
        """
        actual_cost = cost_usd if cost_usd is not None else 0.0

        # Extract provider from model name (e.g., "x-ai/grok-4.1-fast" -> "x-ai")
        provider = model.split("/")[0] if "/" in model else "unknown"

        metric = {
            "user_id": user_id,
            "chat_id": chat_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "provider": provider,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tokens_cached": tokens_cached,
            "tokens_total": tokens_input + tokens_output,
            "cost_usd": actual_cost,
            "latency_ms": latency_ms,
            "tool_calls": tool_calls or [],
            "error": error,
            "retries": retries,
        }

        self._metrics.append(metric)
        self._save_telemetry()

        logger.info(
            f"Recorded telemetry: user={user_id}, tokens={metric['tokens_total']}, cost=${actual_cost:.6f}"
        )

    def _get_window_start(self, hours: int) -> datetime:
        """Get the start time for the sliding window.

        Args:
            hours: Number of hours to look back

        Returns:
            DateTime object representing window start
        """
        return datetime.now(timezone.utc) - timedelta(hours=hours)

    def _filter_by_window(self, metrics: List[Dict], hours: int) -> List[Dict]:
        """Filter metrics to those within the time window.

        Args:
            metrics: List of metric dictionaries
            hours: Number of hours to look back

        Returns:
            Filtered list of metrics
        """
        window_start = self._get_window_start(hours)
        filtered = []

        for metric in metrics:
            try:
                timestamp = datetime.fromisoformat(metric["timestamp"])
                if timestamp >= window_start:
                    filtered.append(metric)
            except (KeyError, ValueError):
                logger.warning(f"Invalid timestamp in metric: {metric}")
                continue

        return filtered

    def get_user_tokens_in_window(self, user_id: int, hours: int = 3) -> int:
        """Get total tokens used by user in the time window.

        Args:
            user_id: Telegram user ID
            hours: Number of hours to look back (default: 3)

        Returns:
            Total number of tokens used
        """
        user_metrics = [m for m in self._metrics if m.get("user_id") == user_id]
        windowed = self._filter_by_window(user_metrics, hours)
        return sum(m.get("tokens_total", 0) for m in windowed)

    def get_user_cost_in_window(self, user_id: int, hours: int = 3) -> float:
        """Get total cost for user in the time window.

        Args:
            user_id: Telegram user ID
            hours: Number of hours to look back (default: 3)

        Returns:
            Total cost in USD
        """
        user_metrics = [m for m in self._metrics if m.get("user_id") == user_id]
        windowed = self._filter_by_window(user_metrics, hours)
        return round(sum(m.get("cost_usd", 0.0) for m in windowed), 6)

    def get_top_offenders(
        self, limit: int = 10, hours: int = 3, by: str = "tokens"
    ) -> List[Dict[str, Any]]:
        """Get top users by token usage or cost.

        Args:
            limit: Number of top users to return
            hours: Number of hours to look back
            by: Sort by "tokens" or "cost"

        Returns:
            List of dicts with user_id and usage stats
        """
        windowed = self._filter_by_window(self._metrics, hours)

        # Aggregate by user
        user_stats: Dict[int, Dict[str, Any]] = {}
        for metric in windowed:
            user_id = metric.get("user_id")
            if user_id is None:
                continue

            if user_id not in user_stats:
                user_stats[user_id] = {
                    "user_id": user_id,
                    "tokens_total": 0,
                    "cost_usd": 0.0,
                    "requests": 0,
                }

            user_stats[user_id]["tokens_total"] += metric.get("tokens_total", 0)
            user_stats[user_id]["cost_usd"] += metric.get("cost_usd", 0.0)
            user_stats[user_id]["requests"] += 1

        # Sort by requested metric
        sort_key = "tokens_total" if by == "tokens" else "cost_usd"
        sorted_users = sorted(user_stats.values(), key=lambda x: x[sort_key], reverse=True)

        return sorted_users[:limit]

    def get_model_stats(self, hours: int = 3) -> List[Dict[str, Any]]:
        """Get statistics grouped by model.

        Args:
            hours: Number of hours to look back

        Returns:
            List of dicts with model stats
        """
        windowed = self._filter_by_window(self._metrics, hours)

        # Aggregate by model
        model_stats: Dict[str, Dict[str, Any]] = {}
        for metric in windowed:
            model = metric.get("model", "unknown")

            if model not in model_stats:
                model_stats[model] = {
                    "model": model,
                    "requests": 0,
                    "tokens_total": 0,
                    "cost_usd": 0.0,
                    "avg_latency_ms": 0,
                }

            model_stats[model]["requests"] += 1
            model_stats[model]["tokens_total"] += metric.get("tokens_total", 0)
            model_stats[model]["cost_usd"] += metric.get("cost_usd", 0.0)
            model_stats[model]["avg_latency_ms"] += metric.get("latency_ms", 0)

        # Calculate averages
        for stats in model_stats.values():
            if stats["requests"] > 0:
                stats["avg_latency_ms"] = int(stats["avg_latency_ms"] / stats["requests"])

        # Sort by requests
        sorted_models = sorted(model_stats.values(), key=lambda x: x["requests"], reverse=True)

        return sorted_models

    def get_overall_stats(self, hours: int = 3) -> Dict[str, Any]:
        """Get overall statistics for the time window.

        Args:
            hours: Number of hours to look back

        Returns:
            Dictionary with overall stats
        """
        windowed = self._filter_by_window(self._metrics, hours)

        if not windowed:
            return {
                "requests": 0,
                "tokens_total": 0,
                "cost_usd": 0.0,
                "unique_users": 0,
                "avg_tokens_per_request": 0,
                "avg_latency_ms": 0,
            }

        total_requests = len(windowed)
        total_tokens = sum(m.get("tokens_total", 0) for m in windowed)
        total_cost = sum(m.get("cost_usd", 0.0) for m in windowed)
        unique_users = len(set(m.get("user_id") for m in windowed if m.get("user_id")))
        total_latency = sum(m.get("latency_ms", 0) for m in windowed)

        return {
            "requests": total_requests,
            "tokens_total": total_tokens,
            "cost_usd": round(total_cost, 6),
            "unique_users": unique_users,
            "avg_tokens_per_request": (
                int(total_tokens / total_requests) if total_requests > 0 else 0
            ),
            "avg_latency_ms": int(total_latency / total_requests) if total_requests > 0 else 0,
        }

    def get_all_metrics(self) -> List[Dict[str, Any]]:
        """Get all telemetry metrics for export.

        Returns:
            List of all metric dictionaries
        """
        return self._metrics.copy()

    def restore_from_json(self, json_content: str) -> bool:
        """Restore telemetry from JSON content.

        Args:
            json_content: JSON string with telemetry data

        Returns:
            True if successful, False otherwise
        """
        try:
            new_metrics = json.loads(json_content)
            if not isinstance(new_metrics, list):
                logger.error("Invalid telemetry data: expected list")
                return False

            # Basic validation
            for metric in new_metrics:
                if not isinstance(metric, dict):
                    logger.error("Invalid metric format")
                    return False

            self._metrics = new_metrics
            self._save_telemetry()
            logger.info(f"Restored {len(self._metrics)} telemetry records")
            return True
        except Exception:
            logger.exception("Failed to restore telemetry from JSON")
            return False
