"""Reusable UI components (Dark Theme)"""

import streamlit as st
from typing import Optional, Any, Dict, List

from .styles import (
    get_building_color, get_status_color, get_confidence_class,
    BUILDING_COLORS, STATUS_COLORS, COLORS
)


def render_kpi_card(
    title: str,
    value: Any,
    delta: Optional[float] = None,
    delta_label: str = "",
    icon: str = "",
    color: str = "primary",
    subtitle: str = "",
) -> None:
    """
    Render a KPI metric card (Dark Theme)

    Args:
        title: Card title
        value: Main value to display
        delta: Optional delta value (positive/negative)
        delta_label: Label for delta
        icon: Optional emoji icon
        color: Color theme
        subtitle: Optional small text below value
    """
    # Format value
    if isinstance(value, float):
        if value >= 1000:
            formatted_value = f"{value:,.0f}"
        else:
            formatted_value = f"{value:.1f}"
    else:
        formatted_value = str(value)

    # Build delta HTML
    delta_html = ""
    if delta is not None:
        delta_class = "positive" if delta >= 0 else "negative"
        delta_sign = "+" if delta >= 0 else ""
        delta_html = f'<div class="delta {delta_class}">{delta_sign}{delta:.1f}% {delta_label}</div>'

    # Subtitle HTML
    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<div style="font-size:0.75rem; color:#888; margin-top:2px;">{subtitle}</div>'

    # Icon prefix
    icon_html = f"{icon} " if icon else ""

    st.markdown(f"""
    <div class="kpi-card">
        <div class="label">{icon_html}{title}</div>
        <div class="value">{formatted_value}</div>
        {subtitle_html}
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def render_status_indicator(status: str) -> str:
    """
    Get HTML for status indicator

    Args:
        status: "active", "running", "idle", or "warning"

    Returns:
        HTML string
    """
    color = get_status_color(status)
    symbols = {
        "active": "●",
        "running": "●",
        "idle": "○",
        "warning": "◉"
    }
    symbol = symbols.get(status, "○")
    return f'<span style="color: {color}; font-size: 10px;">{symbol}</span>'


def render_building_card(
    building: str,
    hoists: List[Dict],
    stats: Dict
) -> None:
    """
    Render building summary card (Dark Theme)

    Args:
        building: Building name (FAB, CUB, WWT)
        hoists: List of hoist info dicts
        stats: Building statistics
    """
    color = get_building_color(building)

    # Build hoist badges
    hoist_badges = ""
    for hoist in hoists:
        status = "active" if hoist.get("is_active", False) else "idle"
        badge_class = "active" if status == "active" else "idle"
        from ..utils.converters import format_hoist_name
        short_name = format_hoist_name(hoist["name"])
        hoist_badges += f'<span class="hoist-badge {badge_class}">{short_name}</span>'

    trip_count = stats.get('trip_count', 0)
    pax_count = stats.get('passenger_count', 0)

    st.markdown(f"""
    <div class="building-card {building}">
        <div class="title">{building} ({len(hoists)}대)</div>
        <div class="hoist-badges">{hoist_badges}</div>
        <div class="stats">운행 {trip_count}회 | 탑승 {pax_count}명</div>
    </div>
    """, unsafe_allow_html=True)


def render_trip_badge(direction: str) -> str:
    """Get HTML for trip direction badge"""
    labels = {"up": "상승", "down": "하강", "round": "왕복"}
    label = labels.get(direction, direction)
    return f'<span class="trip-badge {direction}">{label}</span>'


def render_confidence_bar(confidence: float) -> None:
    """Render confidence level as progress bar (Dark Theme)"""
    conf_class = get_confidence_class(confidence)
    pct = int(confidence * 100)

    st.markdown(f"""
    <div class="confidence-bar">
        <div class="bar">
            <div class="fill {conf_class}" style="width: {pct}%;"></div>
        </div>
        <span class="value">{pct}%</span>
    </div>
    """, unsafe_allow_html=True)


def render_floor_badge(floor: str, building: str = "") -> str:
    """Get HTML for floor badge"""
    return f'<span class="floor-badge">{floor}</span>'


def render_section_header(title: str, icon: str = "") -> None:
    """Render section header (Dark Theme)"""
    icon_html = f"{icon} " if icon else ""
    st.markdown(f"""
    <div class="section-header">{icon_html}{title}</div>
    """, unsafe_allow_html=True)


def render_empty_state(message: str, icon: str = "") -> None:
    """Render empty state placeholder (Dark Theme)"""
    st.markdown(f"""
    <div class="empty-state">
        <div class="icon">{icon}</div>
        <div class="message">{message}</div>
    </div>
    """, unsafe_allow_html=True)


def render_data_status_card(
    name: str,
    rows: int,
    status: str,
    size_mb: float = 0
) -> None:
    """Render data loading status card (Dark Theme)"""
    status_labels = {
        "loaded": "완료",
        "loading": "로딩 중...",
        "error": "오류",
        "pending": "대기"
    }
    label = status_labels.get(status, status)
    size_text = f" ({size_mb:.1f}MB)" if size_mb > 0 else ""

    st.markdown(f"""
    <div class="data-status-card">
        <span class="name">{name}</span>
        <span class="info">{f'{rows:,}' if isinstance(rows, (int, float)) else rows}행{size_text}</span>
        <span class="status {status}">{label}</span>
    </div>
    """, unsafe_allow_html=True)


def render_pipeline_progress(steps: List[Dict]) -> None:
    """
    Render pipeline progress indicator (Dark Theme)

    Args:
        steps: List of dicts with 'name', 'status' ('complete'|'running'|'pending')
               Optional 'progress' (0-100) for running state
    """
    icons = {
        "complete": "✓",
        "running": "●",
        "pending": "○"
    }

    steps_html = ""
    for step in steps:
        status = step.get("status", "pending")
        icon = icons.get(status, "○")
        name = step.get("name", "")

        progress_html = ""
        if status == "running" and "progress" in step:
            pct = step["progress"]
            progress_html = f' <span style="color: #64748B; font-size: 12px;">({pct}%)</span>'

        steps_html += f"""
        <div class="progress-step {status}">
            <span class="icon">{icon}</span>
            <span class="name">{name}{progress_html}</span>
        </div>
        """

    st.markdown(f"""
    <div class="progress-container">
        {steps_html}
    </div>
    """, unsafe_allow_html=True)


def render_cache_status_summary(
    sward_ok: bool,
    trips_ok: bool,
    passengers_ok: bool,
    trips_count: int = 0,
    passengers_count: int = 0
) -> None:
    """Render cache status summary"""
    def status_icon(ok: bool) -> str:
        return "✓" if ok else "○"

    def status_color(ok: bool) -> str:
        return "#22C55E" if ok else "#64748B"

    st.markdown(f"""
    <div class="progress-container">
        <div style="display: flex; align-items: center; margin: 8px 0;">
            <span style="color: {status_color(sward_ok)}; margin-right: 8px;">{status_icon(sward_ok)}</span>
            <span style="color: {'#94A3B8' if sward_ok else '#64748B'};">S-Ward 캐시</span>
        </div>
        <div style="display: flex; align-items: center; margin: 8px 0;">
            <span style="color: {status_color(trips_ok)}; margin-right: 8px;">{status_icon(trips_ok)}</span>
            <span style="color: {'#94A3B8' if trips_ok else '#64748B'};">Trip 추출{f' ({trips_count}개)' if trips_ok else ''}</span>
        </div>
        <div style="display: flex; align-items: center; margin: 8px 0;">
            <span style="color: {status_color(passengers_ok)}; margin-right: 8px;">{status_icon(passengers_ok)}</span>
            <span style="color: {'#94A3B8' if passengers_ok else '#64748B'};">탑승자 분류{f' ({passengers_count}명)' if passengers_ok else ''}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_evidence_bar(
    rssi_score: float,
    pressure_score: float,
    spatial_score: float,
    timing_score: float
) -> None:
    """
    Render v4.5 Rate-Matching score bars (Dark Theme).

    Note: In v4.5, only rate_match and delta_ratio are meaningful.
    spatial_score and timing_score are always 0.0 (legacy compatibility).
    RSSI is used for candidate selection only, not scoring.

    Args:
        rssi_score: Legacy RSSI score (0-1) — kept for backward compatibility
        pressure_score: Pressure rate-match score (= rate_match_score in v4.5)
        spatial_score: Always 0.0 in v4.5 (not used)
        timing_score: Always 0.0 in v4.5 (not used)
    """
    scores = [
        ("Rate Match", pressure_score, "pressure"),
        ("RSSI (참고)", rssi_score, "rssi"),
        ("공간", spatial_score, "spatial"),
        ("타이밍", timing_score, "timing"),
    ]

    bars_html = ""
    for label, score, css_class in scores:
        pct = int(score * 100)
        bars_html += f"""
        <div class="evidence-bar">
            <span class="label">{label}</span>
            <div class="bar-container">
                <div class="bar-fill {css_class}" style="width: {pct}%;"></div>
            </div>
            <span class="value">{pct}%</span>
        </div>
        """

    st.markdown(f"""
    <div class="evidence-summary-card">
        <div class="header">
            <span class="title">v4.5 Rate-Matching 점수</span>
        </div>
        {bars_html}
    </div>
    """, unsafe_allow_html=True)


def render_classification_badge(classification: str, composite_score: float = 0) -> str:
    """
    Get HTML for classification badge

    Args:
        classification: "confirmed", "probable", or "rejected"
        composite_score: Optional composite score to display

    Returns:
        HTML string
    """
    labels = {
        "confirmed": "확정",
        "probable": "추정",
        "rejected": "미분류"
    }
    label = labels.get(classification, classification)

    if composite_score > 0:
        label += f" ({composite_score*100:.0f}%)"

    return f'<span class="classification-badge {classification}">{label}</span>'


def render_passenger_color_legend() -> None:
    """Render passenger count color scale legend"""
    st.markdown("""
    <div class="pax-scale" style="display: flex; gap: 12px; flex-wrap: wrap; padding: 8px 0;">
        <span style="display: flex; align-items: center; gap: 4px;">
            <span class="color-box pax-0" style="width:16px; height:16px; background:#64748B; border-radius:2px;"></span>
            <span style="color:#94A3B8; font-size:11px;">0명</span>
        </span>
        <span style="display: flex; align-items: center; gap: 4px;">
            <span class="color-box" style="width:16px; height:16px; background:#86EFAC; border-radius:2px;"></span>
            <span style="color:#94A3B8; font-size:11px;">1-5명</span>
        </span>
        <span style="display: flex; align-items: center; gap: 4px;">
            <span class="color-box" style="width:16px; height:16px; background:#22C55E; border-radius:2px;"></span>
            <span style="color:#94A3B8; font-size:11px;">6-10명</span>
        </span>
        <span style="display: flex; align-items: center; gap: 4px;">
            <span class="color-box" style="width:16px; height:16px; background:#FCD34D; border-radius:2px;"></span>
            <span style="color:#94A3B8; font-size:11px;">11-15명</span>
        </span>
        <span style="display: flex; align-items: center; gap: 4px;">
            <span class="color-box" style="width:16px; height:16px; background:#F97316; border-radius:2px;"></span>
            <span style="color:#94A3B8; font-size:11px;">16-20명</span>
        </span>
        <span style="display: flex; align-items: center; gap: 4px;">
            <span class="color-box" style="width:16px; height:16px; background:#EF4444; border-radius:2px;"></span>
            <span style="color:#94A3B8; font-size:11px;">21+명</span>
        </span>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# Info Tooltip and Insight Components (v4.0)
# ============================================================

def render_info_tooltip(title: str, content: str) -> None:
    """
    Render info tooltip using st.expander

    Args:
        title: Tooltip title
        content: Markdown content
    """
    with st.expander(f"? {title}", expanded=False):
        st.markdown(content)


def render_insight_card(insights: List[str], title: str = "데이터 기반 인사이트") -> None:
    """
    Render insight card with bullet points

    Args:
        insights: List of insight strings
        title: Card title
    """
    if not insights:
        return

    insights_html = "".join([f"<li>{insight}</li>" for insight in insights])

    st.markdown(f"""
    <div class="insight-card">
        <div class="header">
            <span class="icon">&#128161;</span>
            <span class="title">{title}</span>
        </div>
        <ul class="insights-list">
            {insights_html}
        </ul>
    </div>
    """, unsafe_allow_html=True)


def render_congestion_legend() -> None:
    """Render congestion index color scale legend"""
    st.markdown("""
    <div class="congestion-scale">
        <span class="level">
            <span class="box low"></span>
            <span>0~0.3 (여유)</span>
        </span>
        <span class="level">
            <span class="box medium"></span>
            <span>0.3~0.6 (보통)</span>
        </span>
        <span class="level">
            <span class="box high"></span>
            <span>0.6~0.8 (혼잡)</span>
        </span>
        <span class="level">
            <span class="box critical"></span>
            <span>0.8~1.0 (매우혼잡)</span>
        </span>
    </div>
    """, unsafe_allow_html=True)


def render_wait_time_kpis(
    avg_wait_sec: float,
    max_wait_sec: float,
    total_man_minutes: float
) -> None:
    """
    Render wait time KPI cards

    Args:
        avg_wait_sec: Average wait time in seconds
        max_wait_sec: Maximum wait time in seconds
        total_man_minutes: Total wait man-minutes
    """
    def format_time(seconds: float) -> str:
        if seconds <= 0:
            return "0초"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        if minutes > 0:
            return f"{minutes}분 {secs}초"
        return f"{secs}초"

    col1, col2, col3 = st.columns(3)

    with col1:
        render_kpi_card(
            title="평균 대기시간",
            value=format_time(avg_wait_sec),
            icon=""
        )

    with col2:
        render_kpi_card(
            title="최대 대기시간",
            value=format_time(max_wait_sec),
            icon=""
        )

    with col3:
        if total_man_minutes > 0:
            hours = total_man_minutes / 60
            value = f"{total_man_minutes:.0f}분"
            if hours >= 1:
                value += f" ({hours:.1f}시간)"
        else:
            value = "0분"
        render_kpi_card(
            title="총 대기 인시",
            value=value,
            icon=""
        )


def render_composite_score_card(
    composite_score: float,
    classification: str,
    rssi_score: float = 0,
    pressure_score: float = 0,
    spatial_score: float = 0,
    timing_score: float = 0
) -> None:
    """
    Render composite score with ring visualization (Dark Theme)

    Args:
        composite_score: Weighted composite score (0-1)
        classification: "confirmed", "probable", or "rejected"
        rssi_score: RSSI evidence score
        pressure_score: Pressure correlation score
        spatial_score: Spatial evidence score
        timing_score: Timing evidence score
    """
    pct = int(composite_score * 100)

    # Determine ring color class
    if composite_score >= 0.6:
        ring_class = "high"
        ring_color = "#22C55E"
    elif composite_score >= 0.4:
        ring_class = "medium"
        ring_color = "#F59E0B"
    else:
        ring_class = "low"
        ring_color = "#EF4444"

    badge_html = render_classification_badge(classification)

    st.markdown(f"""
    <div class="evidence-summary-card">
        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
            <div style="
                width: 56px; height: 56px;
                border-radius: 50%;
                background: conic-gradient({ring_color} {pct}%, #2D3748 0);
                display: flex; align-items: center; justify-content: center;
            ">
                <div style="
                    width: 44px; height: 44px;
                    border-radius: 50%;
                    background: #1E2330;
                    display: flex; align-items: center; justify-content: center;
                    font-size: 14px; font-weight: 600; color: #FAFAFA;
                ">{pct}%</div>
            </div>
            <div>
                <div style="font-size: 14px; color: #94A3B8; margin-bottom: 4px;">종합 점수</div>
                {badge_html}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
