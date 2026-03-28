"""CSS styles and color definitions (Dark Theme)"""

# ============================================================
# Dark Theme Color Palette
# ============================================================

COLORS = {
    # Background
    "background": "#0E1117",
    "surface": "#1E2330",
    "surface_elevated": "#262D3D",

    # Text
    "text_primary": "#FAFAFA",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",

    # Accent
    "primary": "#3B82F6",
    "primary_light": "#60A5FA",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",

    # Info
    "info": "#38BDF8",

    # Legacy compatibility
    "secondary": "#64748B",
}

# Building colors
BUILDING_COLORS = {
    "FAB": "#3B82F6",
    "CUB": "#22C55E",
    "WWT": "#F59E0B",
}

# Direction colors
DIRECTION_COLORS = {
    "up": "#22C55E",
    "down": "#3B82F6",
    "round": "#A855F7",
}

# Status colors
STATUS_COLORS = {
    "active": "#22C55E",
    "running": "#22C55E",
    "idle": "#64748B",
    "warning": "#F59E0B",
}

# ============================================================
# Plotly Dark Layout
# ============================================================

PLOTLY_DARK_LAYOUT = {
    "template": "plotly_dark",
    "paper_bgcolor": "#0E1117",
    "plot_bgcolor": "#1E2330",
    "font": {"color": "#FAFAFA", "family": "sans-serif"},
    "title": {"font": {"size": 16, "color": "#FAFAFA"}},
    "legend": {
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": "#94A3B8"},
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
    },
    "xaxis": {
        "gridcolor": "#2D3748",
        "linecolor": "#2D3748",
        "tickfont": {"color": "#94A3B8"},
    },
    "yaxis": {
        "gridcolor": "#2D3748",
        "linecolor": "#2D3748",
        "tickfont": {"color": "#94A3B8"},
    },
}

# ============================================================
# Custom CSS (Dark Theme)
# ============================================================

