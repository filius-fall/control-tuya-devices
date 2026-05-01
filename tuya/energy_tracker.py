"""Persistent tracking for Tuya's daily-reset energy meters."""

from dataclasses import dataclass
from datetime import datetime, timezone
import threading

from . import state_db

KWH_TO_JOULES = 3_600_000.0
_RESET_EPSILON_KWH = 1e-9


@dataclass(frozen=True)
class DeviceEnergyState:
    device_id: str
    total_joules: float = 0.0
    last_raw_kwh: float | None = None
    reset_count: int = 0
    updated_at: str | None = None


def _timestamp(observed_at: datetime | None = None) -> str:
    ts = observed_at or datetime.now(timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


def apply_energy_reading(
    device_id: str,
    state: DeviceEnergyState | None,
    current_kwh: float,
    *,
    observed_at: datetime | None = None,
) -> DeviceEnergyState:
    """Apply a device-reported daily energy reading to persistent state.

    Tuya devices report cumulative energy for the current local day and reset at
    midnight. This function synthesizes a monotonic total by adding positive
    deltas and treating a drop as a daily reset.
    """
    if not device_id:
        raise ValueError("device_id is required")
    if current_kwh < 0:
        raise ValueError("current_kwh must be non-negative")

    previous = state or DeviceEnergyState(device_id=device_id)
    if previous.device_id != device_id:
        raise ValueError("state device_id does not match")

    total_joules = previous.total_joules
    reset_count = previous.reset_count

    if previous.last_raw_kwh is not None:
        if current_kwh + _RESET_EPSILON_KWH < previous.last_raw_kwh:
            total_joules += current_kwh * KWH_TO_JOULES
            reset_count += 1
        else:
            delta_kwh = max(current_kwh - previous.last_raw_kwh, 0.0)
            total_joules += delta_kwh * KWH_TO_JOULES

    return DeviceEnergyState(
        device_id=device_id,
        total_joules=total_joules,
        last_raw_kwh=current_kwh,
        reset_count=reset_count,
        updated_at=_timestamp(observed_at),
    )


class EnergyTracker:
    """Maintain and persist synthesized total energy per device."""

    def __init__(self):
        self._lock = threading.RLock()
        self._states = self._load_states()

    def _load_states(self) -> dict[str, DeviceEnergyState]:
        conn = state_db.connect()
        try:
            rows = conn.execute(
                """
                SELECT device_id, total_joules, last_raw_kwh, reset_count, updated_at
                FROM device_energy
                """
            ).fetchall()
        finally:
            conn.close()

        return {
            device_id: DeviceEnergyState(
                device_id=device_id,
                total_joules=float(total_joules or 0.0),
                last_raw_kwh=(None if last_raw_kwh is None else float(last_raw_kwh)),
                reset_count=int(reset_count or 0),
                updated_at=updated_at,
            )
            for device_id, total_joules, last_raw_kwh, reset_count, updated_at in rows
        }

    def snapshot(self) -> dict[str, DeviceEnergyState]:
        """Return an immutable snapshot of all device energy states."""
        with self._lock:
            return dict(self._states)

    def update(self, device_id: str, current_kwh: float) -> DeviceEnergyState:
        """Update and persist state for a single device."""
        with self._lock:
            next_state = apply_energy_reading(
                device_id, self._states.get(device_id), current_kwh
            )
            conn = state_db.connect()
            try:
                conn.execute(
                    """
                    INSERT INTO device_energy (
                        device_id,
                        total_joules,
                        last_raw_kwh,
                        reset_count,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        total_joules=excluded.total_joules,
                        last_raw_kwh=excluded.last_raw_kwh,
                        reset_count=excluded.reset_count,
                        updated_at=excluded.updated_at
                    """,
                    (
                        next_state.device_id,
                        next_state.total_joules,
                        next_state.last_raw_kwh,
                        next_state.reset_count,
                        next_state.updated_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            self._states[device_id] = next_state
            return next_state
