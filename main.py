"""
호이스트 분석 - Y1
SK하이닉스 Y1 건설현장 호이스트 운행 분석 대시보드
"""

import streamlit as st
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

st.set_page_config(page_title="호이스트 분석 - Y1", page_icon="", layout="wide", initial_sidebar_state="collapsed")


# ── Auth ────────────────────────────────────────────────────
def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.markdown(
        "<h2 style='text-align:center; margin-top:15vh;'>호이스트 분석 - Y1</h2>"
        "<p style='text-align:center; color:#888;'>접속하려면 비밀번호를 입력하세요</p>",
        unsafe_allow_html=True,
    )
    _, col, _ = st.columns([1, 2, 1])
    with col:
        with st.form("login_form"):
            pwd = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인", use_container_width=True, type="primary"):
                import os
                if pwd == os.environ.get("APP_PASSWORD", "wonderful2$"):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다.")
    return False


if not check_password():
    st.stop()

# ── Imports ─────────────────────────────────────────────────
from src.utils.config import CLOUD_MODE, CACHE_DIR, detect_available_dates, DEFAULT_DATE
from src.data.cache_manager import CacheManager
from src.data.loader import load_hoist_info, load_floor_elevation
from src.ui.styles import CUSTOM_CSS
from src.tabs.overview_tab import render_overview_tab
from src.tabs.hoist_tab import render_hoist_tab
from src.tabs.passenger_tab import render_passenger_tab
from src.tabs.floor_tab import render_floor_tab
from src.tabs.multiday_tab import render_multiday_tab


# ── Cached loaders ──────────────────────────────────────────
@st.cache_data(ttl=300)
def _load_data(date_str):
    cm = CacheManager(CACHE_DIR)
    return cm.load_trips(date_str), cm.load_passengers(date_str), cm.load_sward(date_str)

@st.cache_data(ttl=600)
def _load_static(date_str):
    return load_hoist_info(date_str), load_floor_elevation(date_str)


# ── Main ────────────────────────────────────────────────────
def main():
    if "date_str" not in st.session_state:
        avail = detect_available_dates()
        st.session_state.date_str = avail[0] if avail else DEFAULT_DATE

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # Header
    c1, c2 = st.columns([3, 1])
    with c1:
        st.title("호이스트 분석 - Y1")
        st.caption("SK하이닉스 Y1 건설현장 호이스트 운행 대시보드")
    with c2:
        avail = detect_available_dates()
        if avail:
            labels = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in avail]
            sel = st.selectbox("분석 날짜", labels, key="date_sel")
            nd = avail[labels.index(sel)]
            if st.session_state.date_str != nd:
                st.session_state.date_str = nd
                st.cache_data.clear()

    # Load data
    date_str = st.session_state.date_str
    trips_df, passengers_df, sward_df = _load_data(date_str)
    if trips_df is None:
        trips_df = pd.DataFrame()
    if passengers_df is None:
        passengers_df = pd.DataFrame()
    if sward_df is None:
        sward_df = pd.DataFrame()
    try:
        hoist_info, floor_elevations = _load_static(date_str)
    except Exception:
        hoist_info, floor_elevations = {}, {}

    # Tabs
    tab_names = ["종합 현황", "운행 분석", "탑승자 분석", "층별 분석", "멀티데이 분석"]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        render_overview_tab(trips_df, passengers_df, hoist_info, sward_df)
    with tabs[1]:
        render_hoist_tab(trips_df, passengers_df, hoist_info, sward_df)
    with tabs[2]:
        render_passenger_tab(trips_df, passengers_df, hoist_info)
    with tabs[3]:
        render_floor_tab(trips_df, passengers_df, floor_elevations)
    with tabs[4]:
        render_multiday_tab(CacheManager(CACHE_DIR), hoist_info)

    st.markdown("---")
    st.caption(f"호이스트 분석 v4.5 Rate-Matching | TJLABS Research | {'Cloud' if CLOUD_MODE else 'Development'} Mode")


if __name__ == "__main__":
    main()
