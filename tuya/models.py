from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, TypedDict


class TuyaCredentials(TypedDict):
    api_key: str
    api_secret: str
    api_region: str


class DpsMeta(TypedDict, total=False):
    code: str
    type: str
    values: str


@dataclass
class DeviceConfig:
    id: str
    name: str
    local_key: str
    ip_address: str
    version: str
    model: str
    product_name: str
    category: str
    mac: str
    dps_mapping: Dict[str, DpsMeta] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeviceConfig:
        mapping = data.get("dps_mapping") or {}
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            local_key=data.get("local_key", data.get("key", "")),
            ip_address=data.get("ip_address", data.get("ip", "")),
            version=str(data.get("version", "3.3")),
            model=data.get("model", ""),
            product_name=data.get("product_name", ""),
            category=data.get("category", ""),
            mac=data.get("mac", ""),
            dps_mapping={k: DpsMeta(**v) for k, v in mapping.items()} if isinstance(mapping, dict) else {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "local_key": self.local_key,
            "ip_address": self.ip_address,
            "version": self.version,
            "model": self.model,
            "product_name": self.product_name,
            "category": self.category,
            "mac": self.mac,
            "dps_mapping": self.dps_mapping,
        }


@dataclass
class PowerReading:
    device_name: str
    device_id: str
    ip: str
    online: bool
    timestamp: str
    voltage_v: Optional[float] = None
    current_ma: Optional[float] = None
    power_w: Optional[float] = None
    energy_wh: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "timestamp": self.timestamp,
            "device_name": self.device_name,
            "device_id": self.device_id,
            "ip": self.ip,
            "status": "online" if self.online else "offline",
            "voltage_v": self.voltage_v,
            "current_ma": self.current_ma,
            "power_w": self.power_w,
            "energy_wh": self.energy_wh,
        }
        d.update(self.extra)
        return d


class PowerLostEvent(TypedDict):
    event: str
    device_name: str
    device_id: str
    ip: str
    last_seen_online: Optional[str]


class PowerRestoredEvent(TypedDict):
    event: str
    device_name: str
    device_id: str
    ip: str
    offline_since: Optional[str]
    outage_duration_seconds: Optional[float]


@dataclass
class DeviceStatus:
    online: Optional[bool] = None
    last_online: Optional[str] = None
    last_offline: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "online": self.online,
            "last_online": self.last_online,
            "last_offline": self.last_offline,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeviceStatus:
        return cls(
            online=data.get("online"),
            last_online=data.get("last_online"),
            last_offline=data.get("last_offline"),
        )


@dataclass
class PollResult:
    reading: PowerReading
    event: Optional[Dict[str, Any]] = None


__all__ = [
    "TuyaCredentials",
    "DpsMeta",
    "DeviceConfig",
    "PowerReading",
    "PowerLostEvent",
    "PowerRestoredEvent",
    "DeviceStatus",
    "PollResult",
]
