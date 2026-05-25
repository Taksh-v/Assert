"""
RunLedger — Unified run lifecycle interface for all background job models.

Every long-running operation (connector sync, reasoning, DLQ retry, memory
reflection) shares the same fundamental state machine:

    QUEUED → RUNNING → COMPLETED | COMPLETED_WITH_ERRORS | FAILED | CANCELLED
                  ↕
             SUSPENDED  (reasoning only)

This module provides:
  • RunStatus  — canonical status constants & helper sets.
  • RunLedgerMixin — lifecycle transition methods any SQLAlchemy model can adopt
                     by mixing in alongside Base.

Usage::

    class SyncRun(RunLedgerMixin, Base):
        __tablename__ = "sync_runs"
        _STATUS_MAP = {}            # uses canonical names directly
        _REVERSE_STATUS_MAP = {}
        ...

    class BackgroundTask(RunLedgerMixin, Base):
        __tablename__ = "background_tasks"
        _STATUS_MAP = {
            RunStatus.QUEUED: "pending",
            RunStatus.RUNNING: "processing",
        }
        _REVERSE_STATUS_MAP = {v: k for k, v in _STATUS_MAP.items()}
        ...
"""

from datetime import datetime
from typing import Any, Dict, Optional, Set


class InvalidRunTransitionError(RuntimeError):
    """Raised when a run model is moved through an invalid lifecycle transition."""

    pass


# ── Canonical Status Constants ──────────────────────────────────────────────

class RunStatus:
    """
    Canonical run lifecycle states shared across all run models.
    Individual models may use different string values internally
    but MUST map to these canonical states via _STATUS_MAP / _REVERSE_STATUS_MAP.
    """
    QUEUED = "queued"
    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"

    TERMINAL: Set[str] = {COMPLETED, COMPLETED_WITH_ERRORS, FAILED, CANCELLED}
    ACTIVE: Set[str] = {QUEUED, RUNNING, SUSPENDED}

    # Valid transitions: from_status -> {allowed next statuses}
    TRANSITIONS: Dict[str, Set[str]] = {
        QUEUED: {RUNNING, CANCELLED, FAILED},
        RUNNING: {COMPLETED, COMPLETED_WITH_ERRORS, FAILED, CANCELLED, SUSPENDED},
        SUSPENDED: {RUNNING, CANCELLED, FAILED},
        # Terminal states have no outgoing transitions
        COMPLETED: set(),
        COMPLETED_WITH_ERRORS: set(),
        FAILED: set(),
        CANCELLED: set(),
    }


# ── Lifecycle Mixin ─────────────────────────────────────────────────────────

