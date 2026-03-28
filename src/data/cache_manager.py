"""Parquet-based cache management (Cloud Release - Load Only)"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd

from ..utils.config import CACHE_DIR, CACHE_VERSION

logger = logging.getLogger(__name__)


class CacheManager:
    """Manage Parquet caches for processed data (Load Only)"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._meta_file = self.cache_dir / "cache_meta.json"
        self._meta = self._load_meta()

    def _load_meta(self) -> Dict[str, Any]:
        """Load cache metadata"""
        if self._meta_file.exists():
            with open(self._meta_file, "r") as f:
                return json.load(f)
        return {"version": CACHE_VERSION, "entries": {}}

    def _get_cache_path(self, date_str: str, cache_type: str) -> Path:
        """Get path for cache file"""
        return self.cache_dir / f"{date_str}_{cache_type}.parquet"

    # ========== Trips Cache ==========

    def load_trips(self, date_str: str) -> Optional[pd.DataFrame]:
        """Load trips from cache"""
        path = self._get_cache_path(date_str, "trips")
        if not path.exists():
            return None

        df = pd.read_parquet(path)
        # Convert datetime columns
        for col in ["start_time", "end_time"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

        logger.info(f"Loaded {len(df)} trips from cache")
        return df

    # ========== Passengers Cache ==========

    def load_passengers(self, date_str: str) -> Optional[pd.DataFrame]:
        """Load passengers from cache"""
        path = self._get_cache_path(date_str, "passengers")
        if not path.exists():
            return None

        df = pd.read_parquet(path)
        # Convert datetime columns
        for col in ["boarding_time", "alighting_time"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

        logger.info(f"Loaded {len(df)} passengers from cache")
        return df

    # ========== S-Ward Cache ==========

    def load_sward(self, date_str: str) -> Optional[pd.DataFrame]:
        """Load S-Ward data from cache"""
        path = self._get_cache_path(date_str, "sward")
        if not path.exists():
            return None

        df = pd.read_parquet(path)
        if "insert_datetime" in df.columns:
            df["insert_datetime"] = pd.to_datetime(df["insert_datetime"])
        return df

    # ========== T-Ward Device Cache ==========

    def load_tward(self, date_str: str) -> Optional[pd.DataFrame]:
        """Load T-Ward data from cache"""
        path = self._get_cache_path(date_str, "tward")
        if not path.exists():
            return None

        df = pd.read_parquet(path)
        if "insert_datetime" in df.columns:
            df["insert_datetime"] = pd.to_datetime(df["insert_datetime"])
        return df

    # ========== Utility Methods ==========

    def is_valid_cache(self, date_str: str, cache_type: str) -> bool:
        """Check if cache exists"""
        path = self._get_cache_path(date_str, cache_type)
        return path.exists()

    def get_cache_status(self) -> Dict[str, Any]:
        """Get status of all caches"""
        status = {
            "version": self._meta.get("version"),
            "entries": {}
        }

        for key, entry in self._meta.get("entries", {}).items():
            date_str, cache_type = key.rsplit("_", 1)
            path = self._get_cache_path(date_str, cache_type)

            status["entries"][key] = {
                "exists": path.exists(),
                "rows": entry.get("rows", 0),
                "created_at": entry.get("created_at"),
                "size_mb": path.stat().st_size / 1024 / 1024 if path.exists() else 0
            }

        return status

    # ========== Stub Methods (No-op in Cloud) ==========

    def save_trips(self, *args, **kwargs):
        """Stub: Save disabled in cloud mode"""
        pass

    def save_passengers(self, *args, **kwargs):
        """Stub: Save disabled in cloud mode"""
        pass

    def save_sward(self, *args, **kwargs):
        """Stub: Save disabled in cloud mode"""
        pass

    def save_tward(self, *args, **kwargs):
        """Stub: Save disabled in cloud mode"""
        pass

    def clear_cache(self, *args, **kwargs):
        """Stub: Clear disabled in cloud mode"""
        pass
