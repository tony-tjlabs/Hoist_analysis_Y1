"""Data schemas for Hoist Analysis"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class SWardRecord:
    """S-Ward sensor record from hoist gateway"""
    insert_datetime: datetime
    gateway_no: int
    temperature: float
    acceleration_v: float
    pressure: float
    is_movied: int  # 0=stopped, 1=moving
    item_count: int


@dataclass
class DeviceRecord:
    """BLE device detection record"""
    insert_datetime: datetime
    gateway_no: int
    user_no: Optional[str]
    user_name: Optional[str]
    company_name: Optional[str]
    mac_address: str
    rssi: int
    device_type: int  # 1=iPhone, 10=Android, 41=T-Ward
    pressure: Optional[float]  # T-Ward only (type=41)


@dataclass
class HoistInfo:
    """Hoist-gateway mapping"""
    hoist_name: str
    building_name: str
    fix_gateway_no: int
    mov_gateway_no: int


@dataclass
class FloorElevation:
    """Floor height mapping"""
    building_name: str
    floor_name: str
    elevation: float  # meters


@dataclass
class Trip:
    """Extracted trip record"""
    trip_id: int
    hoist_name: str
    building_name: str
    start_time: datetime
    end_time: datetime
    duration_sec: int
    start_floor: str
    end_floor: str
    floors_visited: List[str] = field(default_factory=list)
    direction: str = "round"  # "up", "down", "round"
    passenger_count: int = 0

    @property
    def duration_min(self) -> float:
        return self.duration_sec / 60.0


@dataclass
class PassengerClassification:
    """Passenger boarding classification"""
    classification_id: int
    trip_id: int
    user_name: str
    company_name: str
    mac_address: str
    hoist_name: str
    boarding_time: datetime
    alighting_time: Optional[datetime]
    boarding_floor: str
    alighting_floor: Optional[str]
    confidence: float  # 0.0 ~ 1.0
    method: str  # "pressure", "rssi", "hybrid"


@dataclass
class HoistMetrics:
    """Aggregated hoist metrics"""
    hoist_name: str
    building_name: str
    trip_count: int
    operating_time_min: float
    idle_time_min: float
    utilization_rate: float
    avg_passengers: float
    total_passengers: int


@dataclass
class FloorMetrics:
    """Floor-level metrics"""
    building_name: str
    floor_name: str
    stop_count: int
    total_stop_duration_min: float
    boarding_count: int
    alighting_count: int
