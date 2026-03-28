"""Global constants for Hoist Analysis"""

# Building colors
BUILDING_COLORS = {
    "FAB": "#2196F3",  # Blue
    "CUB": "#4CAF50",  # Green
    "WWT": "#FF9800",  # Orange
}

# Hoist status indicators
HOIST_STATUS = {
    "running": {"symbol": "●", "color": "#43A047"},
    "idle": {"symbol": "○", "color": "#78909C"},
    "warning": {"symbol": "◉", "color": "#FB8C00"},
}

# Device types
DEVICE_TYPES = {
    1: "iPhone",
    10: "Android",
    31: "Other",
    41: "T-Ward",
}

# Direction labels
DIRECTION_LABELS = {
    "up": "상승",
    "down": "하강",
    "round": "왕복",
}

# Floor order for sorting
FLOOR_ORDER = {
    "B1": -1,
    "1F": 0, "2F": 1, "3F": 2, "4F": 3, "5F": 4,
    "6F": 5, "7F": 6, "8F": 7, "9F": 8, "10F": 9,
    "Roof": 10,
}

# Default chart colors
CHART_COLORS = {
    "primary": "#1E88E5",
    "secondary": "#78909C",
    "success": "#43A047",
    "warning": "#FB8C00",
    "danger": "#E53935",
}
