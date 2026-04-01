"""Parquet-based cache management"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd

from ..utils.config import CACHE_DIR, CACHE_VERSION

logger = logging.getLogger(__name__)


class CacheManager:
    """Manage Parquet caches for processed data"""

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

    def _save_meta(self) -> None:
        """Save cache metadata"""
        with open(self._meta_file, "w") as f:
            json.dump(self._meta, f, indent=2, default=str)

    def _get_cache_path(self, date_str: str, cache_type: str) -> Path:
        """Get path for cache file"""
        return self.cache_dir / f"{date_str}_{cache_type}.parquet"

    def _update_meta(self, date_str: str, cache_type: str, rows: int) -> None:
        """Update metadata for cache entry"""
        key = f"{date_str}_{cache_type}"
        self._meta["entries"][key] = {
            "created_at": datetime.now().isoformat(),
            "rows": rows,
            "version": CACHE_VERSION
        }
        self._save_meta()

    # ========== Trips Cache ==========

    def save_trips(self, trips_df: pd.DataFrame, date_str: str) -> None:
        """Save trips DataFrame to Parquet"""
        path = self._get_cache_path(date_str, "trips")
        trips_df.to_parquet(path, index=False)
        self._update_meta(date_str, "trips", len(trips_df))
        logger.info(f"Saved {len(trips_df)} trips to {path}")

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

    def save_passengers(self, passengers_df: pd.DataFrame, date_str: str) -> None:
        """Save passenger classifications to Parquet"""
        path = self._get_cache_path(date_str, "passengers")
        passengers_df.to_parquet(path, index=False)
        self._update_meta(date_str, "passengers", len(passengers_df))
        logger.info(f"Saved {len(passengers_df)} passengers to {path}")

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

    # ========== Floor Stats Cache ==========

    def save_floor_stats(self, stats_df: pd.DataFrame, date_str: str) -> None:
        """Save floor statistics to Parquet"""
        path = self._get_cache_path(date_str, "floor_stats")
        stats_df.to_parquet(path, index=False)
        self._update_meta(date_str, "floor_stats", len(stats_df))
        logger.info(f"Saved floor stats to {path}")

    def load_floor_stats(self, date_str: str) -> Optional[pd.DataFrame]:
        """Load floor stats from cache"""
        path = self._get_cache_path(date_str, "floor_stats")
        if not path.exists():
            return None
        return pd.read_parquet(path)

    # ========== S-Ward Cache ==========

    def save_sward(self, sward_df: pd.DataFrame, date_str: str) -> None:
        """Save preprocessed S-Ward data to Parquet"""
        path = self._get_cache_path(date_str, "sward")
        sward_df.to_parquet(path, index=False)
        self._update_meta(date_str, "sward", len(sward_df))
        logger.info(f"Saved {len(sward_df)} S-Ward records to {path}")

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

    def save_tward(self, tward_df: pd.DataFrame, date_str: str) -> None:
        """Save T-Ward device data to Parquet"""
        path = self._get_cache_path(date_str, "tward")
        tward_df.to_parquet(path, index=False)
        self._update_meta(date_str, "tward", len(tward_df))
        logger.info(f"Saved {len(tward_df)} T-Ward records to {path}")

    def load_tward(self, date_str: str) -> Optional[pd.DataFrame]:
        """Load T-Ward data from cache

        Tries to load slim version first (tward_slim), falls back to full tward.
        Slim version contains only: insert_datetime, gateway_no, mac_address, rssi
        """
        # 1. Try slim version first (smaller, faster for deployment)
        slim_path = self._get_cache_path(date_str, "tward_slim")
        if slim_path.exists():
            df = pd.read_parquet(slim_path)
            if "insert_datetime" in df.columns:
                df["insert_datetime"] = pd.to_datetime(df["insert_datetime"])
            logger.info(f"Loaded {len(df)} T-Ward records from slim cache")
            return df

        # 2. Fall back to full version
        path = self._get_cache_path(date_str, "tward")
        if not path.exists():
            return None

        df = pd.read_parquet(path)
        if "insert_datetime" in df.columns:
            df["insert_datetime"] = pd.to_datetime(df["insert_datetime"])
        return df

    # ========== Utility Methods ==========

    def is_valid_cache(self, date_str: str, cache_type: str) -> bool:
        """Check if cache exists and is valid version"""
        key = f"{date_str}_{cache_type}"
        if key not in self._meta.get("entries", {}):
            return False

        entry = self._meta["entries"][key]
        if entry.get("version") != CACHE_VERSION:
            return False

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

    def clear_cache(self, date_str: Optional[str] = None) -> None:
        """Clear cache for specific date or all"""
        if date_str:
            # Clear specific date
            for cache_type in ["trips", "passengers", "floor_stats", "sward", "tward"]:
                path = self._get_cache_path(date_str, cache_type)
                if path.exists():
                    path.unlink()
                    logger.info(f"Cleared cache: {path}")

                key = f"{date_str}_{cache_type}"
                if key in self._meta.get("entries", {}):
                    del self._meta["entries"][key]
        else:
            # Clear all
            for path in self.cache_dir.glob("*.parquet"):
                path.unlink()
                logger.info(f"Cleared cache: {path}")
            self._meta["entries"] = {}

        self._save_meta()
