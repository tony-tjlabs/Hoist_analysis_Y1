"""Data loaders for Hoist Analysis"""

import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Generator
import logging

from .schema import HoistInfo, FloorElevation
from ..utils.config import SAMPLE_DATA_DIR, DEFAULT_DATE, get_data_dir

logger = logging.getLogger(__name__)


def load_sward_data(
    date_str: Optional[str] = None,
    file_path: Optional[Path] = None
) -> pd.DataFrame:
    """
    Load S-Ward sensor data from CSV

    Args:
        date_str: Date string (YYYYMMDD). Uses default if None.
        file_path: Path to CSV file. Uses date_str based path if None.

    Returns:
        DataFrame with parsed datetime and cleaned columns
    """
    if file_path is None:
        date_str = date_str or DEFAULT_DATE
        data_dir = get_data_dir(date_str)
        file_path = data_dir / f"Y1_Hoist_SWardData_{date_str}.csv"

    logger.info(f"Loading S-Ward data from {file_path}")

    df = pd.read_csv(file_path)

    # Parse datetime (format: "2026-03-26 00:00:00.143 +0900")
    df["insert_datetime"] = pd.to_datetime(
        df["insert_datetime"].str.replace(r" [+-]\d{4}$", "", regex=True)
    )

    # Rename columns for consistency
    df = df.rename(columns={
        "is_movied": "is_moving",
        "batt_value": "battery"
    })

    # Sort by datetime
    df = df.sort_values("insert_datetime").reset_index(drop=True)

    logger.info(f"Loaded {len(df):,} S-Ward records")
    return df


def load_device_data(
    date_str: Optional[str] = None,
    file_path: Optional[Path] = None,
    chunk_size: int = 500000,
    tward_only: bool = False
) -> pd.DataFrame:
    """
    Load device detection data from CSV (CP949 encoding)

    Args:
        date_str: Date string (YYYYMMDD). Uses default if None.
        file_path: Path to CSV file. Uses date_str based path if None.
        chunk_size: Rows to process per chunk (memory optimization)
        tward_only: If True, only load T-Ward records (type=41)

    Returns:
        DataFrame with device records
    """
    if file_path is None:
        date_str = date_str or DEFAULT_DATE
        data_dir = get_data_dir(date_str)
        file_path = data_dir / f"Y1_Hoist_DeviceData_{date_str}.csv"

    logger.info(f"Loading device data from {file_path}")

    # Define columns to load (skip unnecessary ones for memory)
    usecols = [
        "insert_datetime", "gateway_no", "user_no", "user_name",
        "company_name", "mac_address", "rssi", "type", "pressure"
    ]

    # Read in chunks for memory efficiency
    chunks = []
    total_rows = 0

    for chunk in pd.read_csv(
        file_path,
        encoding="cp949",
        usecols=usecols,
        chunksize=chunk_size,
        low_memory=False
    ):
        # Filter T-Ward only if requested
        if tward_only:
            chunk = chunk[chunk["type"] == 41]

        # Parse datetime
        chunk["insert_datetime"] = pd.to_datetime(
            chunk["insert_datetime"].str.replace(r" [+-]\d{4}$", "", regex=True)
        )

        chunks.append(chunk)
        total_rows += len(chunk)

        if total_rows % 1000000 == 0:
            logger.info(f"Processed {total_rows:,} rows...")

    df = pd.concat(chunks, ignore_index=True)

    # Rename type column
    df = df.rename(columns={"type": "device_type"})

    # Convert pressure to numeric (may have empty values)
    df["pressure"] = pd.to_numeric(df["pressure"], errors="coerce")

    # Sort by datetime
    df = df.sort_values("insert_datetime").reset_index(drop=True)

    logger.info(f"Loaded {len(df):,} device records")
    return df