CUSTOM_CSS = """
<style>
/* ==================== Scroll Fix ==================== */
/* Prevent scroll-to-top on widget interaction */
[data-testid="stAppViewContainer"] {
    scroll-behavior: auto !important;
}
/* Hide Streamlit header to save space */
header[data-testid="stHeader"] {
    height: 0 !important;
    min-height: 0 !important;
    padding: 0 !important;
}

/* ==================== KPI Card ==================== */
.kpi-card {
    background: #1E2330;
    border-radius: 12px;
    padding: 20px;
    border: 1px solid #2D3748;
    text-align: center;
    height: 100%;
}

.kpi-card .value {
    font-size: 32px;
    font-weight: 700;
    color: #FAFAFA;
}

.kpi-card .label {
    font-size: 14px;
    color: #94A3B8;
    margin-top: 8px;
}

.kpi-card .delta {
    font-size: 12px;
    margin-top: 4px;
}

.kpi-card .delta.positive { color: #22C55E; }
.kpi-card .delta.negative { color: #EF4444; }
.kpi-card .delta.neutral { color: #64748B; }

/* ==================== Building Card ==================== */
.building-card {
    background: #1E2330;
    border-radius: 12px;
    padding: 16px;
    border-left: 4px solid var(--building-color, #64748B);
    margin-bottom: 8px;
}

.building-card.FAB { --building-color: #3B82F6; }
.building-card.CUB { --building-color: #22C55E; }
.building-card.WWT { --building-color: #F59E0B; }

.building-card .title {
    font-size: 18px;
    font-weight: 600;
    color: var(--building-color, #FAFAFA);
}

.building-card .hoist-badges {
    margin: 8px 0;
}

.building-card .stats {
    font-size: 14px;
    color: #94A3B8;
    margin-top: 8px;
}

/* ==================== Status Indicators ==================== */
.status-active, .status-running { color: #22C55E; }
.status-idle { color: #64748B; }
.status-warning { color: #F59E0B; }

/* ==================== Section Header ==================== */
.section-header {
    font-size: 18px;
    font-weight: 600;
    color: #FAFAFA;
    margin: 24px 0 16px 0;
    padding-bottom: 8px;
    border-bottom: 2px solid #2D3748;
}

/* ==================== Progress Container ==================== */
.progress-container {
    background: #1E2330;
    border-radius: 12px;
    padding: 20px;
    border: 1px solid #2D3748;
}

.progress-step {
    display: flex;
    align-items: center;
    margin: 12px 0;
    font-size: 14px;
}

.progress-step .icon {
    width: 24px;
    margin-right: 12px;
    font-size: 16px;
}

.progress-step.complete .icon { color: #22C55E; }
.progress-step.complete .name { color: #94A3B8; }

.progress-step.running .icon { color: #F59E0B; }
.progress-step.running .name { color: #FAFAFA; font-weight: 500; }

.progress-step.pending .icon { color: #64748B; }
.progress-step.pending .name { color: #64748B; }

/* ==================== Data Status Card ==================== */
.data-status-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: #1E2330;
    border-radius: 8px;
    margin-bottom: 8px;
    border: 1px solid #2D3748;
}

.data-status-card .name {
    font-weight: 500;
    color: #FAFAFA;
}

.data-status-card .info {
    font-size: 12px;
    color: #64748B;
}

.data-status-card .status {
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 4px;
}

.data-status-card .status.loaded {
    background: rgba(34, 197, 94, 0.2);
    color: #22C55E;
}

.data-status-card .status.pending {
    background: rgba(100, 116, 139, 0.2);
    color: #64748B;
}

.data-status-card .status.error {
    background: rgba(239, 68, 68, 0.2);
    color: #EF4444;
}

/* ==================== Confidence Bar ==================== */
.confidence-bar {
    display: flex;
    align-items: center;
    gap: 8px;
}

.confidence-bar .bar {
    flex: 1;
    height: 4px;
    background: #2D3748;
    border-radius: 2px;
    overflow: hidden;
}

.confidence-bar .fill {
    height: 100%;
    transition: width 0.3s ease;
}

.confidence-bar .fill.high { background: #22C55E; }
.confidence-bar .fill.medium { background: #F59E0B; }
.confidence-bar .fill.low { background: #EF4444; }

.confidence-bar .value {
    font-size: 12px;
    color: #94A3B8;
    min-width: 36px;
    text-align: right;
}

/* ==================== Trip Badge ==================== */
.trip-badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
}

.trip-badge.up {
    background: rgba(34, 197, 94, 0.2);
    color: #22C55E;
}

.trip-badge.down {
    background: rgba(59, 130, 246, 0.2);
    color: #3B82F6;
}

.trip-badge.round {
    background: rgba(168, 85, 247, 0.2);
    color: #A855F7;
}

/* ==================== Floor Badge ==================== */
.floor-badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    background: rgba(100, 116, 139, 0.2);
    color: #94A3B8;
}

/* ==================== Hoist Badge ==================== */
.hoist-badge {
    display: inline-block;
    padding: 2px 6px;
    margin: 2px;
    border-radius: 4px;
    font-size: 11px;
}

.hoist-badge.active {
    background: rgba(34, 197, 94, 0.2);
    color: #22C55E;
}

.hoist-badge.idle {
    background: rgba(100, 116, 139, 0.2);
    color: #64748B;
}

/* ==================== Empty State ==================== */
.empty-state {
    text-align: center;
    padding: 48px 24px;
    color: #64748B;
}

.empty-state .icon {
    font-size: 48px;
    margin-bottom: 16px;
}

.empty-state .message {
    font-size: 16px;
}

/* ==================== Styled Table ==================== */
.styled-table {
    border-collapse: collapse;
    width: 100%;
}

.styled-table th {
    background-color: #262D3D;
    color: #FAFAFA;
    padding: 12px;
    text-align: left;
    font-weight: 600;
}

.styled-table td {
    color: #94A3B8;
    padding: 10px 12px;
    border-bottom: 1px solid #2D3748;
}

.styled-table tr:hover {
    background-color: #262D3D;
}

/* ==================== Metric Delta ==================== */
.delta-positive { color: #22C55E; }
.delta-negative { color: #EF4444; }
.delta-neutral { color: #64748B; }

/* ==================== Evidence Bar ==================== */
.evidence-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 4px 0;
}

.evidence-bar .label {
    min-width: 60px;
    font-size: 12px;
    color: #94A3B8;
}

.evidence-bar .bar-container {
    flex: 1;
    height: 8px;
    background: #2D3748;
    border-radius: 4px;
    overflow: hidden;
}

.evidence-bar .bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s ease;
}

.evidence-bar .bar-fill.rssi { background: #3B82F6; }
.evidence-bar .bar-fill.pressure { background: #22C55E; }
.evidence-bar .bar-fill.spatial { background: #F59E0B; }
.evidence-bar .bar-fill.timing { background: #A855F7; }

.evidence-bar .value {
    min-width: 40px;
    font-size: 12px;
    color: #FAFAFA;
    text-align: right;
}

/* ==================== Classification Badge ==================== */
.classification-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
}

.classification-badge.confirmed {
    background: rgba(34, 197, 94, 0.2);
    color: #22C55E;
    border: 1px solid rgba(34, 197, 94, 0.4);
}

.classification-badge.probable {
    background: rgba(245, 158, 11, 0.2);
    color: #F59E0B;
    border: 1px solid rgba(245, 158, 11, 0.4);
}

.classification-badge.rejected {
    background: rgba(100, 116, 139, 0.2);
    color: #64748B;
    border: 1px solid rgba(100, 116, 139, 0.4);
}

/* ==================== Composite Score Ring ==================== */
.score-ring {
    display: flex;
    align-items: center;
    gap: 12px;
}

.score-ring .ring-visual {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    font-weight: 600;
    color: #FAFAFA;
}

.score-ring .ring-visual.high {
    background: conic-gradient(#22C55E var(--pct), #2D3748 0);
}

.score-ring .ring-visual.medium {
    background: conic-gradient(#F59E0B var(--pct), #2D3748 0);
}

.score-ring .ring-visual.low {
    background: conic-gradient(#EF4444 var(--pct), #2D3748 0);
}

/* ==================== Passenger Color Scale ==================== */
.pax-scale {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
}

.pax-scale .color-box {
    width: 16px;
    height: 16px;
    border-radius: 2px;
}

.pax-scale .pax-0 { background: #64748B; }
.pax-scale .pax-1-5 { background: #86EFAC; }
.pax-scale .pax-6-10 { background: #22C55E; }
.pax-scale .pax-11-15 { background: #FCD34D; }
.pax-scale .pax-16-20 { background: #F97316; }
.pax-scale .pax-21-plus { background: #EF4444; }

/* ==================== Evidence Summary Card ==================== */
.evidence-summary-card {
    background: #1E2330;
    border-radius: 12px;
    padding: 16px;
    border: 1px solid #2D3748;
}

.evidence-summary-card .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
}

.evidence-summary-card .title {
    font-size: 14px;
    font-weight: 600;
    color: #FAFAFA;
}

/* ==================== Insight Card (v4.0) ==================== */
.insight-card {
    background: #1E2330;
    border: 1px solid #2D3748;
    border-left: 3px solid #F59E0B;
    border-radius: 8px;
    padding: 16px;
    margin: 12px 0;
}

.insight-card .header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
}

.insight-card .icon {
    font-size: 18px;
}

.insight-card .title {
    font-size: 14px;
    font-weight: 600;
    color: #F59E0B;
}

.insight-card .insights-list {
    margin: 0;
    padding-left: 20px;
    color: #E2E8F0;
}

.insight-card .insights-list li {
    margin: 6px 0;
    font-size: 13px;
}

/* ==================== Congestion Scale (v4.0) ==================== */
.congestion-scale {
    display: flex;
    gap: 12px;
    margin: 8px 0;
    flex-wrap: wrap;
}

.congestion-scale .level {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: #94A3B8;
}

.congestion-scale .level .box {
    width: 12px;
    height: 12px;
    border-radius: 2px;
}

.congestion-scale .level .box.low { background: #22C55E; }
.congestion-scale .level .box.medium { background: #FBBF24; }
.congestion-scale .level .box.high { background: #F97316; }
.congestion-scale .level .box.critical { background: #EF4444; }

/* ==================== Wait Time KPI (v4.0) ==================== */
.wait-kpi-card {
    background: #1E2330;
    border-radius: 8px;
    padding: 16px;
    border: 1px solid #2D3748;
    text-align: center;
}

.wait-kpi-card .label {
    font-size: 12px;
    color: #94A3B8;
    margin-bottom: 4px;
}

.wait-kpi-card .value {
    font-size: 24px;
    font-weight: 600;
    color: #FAFAFA;
}

.wait-kpi-card .subtitle {
    font-size: 11px;
    color: #64748B;
    margin-top: 4px;
}
</style>
"""