class RunLedgerMixin:
    """
    Mixin providing unified run lifecycle methods.

    Models using this mixin MUST have at minimum:
        • status  (String column)
        • updated_at  (DateTime column, auto-set on update)

    Optional columns that will be set if present:
        • error / error_message  (String/Text)
        • started_at  (DateTime)
        • completed_at  (DateTime)
        • stats  (JSON)

    Subclasses override ``_STATUS_MAP`` to translate canonical RunStatus values
    into model-specific status strings (e.g. ``pending`` instead of ``queued``).
    Leave the map empty if the model already uses canonical names.
    """

    # Override in subclass: {RunStatus.X: "model_specific_value", ...}
    _STATUS_MAP: Dict[str, str] = {}
    # Override in subclass: {"model_specific_value": RunStatus.X, ...}
    _REVERSE_STATUS_MAP: Dict[str, str] = {}

    # ── Status helpers ──────────────────────────────────────────────

    def _to_model_status(self, canonical: str) -> str:
        """Translate canonical RunStatus to model-specific status string."""
        return self._STATUS_MAP.get(canonical, canonical)

    def _to_canonical_status(self, model_status: str) -> str:
        """Translate model-specific status string to canonical RunStatus."""
        return self._REVERSE_STATUS_MAP.get(model_status, model_status)

    @property
    def canonical_status(self) -> str:
        """Get canonical RunStatus regardless of model-specific vocabulary."""
        return self._to_canonical_status(self.status)

    @property
    def is_terminal(self) -> bool:
        """True if the run has reached a final state."""
        return self.canonical_status in RunStatus.TERMINAL

    @property
    def is_active(self) -> bool:
        """True if the run is still in progress (queued, running, or suspended)."""
        return self.canonical_status in RunStatus.ACTIVE

    def can_transition_to(self, canonical_status: str) -> bool:
        """Return True when the current canonical status can move to the target status."""
        current_status = self.canonical_status
        return canonical_status in RunStatus.TRANSITIONS.get(current_status, set())

    def _require_transition(self, canonical_status: str) -> None:
        current_status = self.canonical_status
        if not self.can_transition_to(canonical_status):
            allowed = sorted(RunStatus.TRANSITIONS.get(current_status, set()))
            raise InvalidRunTransitionError(
                f"Invalid run transition from {current_status} to {canonical_status}; allowed next states: {allowed}"
            )

    def _transition_to(
        self,
        canonical_status: str,
        *,
        stats: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        set_started_at: bool = False,
        set_completed_at: bool = False,
    ) -> None:
        self._require_transition(canonical_status)
        self.status = self._to_model_status(canonical_status)
        if set_started_at and hasattr(self, "started_at") and getattr(self, "started_at", None) is None:
            self.started_at = datetime.utcnow()
        if set_completed_at and hasattr(self, "completed_at"):
            self.completed_at = datetime.utcnow()
        self._set_timestamp("updated_at")
        self._set_error(error)
        if stats is not None and hasattr(self, "stats"):
            self.stats = stats

    # ── Lifecycle transitions ───────────────────────────────────────

    def _set_timestamp(self, attr: str) -> None:
        if hasattr(self, attr):
            setattr(self, attr, datetime.utcnow())

    def _set_error(self, error: Optional[str]) -> None:
        if error is None:
            return
        error_str = str(error)
        if hasattr(self, "error"):
            self.error = error_str
        elif hasattr(self, "error_message"):
            self.error_message = error_str

    def mark_started(self) -> None:
        """Transition from QUEUED → RUNNING."""
        self._transition_to(RunStatus.RUNNING, set_started_at=True)

    def mark_completed(self, stats: Optional[Dict[str, Any]] = None) -> None:
        """Transition to COMPLETED."""
        self._transition_to(RunStatus.COMPLETED, stats=stats, set_completed_at=True)

    def mark_completed_with_errors(
        self, stats: Optional[Dict[str, Any]] = None, error: Optional[str] = None
    ) -> None:
        """Transition to COMPLETED_WITH_ERRORS (partial success)."""
        self._transition_to(
            RunStatus.COMPLETED_WITH_ERRORS,
            stats=stats,
            error=error,
            set_completed_at=True,
        )

    def mark_failed(self, error: Optional[str] = None) -> None:
        """Transition to FAILED."""
        self._transition_to(RunStatus.FAILED, error=error, set_completed_at=True)

    def mark_cancelled(self) -> None:
        """Transition to CANCELLED."""
        self._transition_to(RunStatus.CANCELLED, set_completed_at=True)

    def mark_suspended(self) -> None:
        """Transition to SUSPENDED (reasoning only)."""
        self._transition_to(RunStatus.SUSPENDED)

    def heartbeat(self) -> None:
        """Update the timestamp to signal liveness without changing status."""
        if self.is_terminal:
            raise InvalidRunTransitionError(
                f"Cannot heartbeat terminal run state {self.canonical_status}"
            )
        self._set_timestamp("updated_at")

    def latest_for_subject(self, subject_id: str) -> Optional[str]:
        """
        Override in subclass to query the latest run for a given subject
        (e.g., connector_id, workspace_id). Returns the run ID or None.
        """
        raise NotImplementedError(
            "Subclass must implement latest_for_subject() for its domain."
        )
