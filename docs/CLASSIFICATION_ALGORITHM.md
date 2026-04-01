# v4.5 Rate-Matching Passenger Classification Algorithm

> **Version**: v4.5 (2026-04-01)
> **Files**: `src/analysis/worker_state_classifier.py`, `src/analysis/worker_classifier_v4.py`
> **Purpose**: Classify construction hoist passengers using barometric pressure rate matching

---

## 1. Problem Definition

### Goal
Determine whether a T-Ward (worker tag) **actually boarded** a specific hoist.

### Challenges
- **Waiting workers**: Many workers wait near the hoist without boarding (high RSSI does not mean boarding)
- **RSSI noise**: BLE signal strength is very noisy (walls, human bodies, reflections)
- **10-second sampling**: Sensor data at 10s intervals -- insufficient data points for short trips
- **Multiple hoists**: Same building may have multiple hoists -- need to disambiguate

### Key Insight (v4.5)
**RSSI alone is insufficient.** The v4.5 algorithm uses **barometric pressure rate matching** as the primary evidence.
Workers riding the same elevator experience the same pressure change rate (dp/dt).
RSSI is used only for candidate selection, not for scoring.

---

## 2. Algorithm: Sequential Filter

```
Step 1: RSSI Candidate Selection (-75 dBm)
  - Worker T-Ward detected by hoist mov_gw (moving gateway) with RSSI >= -75 dBm
  - This only confirms "was near the hoist" -- NOT used in scoring

Step 2: Altitude Change Check (>= 0.3 hPa)
  - Worker's barometer must show meaningful vertical movement during the trip window
  - 0.3 hPa approximately equals 2.5 meters (one floor)

Step 3: Multi-scale Rate Matching (dp/dt comparison)
  - Compare worker's pressure change rate with hoist's pressure change rate
  - Windows: 10s, 30s, 60s (multi-scale for robustness against BLE gaps)
  - BLE communication gaps (30~90s data loss) due to concrete/rebar structures
  - rate_match_score = fraction of intervals where dp/dt(worker) matches dp/dt(hoist)
  - Match criterion: |dp/dt(worker) - dp/dt(hoist)| < threshold

Step 4: Composite Scoring
  composite = rate_match * 0.65 + delta_ratio * 0.25 + direction * 0.10

  - rate_match (65%): Multi-scale pressure rate matching score
  - delta_ratio (25%): worker_delta_hpa / hoist_delta_hpa (ideal = 1.0)
  - direction (10%): Both moving same direction (up/down) bonus

Step 5: RSSI Boarding-Segment Reassignment
  - When multiple hoists in the same building operate simultaneously
  - Worker is assigned to the hoist with the strongest avg RSSI during boarding~alighting
```

---

## 3. Classification Thresholds

| Classification | Condition | Meaning |
|---------------|-----------|---------|
| **Confirmed** | composite >= 0.60 | Pressure rate matches hoist well |
| **Probable** | composite 0.45~0.60 | Classified as boarding. BLE gaps reduce confidence |

### Probable Sub-categories

| Type | Condition | Explanation |
|------|-----------|-------------|
| **Primary** | rate_match >= 0.40, composite < 0.60 | Rate matching OK, but delta_ratio or direction reduces composite below 0.60 |
| **Fallback** | rate_match < 0.40, delta_ratio 0.5~1.3, worker_delta >= 0.5 hPa | Few matching intervals due to BLE gaps (30~90s), but overall pressure change matches |

### Key Message
**Probable IS classified as boarding.** The difference from Confirmed is confidence level, not boarding status.
Probable occurs when BLE communication gaps (caused by concrete/rebar structures, 30~90 second data loss) reduce the number of comparable rate-matching intervals.

---

## 4. Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `CANDIDATE_RSSI_THRESHOLD` | -75 dBm | Candidate selection only (NOT used in scoring) |
| `MIN_ALTITUDE_CHANGE` | 0.3 hPa | Minimum vertical movement from worker barometer (~2.5m) |
| `RATE_WEIGHT` | 0.65 | Composite weight for rate matching |
| `DELTA_WEIGHT` | 0.25 | Composite weight for delta ratio |
| `DIRECTION_WEIGHT` | 0.10 | Composite weight for direction match |
| `CONFIRMED_THRESHOLD` | 0.60 | Confirmed classification cutoff |
| `PROBABLE_THRESHOLD` | 0.45 | Probable classification cutoff |
| `RESAMPLE_SEC` | 10 | Data resampling interval |
| `MAX_PASSENGERS_PER_TRIP` | 30 | Soft cap (warning, not rejection) |

---

## 5. Data Columns (v4.5 Output)

| Column | Type | Description |
|--------|------|-------------|
| `classification` | str | "confirmed" or "probable" |
| `composite_score` | float | Weighted composite (0~1) |
| `rate_match_score` | float | Fraction of intervals with dp/dt match |
| `rate_match_intervals` | int | Number of intervals where rate matched |
| `total_moving_intervals` | int | Total intervals during hoist movement |
| `delta_ratio` | float | worker_delta / hoist_delta (ideal=1.0) |
| `worker_delta_hpa` | float | Worker's total pressure change (hPa) |
| `rssi_score` | float | Legacy RSSI score (kept for compatibility) |
| `pressure_score` | float | Legacy pressure score (= rate_match_score in v4) |
| `spatial_score` | float | Always 0.0 in v4 (not used) |
| `timing_score` | float | Always 0.0 in v4 (not used) |

---

## 6. Why Rate-Matching Works

The fundamental physical principle:

```
If a worker is inside the hoist elevator:
  dp/dt(worker) == dp/dt(hoist)   (same elevator = same pressure change rate)

If a worker is waiting nearby:
  dp/dt(worker) == 0              (standing still = no pressure change)
  dp/dt(hoist) != 0               (hoist is moving)

If a worker is on stairs:
  dp/dt(worker) != dp/dt(hoist)   (different speed of vertical movement)
```

This is why RSSI is only used for candidate selection:
- High RSSI = near the hoist (could be waiting or boarding)
- Rate matching = actually moving with the hoist (definitive evidence)

---

## 7. 5-Day Results (Y1 Site)

| Date | Total | Confirmed | Probable | Max/trip | Avg/trip |
|------|-------|-----------|----------|----------|----------|
| 03/23 | 3,460 | 1,997 | 1,463 | 31 | 5.0 |
| 03/24 | 3,658 | 2,077 | 1,581 | 34 | 4.8 |
| 03/25 | 4,451 | 2,543 | 1,908 | 53 | 5.1 |
| 03/26 | 4,330 | 2,472 | 1,858 | 38 | 5.0 |
| 03/27 | 4,581 | 2,749 | 1,832 | 55 | 5.1 |

---

## 8. Evolution History

| Version | Approach | Key Change |
|---------|----------|------------|
| v1 | RSSI cross-correlation | Binary yes/no per worker-trip pair |
| v2 | Multi-evidence (RSSI+pressure+spatial+timing) | 4 weighted scores |
| v3 | Trip-centric threshold | Better thresholds, but still RSSI-dependent |
| v4.4 | Worker-centric Rate-Matching | dp/dt comparison, RSSI for candidates only |
| **v4.5** | **+ Multi-scale windows + RSSI reassignment** | **10s/30s/60s windows for BLE gap robustness, boarding-segment RSSI reassignment** |

---

*Last updated: 2026-04-01 (v4.5)*