def load_device_data_chunked(
    date_str: Optional[str] = None,
    file_path: Optional[Path] = None,
    chunk_size: int = 500000
) -> Generator[pd.DataFrame, None, None]:
    """
    Generator to load device data in chunks (for memory-constrained environments)

    Args:
        date_str: Date string (YYYYMMDD). Uses default if None.

    Yields:
        DataFrame chunks
    """
    if file_path is None:
        date_str = date_str or DEFAULT_DATE
        data_dir = get_data_dir(date_str)
        file_path = data_dir / f"Y1_Hoist_DeviceData_{date_str}.csv"

    usecols = [
        "insert_datetime", "gateway_no", "user_no", "user_name",
        "company_name", "mac_address", "rssi", "type", "pressure"
    ]

    for chunk in pd.read_csv(
        file_path,
        encoding="cp949",
        usecols=usecols,
        chunksize=chunk_size,
        low_memory=False
    ):
        chunk["insert_datetime"] = pd.to_datetime(
            chunk["insert_datetime"].str.replace(r" [+-]\d{4}$", "", regex=True)
        )
        chunk = chunk.rename(columns={"type": "device_type"})
        chunk["pressure"] = pd.to_numeric(chunk["pressure"], errors="coerce")
        yield chunk


def load_hoist_info(
    date_str: Optional[str] = None,
    file_path: Optional[Path] = None
) -> Dict[str, HoistInfo]:
    """
    Load hoist-gateway mapping

    Args:
        date_str: Date string (YYYYMMDD). Uses default if None.

    Returns:
        Dict keyed by hoist_name
    """
    if file_path is None:
        date_str = date_str or DEFAULT_DATE
        data_dir = get_data_dir(date_str)
        file_path = data_dir / f"Y1_Hoist_SWardInfo_{date_str}.csv"
        # Fallback: 현장 구조 설정은 data/config/ 에서 검색
        if not file_path.exists():
            from ..utils.config import CONFIG_DIR
            candidates = sorted(CONFIG_DIR.glob("Y1_Hoist_SWardInfo_*.csv"))
            if candidates:
                file_path = candidates[-1]

    logger.info(f"Loading hoist info from {file_path}")

    df = pd.read_csv(file_path)

    hoists = {}
    for _, row in df.iterrows():
        hoist = HoistInfo(
            hoist_name=row["hoist_name"],
            building_name=row["building_name"],
            fix_gateway_no=int(row["fix_gateway_no"]),
            mov_gateway_no=int(row["mov_gateway_no"])
        )
        hoists[hoist.hoist_name] = hoist

    logger.info(f"Loaded {len(hoists)} hoist configurations")
    return hoists


def load_floor_elevation(
    date_str: Optional[str] = None,
    file_path: Optional[Path] = None
) -> Dict[str, Dict[str, float]]:
    """
    Load floor elevations

    Args:
        date_str: Date string (YYYYMMDD). Uses default if None.

    Returns:
        Nested dict: building -> floor -> elevation (meters)
    """
    if file_path is None:
        date_str = date_str or DEFAULT_DATE
        data_dir = get_data_dir(date_str)
        file_path = data_dir / f"Y1_Building_FloorElevation_{date_str}.csv"
        # Fallback: 건물 구조는 data/config/ 에서 검색
        if not file_path.exists():
            from ..utils.config import CONFIG_DIR
            candidates = sorted(CONFIG_DIR.glob("Y1_Building_FloorElevation_*.csv"))
            if candidates:
                file_path = candidates[-1]

    logger.info(f"Loading floor elevations from {file_path}")

    df = pd.read_csv(file_path)

    elevations = {}
    for _, row in df.iterrows():
        building = row["building_name"]
        floor = row["floor_name"]
        elevation = float(row["elevation"])

        if building not in elevations:
            elevations[building] = {}
        elevations[building][floor] = elevation

    # Sort floors by elevation
    for building in elevations:
        elevations[building] = dict(
            sorted(elevations[building].items(), key=lambda x: x[1])
        )

    logger.info(f"Loaded elevations for {len(elevations)} buildings")
    return elevations


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
