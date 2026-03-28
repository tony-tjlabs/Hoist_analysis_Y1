"""
Claude API 기반 LLM 해석 레이어 (호이스트 분석 전용).

집계된 호이스트 운행 데이터를 받아 건설현장 관리자를 위한 인사이트 생성.
보안 최우선: 민감 정보(현장명, 작업자명, 업체명 등)는 익명화 후 전송.

사용처:
  - overview_tab.py: 하루 전체 운영 요약 브리핑
  - hoist_tab.py: 대기시간/혼잡도 기반 운영 개선 제안
  - passenger_tab.py: 업체별/시간대별 이용 패턴 요약
"""

from __future__ import annotations
import os
import logging
import hashlib
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# anthropic 패키지 선택적 임포트 (미설치 시 graceful fallback)
try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    logger.info("anthropic 패키지 미설치 - LLM 해석 비활성화")

# dotenv: 로컬 폴백용 (클라우드에서는 st.secrets 사용)
from pathlib import Path

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    _ENV_PATH = _PROJECT_ROOT / ".env"
except ImportError:
    _DOTENV_AVAILABLE = False
    _ENV_PATH = None

# Streamlit 선택적 임포트
try:
    import streamlit as st
    _STREAMLIT_AVAILABLE = True
except ImportError:
    _STREAMLIT_AVAILABLE = False


# ── 모델 설정 ────────────────────────────────────────────────────────────────
_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 300
_TEMPERATURE = 0.3


# ══════════════════════════════════════════════════════════════════════════════
# 보안: 익명화 레이어
# ══════════════════════════════════════════════════════════════════════════════

# 익명화 매핑 (세션 내 일관성 유지)
_ANON_BUILDING_MAP: Dict[str, str] = {}
_ANON_HOIST_MAP: Dict[str, str] = {}
_ANON_COMPANY_MAP: Dict[str, str] = {}

# 절대 LLM에 전송하면 안 되는 키워드 (현장 식별 가능 정보)
_FORBIDDEN_KEYWORDS = [
    "SK하이닉스", "SK", "하이닉스", "Hynix",
    "Y1", "Y2", "Y-Project", "Y Project",
    "FAB", "CUB", "WWT", "SUB",  # 실제 건물명
    "화성", "이천", "청주",  # 지역명
]


def _get_anon_letter(index: int) -> str:
    """인덱스를 A, B, C... 형태로 변환."""
    if index < 26:
        return chr(65 + index)  # A-Z
    else:
        return f"A{index - 25}"  # A26, A27...


def anonymize_building(building_name: str) -> str:
    """건물명 익명화: FAB -> 건물 A."""
    if not building_name:
        return "건물"
    if building_name not in _ANON_BUILDING_MAP:
        idx = len(_ANON_BUILDING_MAP)
        _ANON_BUILDING_MAP[building_name] = f"건물 {_get_anon_letter(idx)}"
    return _ANON_BUILDING_MAP[building_name]


def anonymize_hoist(hoist_name: str) -> str:
    """호이스트명 익명화: FAB_Hoist_1 -> 호이스트 1."""
    if not hoist_name:
        return "호이스트"
    if hoist_name not in _ANON_HOIST_MAP:
        idx = len(_ANON_HOIST_MAP) + 1
        _ANON_HOIST_MAP[hoist_name] = f"호이스트 {idx}"
    return _ANON_HOIST_MAP[hoist_name]


def anonymize_company(company_name: str) -> str:
    """업체명 익명화: 삼성물산 -> 업체 A."""
    if not company_name:
        return "업체"
    if company_name not in _ANON_COMPANY_MAP:
        idx = len(_ANON_COMPANY_MAP)
        _ANON_COMPANY_MAP[company_name] = f"업체 {_get_anon_letter(idx)}"
    return _ANON_COMPANY_MAP[company_name]


def _contains_forbidden(text: str) -> bool:
    """금지 키워드 포함 여부 검사."""
    text_upper = text.upper()
    for keyword in _FORBIDDEN_KEYWORDS:
        if keyword.upper() in text_upper:
            return True
    return False


