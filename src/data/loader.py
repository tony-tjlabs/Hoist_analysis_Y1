"""Data loaders for Hoist Analysis (Cloud Release - Static data from cache meta)"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from .schema import HoistInfo

logger = logging.getLogger(__name__)

# Static data embedded for cloud deployment (extracted from 20260326 data)
# This avoids the need to include CSV files

_HOIST_INFO = {
    "CUB_Hoist_1": HoistInfo(hoist_name="CUB_Hoist_1", building_name="CUB", fix_gateway_no=113, mov_gateway_no=112),
    "CUB_Hoist_2": HoistInfo(hoist_name="CUB_Hoist_2", building_name="CUB", fix_gateway_no=115, mov_gateway_no=114),
    "CUB_Hoist_3": HoistInfo(hoist_name="CUB_Hoist_3", building_name="CUB", fix_gateway_no=117, mov_gateway_no=116),
    "FAB_Hoist_1": HoistInfo(hoist_name="FAB_Hoist_1", building_name="FAB", fix_gateway_no=103, mov_gateway_no=102),
    "FAB_Hoist_2": HoistInfo(hoist_name="FAB_Hoist_2", building_name="FAB", fix_gateway_no=105, mov_gateway_no=104),
    "FAB_Hoist_3": HoistInfo(hoist_name="FAB_Hoist_3", building_name="FAB", fix_gateway_no=107, mov_gateway_no=106),
    "WWT_Hoist_1": HoistInfo(hoist_name="WWT_Hoist_1", building_name="WWT", fix_gateway_no=109, mov_gateway_no=108),
    "WWT_Hoist_2": HoistInfo(hoist_name="WWT_Hoist_2", building_name="WWT", fix_gateway_no=111, mov_gateway_no=110),
    "WWT_Hoist_3": HoistInfo(hoist_name="WWT_Hoist_3", building_name="WWT", fix_gateway_no=101, mov_gateway_no=100),
}

_FLOOR_ELEVATIONS = {
    "CUB": {
        "1F": 0.0, "2F": 5.5, "3F": 9.5, "4F": 13.8, "5F": 18.0,
        "6F": 22.3, "7F": 26.5, "Roof": 30.8
    },
    "FAB": {
        "B1": -6.0, "1F": 0.0, "2F": 5.8, "3F": 11.5, "4F": 17.3,
        "5F": 23.0, "6F": 28.8, "7F": 34.5, "8F": 40.3, "9F": 46.0,
        "10F": 51.8, "Roof": 57.5
    },
    "WWT": {
        "B1": -5.0, "1F": 0.0, "2F": 4.5, "3F": 9.0, "Roof": 13.5
    }
}


def load_hoist_info(date_str: Optional[str] = None, **kwargs) -> Dict[str, HoistInfo]:
    """
    Load hoist-gateway mapping (static data)

    Args:
        date_str: Ignored in cloud mode

    Returns:
        Dict keyed by hoist_name
    """
    logger.info(f"Loaded {len(_HOIST_INFO)} hoist configurations (embedded)")
    return _HOIST_INFO.copy()


def load_floor_elevation(date_str: Optional[str] = None, **kwargs) -> Dict[str, Dict[str, float]]:
    """
    Load floor elevations (static data)

    Args:
        date_str: Ignored in cloud mode

    Returns:
        Nested dict: building -> floor -> elevation (meters)
    """
    logger.info(f"Loaded elevations for {len(_FLOOR_ELEVATIONS)} buildings (embedded)")
    return {k: dict(v) for k, v in _FLOOR_ELEVATIONS.items()}


def get_gateway_to_hoist_map(hoist_info: Dict[str, HoistInfo]) -> Dict[int, str]:
    """
    Create reverse mapping from mov_gateway_no to hoist_name

    Returns:
        Dict: gateway_no -> hoist_name
    """
    return {
        hoist.mov_gateway_no: hoist.hoist_name
        for hoist in hoist_info.values()
    }


def get_building_hoists(hoist_info: Dict[str, HoistInfo]) -> Dict[str, list]:
    """
    Group hoists by building

    Returns:
        Dict: building_name -> list of hoist_names
    """
    buildings = {}
    for hoist in hoist_info.values():
        if hoist.building_name not in buildings:
            buildings[hoist.building_name] = []
        buildings[hoist.building_name].append(hoist.hoist_name)
    return buildings
