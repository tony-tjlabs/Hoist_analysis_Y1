"""Floor estimation from pressure difference"""

import logging
from typing import Dict, Optional, List, Tuple

import numpy as np

from ..utils.config import PRESSURE_PER_METER, TEMP_COEFFICIENT

logger = logging.getLogger(__name__)


class FloorEstimator:
    """Estimate floor from pressure difference between fix and mov gateways"""

    def __init__(
        self,
        floor_elevations: Dict[str, Dict[str, float]],
        pressure_per_meter: float = PRESSURE_PER_METER,
        temp_coefficient: float = TEMP_COEFFICIENT
    ):
        """
        Initialize floor estimator

        Args:
            floor_elevations: Nested dict - building -> floor -> elevation (meters)
            pressure_per_meter: hPa change per meter (default 0.12 at sea level)
            temp_coefficient: Temperature correction factor
        """
        self.floor_elevations = floor_elevations
        self.pressure_per_meter = pressure_per_meter
        self.temp_coefficient = temp_coefficient

        # Pre-compute sorted floor lists for each building
        self._floor_lists = {}
        for building, floors in floor_elevations.items():
            sorted_floors = sorted(floors.items(), key=lambda x: x[1])
            self._floor_lists[building] = sorted_floors

    def estimate_altitude(
        self,
        delta_pressure: float,
        temperature: float = 15.0
    ) -> float:
        """
        Convert pressure difference to altitude

        Formula: h = (ΔP / P_per_m) * (1 + k * T)

        Args:
            delta_pressure: Pressure difference (fix - mov) in hPa
            temperature: Air temperature in Celsius

        Returns:
            Estimated altitude in meters
        """
        # Temperature correction (air density changes with temperature)
        temp_factor = 1 + self.temp_coefficient * temperature

        # Convert pressure to altitude
        altitude = (delta_pressure / self.pressure_per_meter) * temp_factor

        return altitude

    def map_to_floor(
        self,
        altitude: float,
        building: str,
        tolerance: float = 3.0
    ) -> str:
        """
        Map altitude to nearest floor

        Args:
            altitude: Estimated altitude in meters
            building: Building name
            tolerance: Maximum distance to accept (meters)

        Returns:
            Floor name (e.g., "1F", "5F", "Roof")
        """
        if building not in self._floor_lists:
            logger.warning(f"Unknown building: {building}")
            return "1F"

        floor_list = self._floor_lists[building]

        # Find closest floor
        min_dist = float("inf")
        closest_floor = "1F"

        for floor_name, elevation in floor_list:
            dist = abs(altitude - elevation)
            if dist < min_dist:
                min_dist = dist
                closest_floor = floor_name

        # Warn if too far from any floor
        if min_dist > tolerance:
            logger.debug(
                f"Altitude {altitude:.1f}m is {min_dist:.1f}m from "
                f"nearest floor {closest_floor} in {building}"
            )

        return closest_floor

    def estimate_floor_from_sensors(
        self,
        fix_pressure: float,
        mov_pressure: float,
        temperature: float,
        building: str
    ) -> str:
        """
        Combined estimation from fix and mov gateway pressures

        Args:
            fix_pressure: Fix gateway (ground) pressure in hPa
            mov_pressure: Mov gateway (hoist) pressure in hPa
            temperature: Temperature in Celsius
            building: Building name

        Returns:
            Estimated floor name
        """
        delta_pressure = fix_pressure - mov_pressure
        altitude = self.estimate_altitude(delta_pressure, temperature)
        floor = self.map_to_floor(altitude, building)

        return floor

    def get_elevation(self, building: str, floor: str) -> Optional[float]:
        """Get elevation for a floor in a building"""
        if building not in self.floor_elevations:
            return None
        return self.floor_elevations[building].get(floor)

    def get_floor_order(self, building: str) -> List[str]:
        """Get floors in elevation order (low to high)"""
        if building not in self._floor_lists:
            return []
        return [floor for floor, _ in self._floor_lists[building]]

    def get_floor_range(self, building: str) -> Tuple[str, str]:
        """Get lowest and highest floors for a building"""
        floors = self.get_floor_order(building)
        if not floors:
            return ("1F", "1F")
        return (floors[0], floors[-1])

    def altitude_to_pressure_diff(
        self,
        altitude: float,
        temperature: float = 15.0
    ) -> float:
        """
        Inverse calculation: altitude to pressure difference

        Args:
            altitude: Target altitude in meters
            temperature: Air temperature in Celsius

        Returns:
            Expected pressure difference (fix - mov) in hPa
        """
        temp_factor = 1 + self.temp_coefficient * temperature
        delta_pressure = (altitude * self.pressure_per_meter) / temp_factor
        return delta_pressure

    def calibrate_from_known_floor(
        self,
        known_floor: str,
        building: str,
        measured_delta_p: float,
        temperature: float = 15.0
    ) -> float:
        """
        Calibrate pressure_per_meter from a known floor measurement

        Args:
            known_floor: Floor name with known elevation
            building: Building name
            measured_delta_p: Measured pressure difference
            temperature: Temperature at measurement

        Returns:
            Calibrated pressure_per_meter value
        """
        known_elevation = self.get_elevation(building, known_floor)
        if known_elevation is None or known_elevation == 0:
            return self.pressure_per_meter

        temp_factor = 1 + self.temp_coefficient * temperature
        calibrated = (measured_delta_p * temp_factor) / known_elevation

        logger.info(
            f"Calibrated pressure_per_meter: {self.pressure_per_meter:.4f} -> "
            f"{calibrated:.4f} based on {known_floor} in {building}"
        )

        return calibrated