def anonymize_for_llm(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM 전송용 데이터 익명화.

    허용:
        - 집계 통계 (운행 횟수, 평균 탑승인원, 혼잡도 지수 등)
        - 익명화된 식별자 (호이스트 1, 건물 A, 업체 B)
        - 시간대별 패턴 (07시 52회 운행)

    금지:
        - 작업자 이름, MAC, user_no
        - 업체명 원본
        - 현장명 (SK하이닉스, Y1 등)
        - 호이스트/건물 실제 이름
        - 게이트웨이 번호
        - 좌표 정보
    """
    anon = {}

    for key, value in data.items():
        # 절대 포함 불가 키
        if key in ["worker_name", "worker", "user_no", "mac_address", "mac",
                   "gateway_no", "coordinates", "x", "y", "site_name", "project_name"]:
            continue  # 스킵

        # 건물명 익명화
        if key in ["building", "building_name"]:
            anon["building"] = anonymize_building(str(value))
            continue

        # 호이스트명 익명화
        if key in ["hoist", "hoist_name"]:
            anon["hoist"] = anonymize_hoist(str(value))
            continue

        # 업체명 익명화
        if key in ["company", "company_name"]:
            anon["company"] = anonymize_company(str(value))
            continue

        # Dict 내부 재귀 처리
        if isinstance(value, dict):
            anon[key] = anonymize_for_llm(value)
            continue

        # List 처리
        if isinstance(value, list):
            anon_list = []
            for item in value:
                if isinstance(item, dict):
                    anon_list.append(anonymize_for_llm(item))
                elif isinstance(item, str):
                    # 문자열에 금지 키워드 있으면 스킵
                    if not _contains_forbidden(item):
                        anon_list.append(item)
                else:
                    anon_list.append(item)
            anon[key] = anon_list
            continue

        # 문자열 값에 금지 키워드 검사
        if isinstance(value, str):
            if _contains_forbidden(value):
                continue  # 스킵
            anon[key] = value
            continue

        # 숫자/기타 값은 그대로
        anon[key] = value

    return anon


def validate_no_sensitive_data(text: str) -> bool:
    """최종 검증: 전송 직전 텍스트에 민감 정보 없는지 확인."""
    return not _contains_forbidden(text)


# ══════════════════════════════════════════════════════════════════════════════
# API 클라이언트
# ══════════════════════════════════════════════════════════════════════════════

def _get_api_key() -> Optional[str]:
    """API 키 조회. 1순위: st.secrets, 2순위: .env/환경변수."""
    # 1순위: Streamlit Secrets (클라우드)
    if _STREAMLIT_AVAILABLE:
        try:
            secret_key = st.secrets.get("ANTHROPIC_API_KEY")
            if secret_key and "여기에" not in str(secret_key) and "sk-" in str(secret_key):
                return secret_key
        except (FileNotFoundError, KeyError, Exception):
            pass

    # 2순위: .env (로컬)
    if _DOTENV_AVAILABLE and _ENV_PATH and _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)

    key = os.getenv("ANTHROPIC_API_KEY")
    if key and "여기에" not in str(key) and "sk-" in str(key):
        return key
    return None


def get_llm_status() -> Dict[str, Any]:
    """LLM 연결 상태 진단."""
    status = {
        "anthropic_installed": _ANTHROPIC_AVAILABLE,
        "api_key_configured": False,
        "api_key_source": None,
        "ready": False,
        "message": "",
    }

    if not _ANTHROPIC_AVAILABLE:
        status["message"] = "anthropic 패키지 미설치"
        return status

    api_key = _get_api_key()
    if api_key:
        status["api_key_configured"] = True
        status["ready"] = True
        status["message"] = "Claude API 연결 준비 완료"

        if _STREAMLIT_AVAILABLE:
            try:
                sk = st.secrets.get("ANTHROPIC_API_KEY", "")
                if sk and "여기에" not in str(sk) and "sk-" in str(sk):
                    status["api_key_source"] = "Streamlit secrets"
                else:
                    status["api_key_source"] = ".env / 환경변수"
            except Exception:
                status["api_key_source"] = ".env / 환경변수"
        else:
            status["api_key_source"] = ".env / 환경변수"
    else:
        status["message"] = "ANTHROPIC_API_KEY 미설정"

    return status


def _get_client():
    """Anthropic 클라이언트 반환. 불가 시 None."""
    if not _ANTHROPIC_AVAILABLE:
        return None
    api_key = _get_api_key()
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def _call(prompt: str, max_tokens: int = _MAX_TOKENS) -> Optional[str]:
    """Claude API 호출. 실패 시 None."""
    # 전송 직전 보안 검증
    if not validate_no_sensitive_data(prompt):
        logger.error("LLM 프롬프트에 민감 정보 감지됨 - 호출 취소")
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        msg = client.messages.create(
            model=_MODEL,
            max_tokens=max_tokens,
            temperature=_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Claude API 호출 실패: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 인사이트 생성 함수
# ══════════════════════════════════════════════════════════════════════════════

def generate_daily_summary(
    total_trips: int,
    total_passengers: int,
    active_hoists: int,
    total_hoists: int,
    peak_hour: Optional[int],
    peak_trips: int,
    avg_ci: float,
    building_stats: Dict[str, Dict],
) -> Optional[str]:
    """
    종합 현황 탭: 하루 전체 운영 요약.

    Args:
        total_trips: 총 운행 횟수
        total_passengers: 총 탑승인원
        active_hoists: 활성 호이스트 수
        total_hoists: 전체 호이스트 수
        peak_hour: 피크 시간대 (hour)
        peak_trips: 피크 시간 운행 수
        avg_ci: 평균 혼잡도 지수
        building_stats: 건물별 통계 {building: {trips, passengers}}

    Returns:
        LLM 생성 요약 또는 None
    """
    # 익명화된 건물 통계
    anon_building = {}
    for bldg, stats in building_stats.items():
        anon_name = anonymize_building(bldg)
        anon_building[anon_name] = {
            "trips": stats.get("trips", 0),
            "passengers": stats.get("passengers", 0),
        }

    data = {
        "total_trips": total_trips,
        "total_passengers": total_passengers,
        "active_hoists": active_hoists,
        "total_hoists": total_hoists,
        "peak_hour": f"{peak_hour}:00" if peak_hour is not None else "없음",
        "peak_trips": peak_trips,
        "avg_congestion_index": round(avg_ci, 2),
        "building_stats": anon_building,
    }

    prompt = f"""건설현장 호이스트 운행 데이터를 요약해주세요.

데이터:
{data}

규칙:
- 핵심 패턴 2-3개 도출
- 운영 개선 포인트 1개 제안 (있을 경우에만)
- 40단어 이내 한국어
- 숫자는 유지하되 해석 추가
- "분석가 역할" 하지 말고 수치 기반 간결한 요약만"""

    return _call(prompt)


def generate_congestion_insight(
    hoist_hourly_ci: Dict[str, Dict[int, float]],
    peak_analysis: Dict[str, Any],
    insights: List[str],
) -> Optional[str]:
    """
    종합 현황/운행 분석 탭: 혼잡도 기반 해석.

    Args:
        hoist_hourly_ci: {hoist_name: {hour: ci_value}}
        peak_analysis: 피크 시간 분석 결과
        insights: 규칙 기반 인사이트 리스트
    """
    # 호이스트명 익명화
    anon_ci = {}
    for hoist, hourly in hoist_hourly_ci.items():
        anon_hoist = anonymize_hoist(hoist)
        anon_ci[anon_hoist] = hourly

    data = {
        "hourly_congestion": anon_ci,
        "peak_hour": peak_analysis.get("peak_hour"),
        "peak_ci": round(peak_analysis.get("peak_ci", 0), 2),
        "rule_based_insights": insights[:3],  # 최대 3개
    }

    prompt = f"""호이스트 혼잡도 데이터를 해석해주세요.

데이터:
{data}

규칙:
- 혼잡도 패턴 1-2개 해석
- 운행 분산 제안 (필요시)
- 30단어 이내 한국어
- 기존 규칙 기반 인사이트와 중복 피하기"""

    return _call(prompt)


def generate_wait_time_insight(
    avg_wait: float,
    max_wait: float,
    hoist_wait: Dict[str, float],
    hourly_wait: Dict[int, float],
) -> Optional[str]:
    """
    운행 분석 탭: 대기시간 기반 해석.

    Args:
        avg_wait: 평균 대기시간 (분)
        max_wait: 최대 대기시간 (분)
        hoist_wait: 호이스트별 평균 대기시간
        hourly_wait: 시간대별 평균 대기시간
    """
    # 호이스트명 익명화
    anon_wait = {}
    for hoist, wait in hoist_wait.items():
        anon_hoist = anonymize_hoist(hoist)
        anon_wait[anon_hoist] = round(wait, 1)

    data = {
        "avg_wait_min": round(avg_wait, 1),
        "max_wait_min": round(max_wait, 1),
        "hoist_wait": anon_wait,
        "hourly_wait": {h: round(w, 1) for h, w in hourly_wait.items()},
    }

    prompt = f"""호이스트 대기시간 데이터를 해석해주세요.

데이터:
{data}

규칙:
- 대기시간 패턴 1-2개 해석
- 병목 시간대/호이스트 지적 (있을 경우)
- 30단어 이내 한국어"""

    return _call(prompt)


def generate_passenger_pattern_insight(
    company_stats: Dict[str, Dict],
    hourly_pattern: Dict[int, int],
    classification_summary: Dict[str, int],
) -> Optional[str]:
    """
    탑승자 분석 탭: 업체별/시간대별 이용 패턴 요약.

    Args:
        company_stats: 업체별 통계 {company: {count, avg_floor}}
        hourly_pattern: 시간대별 탑승자 수
        classification_summary: 분류별 인원 {type: count}
    """
    # 업체명 익명화
    anon_company = {}
    for company, stats in company_stats.items():
        anon_name = anonymize_company(company)
        anon_company[anon_name] = {
            "passengers": stats.get("count", 0),
            "avg_floor": round(stats.get("avg_floor", 0), 1),
        }

    data = {
        "company_usage": anon_company,
        "hourly_pattern": hourly_pattern,
        "classification": classification_summary,
    }

    prompt = f"""호이스트 탑승자 패턴 데이터를 요약해주세요.

데이터:
{data}

규칙:
- 업체 이용 패턴 1-2개 해석
- 피크 시간대 특성 언급
- 30단어 이내 한국어"""

    return _call(prompt)


# ══════════════════════════════════════════════════════════════════════════════
# UI 헬퍼
# ══════════════════════════════════════════════════════════════════════════════

def render_data_comment(content: str, title: str = "데이터 기반 해석") -> None:
    """
    LLM 응답을 접힌 상태의 expander로 표시.
    데이터가 항상 먼저 보이도록 expanded=False.
    """
    if not _STREAMLIT_AVAILABLE:
        return

    if not content:
        return

    with st.expander(f":bulb: {title}", expanded=False):
        st.markdown(content)


def get_cache_key(*args) -> str:
    """캐시 키 생성 (날짜+데이터 해시)."""
    text = "".join(str(a) for a in args)
    return hashlib.md5(text.encode()).hexdigest()[:12]


def get_cached_insight(cache_key: str) -> Optional[str]:
    """session_state에서 캐시된 인사이트 조회."""
    if not _STREAMLIT_AVAILABLE:
        return None
    if "llm_cache" not in st.session_state:
        st.session_state.llm_cache = {}
    return st.session_state.llm_cache.get(cache_key)


def set_cached_insight(cache_key: str, content: str) -> None:
    """session_state에 인사이트 캐싱."""
    if not _STREAMLIT_AVAILABLE:
        return
    if "llm_cache" not in st.session_state:
        st.session_state.llm_cache = {}
    st.session_state.llm_cache[cache_key] = content


def clear_llm_cache() -> None:
    """날짜 변경 시 캐시 초기화."""
    if _STREAMLIT_AVAILABLE and "llm_cache" in st.session_state:
        st.session_state.llm_cache = {}
