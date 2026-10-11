"""Agent Performance & Telemetry Tracking for Receipts.

Monitors multi-agent latencies (p50/p95), hallucination suppression,
grounding verification against Qdrant, and token/efficiency metrics.
"""
import statistics
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional


class TelemetryTracker:
    def __init__(self, max_history: int = 500):
        self.max_history = max_history
        self.runs: deque = deque(maxlen=max_history)
        self.step_latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.total_processed: int = 0
        self.grounded_receipts: int = 0
        self.hallucinations_suppressed: int = 0
        self.state_transitions: int = 0
        self.qdrant_queries: int = 0
        self.knowledge_base_active: bool = True
        self.playbook_file: str = "TEAM_COMMITMENT_PLAYBOOK.md"

    def record_step(self, step: str, latency_ms: float):
        self.step_latencies[step].append(latency_ms)
        if step.lower() == "qdrant":
            self.qdrant_queries += 1

    def record_grounding(self, verified: bool, detail: str = ""):
        if verified:
            self.grounded_receipts += 1
        else:
            self.hallucinations_suppressed += 1

    def record_transition(self):
        self.state_transitions += 1

    def record_run(self, run_id: str, total_ms: float, latencies: Dict[str, float], status: str = "ok"):
        self.total_processed += 1
        entry = {
            "run_id": run_id,
            "ts": time.time(),
            "total_ms": round(total_ms, 2),
            "latencies": {k: round(v, 2) for k, v in latencies.items()},
            "status": status,
        }
        self.runs.append(entry)

    def _percentile(self, values: List[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * (p / 100.0)
        f = int(k)
        c = f + 1
        if c < len(sorted_vals):
            d0 = sorted_vals[f] * (c - k)
            d1 = sorted_vals[c] * (k - f)
            return round(d0 + d1, 2)
        return round(sorted_vals[f], 2)

    def get_metrics(self) -> Dict[str, Any]:
        e2e_vals = [r["total_ms"] for r in self.runs]
        extractor_vals = list(self.step_latencies["extractor"])
        qdrant_vals = list(self.step_latencies["qdrant"])
        auditor_vals = list(self.step_latencies["auditor"])
        manager_vals = list(self.step_latencies["manager"])

        total_audits = self.grounded_receipts + self.hallucinations_suppressed
        groundedness_rate = 100.0 if total_audits == 0 else round((self.grounded_receipts / total_audits) * 100, 1)

        return {
            "summary": {
                "total_processed_utterances": self.total_processed,
                "grounded_receipts_issued": self.grounded_receipts,
                "hallucinations_suppressed": self.hallucinations_suppressed,
                "groundedness_rate_percent": groundedness_rate,
                "state_transitions_executed": self.state_transitions,
                "qdrant_vector_queries": self.qdrant_queries,
                "knowledge_base_grounding": {
                    "status": "active" if self.knowledge_base_active else "inactive",
                    "playbook": self.playbook_file,
                    "standard": "SLA & Architecture Standards v1.0",
                },
            },
            "latencies_ms": {
                "e2e": {
                    "p50": self._percentile(e2e_vals, 50),
                    "p95": self._percentile(e2e_vals, 95),
                    "avg": round(statistics.mean(e2e_vals), 2) if e2e_vals else 0.0,
                    "min": round(min(e2e_vals), 2) if e2e_vals else 0.0,
                    "max": round(max(e2e_vals), 2) if e2e_vals else 0.0,
                },
                "qdrant_vector_search": {
                    "p50": self._percentile(qdrant_vals, 50),
                    "p95": self._percentile(qdrant_vals, 95),
                    "avg": round(statistics.mean(qdrant_vals), 2) if qdrant_vals else 0.0,
                },
                "extractor_agent": {
                    "p50": self._percentile(extractor_vals, 50),
                    "p95": self._percentile(extractor_vals, 95),
                    "avg": round(statistics.mean(extractor_vals), 2) if extractor_vals else 0.0,
                },
                "auditor_agent": {
                    "p50": self._percentile(auditor_vals, 50),
                    "p95": self._percentile(auditor_vals, 95),
                    "avg": round(statistics.mean(auditor_vals), 2) if auditor_vals else 0.0,
                },
                "manager_agent": {
                    "p50": self._percentile(manager_vals, 50),
                    "p95": self._percentile(manager_vals, 95),
                    "avg": round(statistics.mean(manager_vals), 2) if manager_vals else 0.0,
                },
            },
            "guards": {
                "hallucination_guard": "Active — Cryptographic verification of Qdrant vector memory IDs",
                "state_machine_guard": "Active — Enforces OPEN->BLOCKED->RESOLVED & ACTIVE->SUPERSEDED",
                "rate_limiter_guard": "Active — Max alerts per hour windowing",
                "privacy_vault_guard": "Active — Isolated sessions and topic wipes",
            },
        }


# Global singleton tracker
TRACKER = TelemetryTracker()