# ============================================================
# Helper Functions
# ============================================================

def get_building_color(building: str) -> str:
    """Get color for building"""
    return BUILDING_COLORS.get(building, COLORS["secondary"])


def get_status_color(status: str) -> str:
    """Get color for status"""
    return STATUS_COLORS.get(status, COLORS["secondary"])


def get_direction_color(direction: str) -> str:
    """Get color for direction"""
    return DIRECTION_COLORS.get(direction, COLORS["secondary"])


def get_confidence_class(confidence: float) -> str:
    """Get CSS class for confidence level"""
    if confidence >= 0.8:
        return "high"
    elif confidence >= 0.6:
        return "medium"
    else:
        return "low"


def apply_dark_layout(fig):
    """Apply dark theme layout to Plotly figure"""
    fig.update_layout(**PLOTLY_DARK_LAYOUT)
    return fig


# ============================================================
# Passenger Color Scale for Elevator Shaft Visualization
# ============================================================

PASSENGER_COLOR_SCALE = {
    0: "#64748B",       # Gray - 0 passengers
    1: "#86EFAC",       # Light green - 1-5
    6: "#22C55E",       # Green - 6-10
    11: "#FCD34D",      # Yellow - 11-15
    16: "#F97316",      # Orange - 16-20
    21: "#EF4444",      # Red - 21-25
}


def get_passenger_color(count: int) -> str:
    """
    Get color for passenger count (Elevator Shaft visualization)

    Args:
        count: Number of passengers

    Returns:
        Hex color string
    """
    if count == 0:
        return PASSENGER_COLOR_SCALE[0]
    elif count <= 5:
        return PASSENGER_COLOR_SCALE[1]
    elif count <= 10:
        return PASSENGER_COLOR_SCALE[6]
    elif count <= 15:
        return PASSENGER_COLOR_SCALE[11]
    elif count <= 20:
        return PASSENGER_COLOR_SCALE[16]
    else:
        return PASSENGER_COLOR_SCALE[21]


def get_classification_color(classification: str) -> str:
    """Get color for classification status"""
    colors = {
        "confirmed": "#22C55E",
        "probable": "#F59E0B",
        "rejected": "#64748B",
    }
    return colors.get(classification, "#64748B")


def get_evidence_color(evidence_type: str) -> str:
    """Get color for evidence type"""
    colors = {
        "rssi": "#3B82F6",
        "pressure": "#22C55E",
        "spatial": "#F59E0B",
        "timing": "#A855F7",
    }
    return colors.get(evidence_type, "#64748B")
