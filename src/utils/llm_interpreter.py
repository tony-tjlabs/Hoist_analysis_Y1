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
_MAX_TOKENS = 800
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
    hourly_passengers: Optional[Dict[int, int]] = None,
    hourly_trips: Optional[Dict[int, int]] = None,
) -> Optional[str]:
    """
    운행 분석 탭: 대기시간 기반 해석 (건설현장 컨텍스트 포함).

    Args:
        avg_wait: 평균 대기시간 (초)
        max_wait: 최대 대기시간 (초)
        hoist_wait: 호이스트별 평균 대기시간 (초)
        hourly_wait: 시간대별 평균 대기시간 (초)
        hourly_passengers: 시간대별 탑승 건수 (컨텍스트용)
        hourly_trips: 시간대별 운행 횟수 (컨텍스트용)
    """
    # 호이스트명 익명화
    anon_wait = {}
    for hoist, wait in hoist_wait.items():
        anon_hoist = anonymize_hoist(hoist)
        anon_wait[anon_hoist] = round(wait, 1)

    # 시간대별 대기시간 + 탑승건수 + 운행수를 함께 전달
    hourly_context = {}
    for h, w in hourly_wait.items():
        entry = {"avg_wait_sec": round(w, 1)}
        if hourly_passengers:
            entry["passengers"] = hourly_passengers.get(h, 0)
        if hourly_trips:
            entry["trips"] = hourly_trips.get(h, 0)
        hourly_context[h] = entry

    data = {
        "avg_wait_sec": round(avg_wait, 1),
        "max_wait_sec": round(max_wait, 1),
        "hoist_wait_sec": anon_wait,
        "hourly_context": hourly_context,
    }

    prompt = f"""건설현장 호이스트 대기시간 데이터를 해석해주세요.

데이터:
{data}

건설현장 컨텍스트:
- 건설현장은 보통 06~07시 출근, 18~19시 퇴근
- 야간 작업조는 새벽에 교대하며, 이때 호이스트 이용은 소수
- 새벽 시간(00~05시)에 대기시간이 길게 나오면, 실제 대기가 아닌 BLE 센서 감지 특성(야간 저빈도 감지)이나 작업자가 호이스트 근처에서 다른 작업을 하다가 탑승한 경우일 수 있음
- 대기시간은 "호이스트 근처 첫 감지 ~ 실제 탑승"으로 계산됨

규칙:
- [WHAT] 데이터에서 보이는 패턴 2-3개 (시간대별 대기시간 + 탑승건수를 함께 해석)
- [WHY] 각 패턴의 원인 추정 (건설현장 특성 반영)
- [NOTE] 데이터 해석 시 주의점 (측정 한계, 신뢰도 이슈 등)
- 60단어 이내 한국어
- 새벽/야간의 높은 대기시간은 반드시 탑승 건수와 함께 언급하여 맥락 제공"""

    return _call(prompt, max_tokens=400)


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
# v4.5 탑승자 분석 인사이트
# ══════════════════════════════════════════════════════════════════════════════

def generate_passenger_daily_insight(
    total_passengers: int,
    confirmed_count: int,
    probable_count: int,
    hourly_pattern: Dict[int, int],
    peak_hour: Optional[int],
    peak_count: int,
    hoist_summary: Dict[str, Dict],
    company_summary: Dict[str, int],
) -> Optional[str]:
    """
    탑승자 분석 탭: 일일 탑승자 종합 분석.

    SK하이닉스 + SK에코플랜트 고객 프레젠테이션용 — 상세한 설명 필요.
    """
    # 익명화
    anon_hoist = {}
    for hoist, stats in hoist_summary.items():
        anon_hoist[anonymize_hoist(hoist)] = stats

    anon_company = {}
    for company, count in company_summary.items():
        anon_company[anonymize_company(company)] = count

    data = {
        "total_passengers": total_passengers,
        "confirmed": confirmed_count,
        "probable": probable_count,
        "confirmed_pct": round(confirmed_count / max(total_passengers, 1) * 100, 1),
        "probable_pct": round(probable_count / max(total_passengers, 1) * 100, 1),
        "hourly_pattern": hourly_pattern,
        "peak_hour": f"{peak_hour}:00" if peak_hour is not None else "없음",
        "peak_count": peak_count,
        "hoist_summary": anon_hoist,
        "company_usage": anon_company,
    }

    prompt = f"""건설현장 호이스트 탑승자 일일 종합 분석입니다. 고객 프레젠테이션용으로 상세하게 작성해주세요.

데이터:
{data}

건설현장 컨텍스트:
- 호이스트 = 건설현장 수직 이동 수단 (엘리베이터)
- 탑승자 분류: 확정(Confirmed) = 기압 변화율 일치 확인, 추정(Probable) = BLE gap으로 확신도 낮지만 탑승으로 분류
- 출근(07~08시), 퇴근(17~18시), 점심(12~13시)이 전형적 피크
- 업체별 이용 패턴은 해당 업체의 작업 위치와 관련됨

규칙:
- [WHAT] 데이터에서 보이는 핵심 패턴 3-4개 (숫자 반드시 포함)
- [WHY] 각 패턴의 원인 추정 (건설현장 특성 반영)
- [NOTE] 데이터 해석 시 참고사항 (Probable 의미, BLE 한계 등)
- 120단어 이내 한국어
- 프레젠테이션에 적합한 명확하고 자신있는 톤"""

    return _call(prompt, max_tokens=800)


def generate_hoist_usage_insight(
    hoist_data: Dict[str, Dict],
) -> Optional[str]:
    """
    탑승자 분석 탭: 호이스트별 이용 분석.
    """
    # 익명화
    anon_data = {}
    for hoist, stats in hoist_data.items():
        anon_name = anonymize_hoist(hoist)
        anon_stats = {k: v for k, v in stats.items() if k != "top_companies"}
        # 업체명 익명화
        if "top_companies" in stats:
            anon_companies = {}
            for company, count in stats["top_companies"].items():
                anon_companies[anonymize_company(company)] = count
            anon_stats["top_companies"] = anon_companies
        anon_data[anon_name] = anon_stats

    data = {"hoist_usage": anon_data}

    prompt = f"""건설현장 호이스트별 이용 분석입니다. 호이스트 간 비교와 최적화 제안을 해주세요.

데이터:
{data}

건설현장 컨텍스트:
- 각 호이스트는 특정 건물(동)에 배치됨
- 호이스트별 이용 편차가 크면 → 부하 불균형 (특정 호이스트 과부하, 장비 마모 가속)
- 특정 업체가 특정 호이스트에 집중 → 해당 업체 작업 위치와 관련
- 확정 비율이 높은 호이스트 = BLE 커버리지 양호, Probable 비율 높음 = BLE 간헐 감지

규칙:
- [WHAT] 호이스트별 이용 현황과 특이사항 2-3개
- [WHY] 부하 편차의 원인과 업체별 이용 패턴
- [NOTE] 효율화 제안 1-2개 (부하 분산, 피크 시간 조정 등)
- 100단어 이내 한국어
- 호이스트별 confirmed/probable 비율 차이도 언급"""

    return _call(prompt, max_tokens=700)


def generate_probable_explanation_insight(
    prob_stats: Dict[str, Any],
) -> Optional[str]:
    """
    탑승자 분석 탭: Probable 분류 설명.
    고객에게 Probable의 의미를 명확히 전달하기 위한 인사이트.
    """
    data = prob_stats

    prompt = f"""호이스트 탑승자 분류에서 'Probable(추정)' 건에 대한 해석입니다.
고객 프레젠테이션용이므로, Probable이 무엇인지, 왜 발생하는지, 신뢰할 수 있는지를 명확히 설명해주세요.

데이터:
{data}

알고리즘 컨텍스트:
- v4.5 Rate-Matching: 작업자의 기압 변화율(dp/dt)을 호이스트의 기압 변화율과 비교
- RSSI는 후보 선별에만 사용, 점수에 반영하지 않음. 핵심은 기압 변화
- 멀티스케일 매칭: 10초/30초/60초 3개 윈도우에서 비교 (BLE 통신 갭에 강건)
- Confirmed (composite >= 0.60): 기압 변화율이 호이스트와 잘 일치
- Probable (composite 0.45~0.60): 호이스트 탑승으로 분류됨. BLE 통신 갭으로 확신도 낮음
- Primary Probable: rate >= 0.40이지만 composite < 0.60 (delta/direction 감점)
- Fallback Probable: rate < 0.40이지만 delta ratio 0.5~1.3 + worker delta >= 0.5hPa

핵심 메시지:
- Probable도 "호이스트 탑승"으로 분류됨 (미탑승이 아님)
- Confirmed과의 차이는 "확신도"이지 "탑승 여부"가 아님
- BLE 통신 갭(콘크리트/철근 구조물로 인한 30~90초 데이터 손실)이 주 원인

규칙:
- [WHAT] Probable 현황 요약 (건수, 비율, Primary/Fallback 분포)
- [WHY] Probable이 발생하는 기술적 원인 (BLE gap, rate matching 구간 부족)
- [NOTE] Probable 데이터의 신뢰성과 활용 방법
- 100단어 이내 한국어
- 고객이 Probable을 "미탑승"으로 오해하지 않도록 명확히 설명"""

    return _call(prompt, max_tokens=700)


def generate_algorithm_explanation(
    algo_stats: Dict[str, Any],
) -> Optional[str]:
    """
    탑승자 분석 탭: v4.5 알고리즘 성능 해석.
    """
    data = algo_stats

    prompt = f"""호이스트 탑승자 분류 알고리즘(v4.5 Rate-Matching)의 성능을 해석해주세요.

데이터:
{data}

알고리즘 설명:
- v4.5 Rate-Matching: RSSI(신호 강도)는 후보 선별에만 사용, 점수에 반영하지 않음
- 핵심은 기압 변화율(dp/dt) 비교: 같은 엘리베이터에 탑승하면 같은 속도로 기압이 변함
- 멀티스케일 매칭: 10초/30초/60초 3개 윈도우에서 비교 (BLE 통신 갭 30~90초에 강건)
- Composite = rate_match x 0.65 + delta_ratio x 0.25 + direction x 0.10
- RSSI 탑승구간 재배정: 동일 건물 내 복수 호이스트 동시 운행 시 평균 RSSI 기준 재배정
- Confirmed >= 0.60, Probable 0.45~0.60

규칙:
- [WHAT] 알고리즘 분류 결과 요약 (확정/추정 비율, 평균 점수)
- [WHY] 이 알고리즘이 기존 방식(RSSI 기반)보다 나은 이유
- [NOTE] 한계점과 향후 개선 방향
- 80단어 이내 한국어
- 기술적이지만 비전문가도 이해할 수 있는 수준"""

    return _call(prompt, max_tokens=600)


# ══════════════════════════════════════════════════════════════════════════════
# 멀티데이 분석 인사이트 (v5.1)
# ══════════════════════════════════════════════════════════════════════════════

def generate_multiday_structural_insight(
    daily_stats: List[Dict],
    hourly_pattern: Dict[int, Dict],
    hoist_stats: Dict[str, Dict],
) -> Optional[str]:
    """
    멀티데이 탭: 구조적 패턴 발견 및 효율화 제안.

    Args:
        daily_stats: 일별 통계 [{date, trips, passengers, peak_hour, peak_ci}]
        hourly_pattern: 시간대별 반복 패턴 {hour: {avg_pax, occurrence_rate, dates_occurred}}
        hoist_stats: 호이스트별 통계 {hoist: {total_trips, avg_util, trip_share}}
    """
    # 익명화
    anon_hoist_stats = {}
    for hoist, stats in hoist_stats.items():
        anon_hoist = anonymize_hoist(hoist)
        anon_hoist_stats[anon_hoist] = {
            "total_trips": stats.get("total_trips", 0),
            "utilization_pct": round(stats.get("avg_util", 0) * 100, 1),
            "trip_share_pct": round(stats.get("trip_share", 0), 1),
        }

    # 반복 피크 시간대만 추출 (60% 이상 발생)
    recurring_peaks = {}
    for hour, pattern in hourly_pattern.items():
        if pattern.get("occurrence_rate", 0) >= 0.6:
            recurring_peaks[hour] = {
                "avg_passengers": round(pattern.get("avg_pax", 0), 0),
                "occurrence_rate_pct": round(pattern.get("occurrence_rate", 0) * 100, 0),
            }

    data = {
        "num_days": len(daily_stats),
        "avg_daily_trips": round(sum(d.get("trips", 0) for d in daily_stats) / len(daily_stats), 1) if daily_stats else 0,
        "avg_daily_passengers": round(sum(d.get("passengers", 0) for d in daily_stats) / len(daily_stats), 1) if daily_stats else 0,
        "recurring_peak_hours": recurring_peaks,
        "hoist_utilization": anon_hoist_stats,
    }

    prompt = f"""건설현장 호이스트 멀티데이 분석 데이터입니다. 구조적 패턴과 효율화 제안을 도출해주세요.

데이터:
{data}

건설현장 컨텍스트:
- 호이스트 = 건설현장 엘리베이터 (층간 이동 수단)
- 작업자들은 계단보다 호이스트를 선호 (대기를 감수하더라도)
- 출근(07~08시), 퇴근(17~18시), 점심(12~13시)은 반복적 피크 발생
- 호이스트 운행 패턴은 날짜별로 매우 유사함 (구조적 특성)
- 동일 시간대 여러 호이스트가 피크면 → 시차 운행으로 분산 가능

규칙:
- [분석] 데이터에서 발견한 구조적 패턴 2-3개 (일시적이 아닌 반복되는 패턴)
- [인사이트] 각 패턴의 의미와 영향 (생산성 손실, 대기시간 증가 등)
- [제안] 구체적 효율화 방안 1-2개 (시차 운행, 호이스트 재배치, 피크 시간 추가 투입 등)
- 80단어 이내 한국어
- 수치는 반드시 포함하되, 맥락과 함께 해석"""

    return _call(prompt, max_tokens=500)


def generate_hoist_efficiency_insight(
    hoist_comparison: List[Dict],
    load_imbalance: Dict,
    wait_summary: Optional[Dict] = None,
) -> Optional[str]:
    """
    운행 분석 탭 / 멀티데이 탭: 호이스트 효율화 제안.

    Args:
        hoist_comparison: [{hoist, trips, avg_pax, max_pax, utilization}]
        load_imbalance: {dominant_hoist, dominant_share, imbalance_score}
        wait_summary: 대기시간 요약 (선택)
    """
    # 익명화
    anon_comparison = []
    for h in hoist_comparison:
        anon_comparison.append({
            "hoist": anonymize_hoist(h.get("hoist", "")),
            "trips": h.get("trips", 0),
            "avg_passengers": round(h.get("avg_pax", 0), 1),
            "max_passengers": h.get("max_pax", 0),
            "utilization_pct": round(h.get("utilization", 0) * 100, 1),
        })

    anon_dominant = anonymize_hoist(load_imbalance.get("dominant_hoist", ""))

    data = {
        "hoist_stats": anon_comparison,
        "load_imbalance": {
            "dominant_hoist": anon_dominant,
            "dominant_share_pct": round(load_imbalance.get("dominant_share", 0), 1),
            "imbalance_score": round(load_imbalance.get("imbalance_score", 0), 2),
        },
    }

    if wait_summary:
        data["wait_summary"] = {
            "avg_wait_sec": round(wait_summary.get("avg_wait", 0), 1),
            "max_wait_sec": round(wait_summary.get("max_wait", 0), 1),
        }

    prompt = f"""건설현장 호이스트 효율 분석 데이터입니다. 효율화 제안을 도출해주세요.

데이터:
{data}

건설현장 컨텍스트:
- 가동률 20% 미만 호이스트는 다른 건물 지원 가능
- 부하 집중(30%+)은 해당 호이스트 마모 가속화 + 대기시간 증가
- 피크 시간 추가 호이스트 투입 시 대기시간 50% 이상 감소 가능
- 최대 탑승 25~30명 (물리적 한계, 안전 기준)

규칙:
- [분석] 호이스트별 효율/부하 현황 2-3개 포인트
- [인사이트] 비효율 원인과 영향
- [제안] 구체적 개선 방안 1-2개 (인력 재배치, 시차 운행, 정비 일정 등)
- 70단어 이내 한국어"""

    return _call(prompt, max_tokens=450)


def generate_congestion_context_insight(
    hourly_ci: Dict[int, float],
    hourly_wait: Dict[int, float],
    hourly_passengers: Dict[int, int],
    hourly_trips: Dict[int, int],
) -> Optional[str]:
    """
    종합현황/운행분석 탭: 혼잡도 + 대기시간 교차 분석.

    대기시간과 혼잡도를 교차 분석하여 맥락 기반 해석 제공.

    Args:
        hourly_ci: 시간대별 혼잡도 지수 {hour: ci}
        hourly_wait: 시간대별 평균 대기시간(초) {hour: wait_sec}
        hourly_passengers: 시간대별 탑승 건수 {hour: count}
        hourly_trips: 시간대별 운행 횟수 {hour: count}
    """
    # 시간대별 통합 데이터 구성
    hours_data = {}
    for h in range(6, 21):  # 작업시간
        hours_data[h] = {
            "congestion_index": round(hourly_ci.get(h, 0), 2),
            "avg_wait_sec": round(hourly_wait.get(h, 0), 1),
            "passengers": hourly_passengers.get(h, 0),
            "trips": hourly_trips.get(h, 0),
        }

    # 특이점 추출 (새벽 시간대 / 피크 시간대)
    dawn_data = {h: hours_data.get(h, {}) for h in range(0, 6) if h in hourly_ci}
    peak_hours = [h for h, d in hours_data.items() if d.get("passengers", 0) > 50]

    data = {
        "work_hours": hours_data,
        "peak_hours": peak_hours,
        "has_dawn_data": len(dawn_data) > 0,
    }

    if dawn_data:
        data["dawn_hours"] = dawn_data

    prompt = f"""건설현장 호이스트 혼잡도 + 대기시간 교차 분석입니다.

데이터:
{data}

건설현장 컨텍스트:
- 새벽(00~05시): 대기시간이 길어도 혼잡도가 낮으면 → 실제 대기 아님 (호이스트 근처 체류 후 탑승)
- 출근 시간(07~08시): 대기시간 짧아도 혼잡도 높으면 → 실제 대기. 병목 발생.
- 혼잡도 높음 + 대기시간 높음 = 심각한 병목 → 호이스트 추가 투입 필요
- 혼잡도 낮음 + 대기시간 높음 = BLE 센서 특성 또는 작업 대기

규칙:
- [분석] 혼잡도 x 대기시간 교차 패턴 2-3개 발견
- [인사이트] 각 패턴의 실제 의미 (실제 대기 vs 센서 노이즈)
- [제안] 데이터 해석 시 주의점 또는 개선 방안
- 80단어 이내 한국어
- 새벽 시간 데이터가 있으면 반드시 별도 해석"""

    return _call(prompt, max_tokens=500)


def generate_safety_insight(
    overcrowding_events: List[Dict],
    night_operations: List[Dict],
    fatigue_indicators: Optional[Dict] = None,
) -> Optional[str]:
    """
    안전 관련 인사이트 생성.

    Args:
        overcrowding_events: 과적 이벤트 [{hour, hoist, passengers, capacity}]
        night_operations: 야간 운행 [{hour, trips, passengers}]
        fatigue_indicators: 피로도 지표 (선택)
    """
    # 익명화
    anon_overcrowding = []
    for e in overcrowding_events[:5]:  # 최대 5개
        anon_overcrowding.append({
            "hour": e.get("hour"),
            "hoist": anonymize_hoist(e.get("hoist", "")),
            "passengers": e.get("passengers"),
            "capacity": e.get("capacity", 25),
        })

    data = {
        "overcrowding_events": anon_overcrowding,
        "overcrowding_count": len(overcrowding_events),
        "night_operations": night_operations,
    }

    if fatigue_indicators:
        data["fatigue_indicators"] = fatigue_indicators

    prompt = f"""건설현장 호이스트 안전 분석입니다.

데이터:
{data}

건설현장 컨텍스트:
- 호이스트 정원: 25~30명 (현장마다 다름)
- 과적 시 추락 위험 + 장비 마모 가속화
- 야간 운행: 시야 확보 어려움, 피로도 증가
- 작업자 피로도 = 이동 빈도 + 대기시간 누적 관련

규칙:
- [분석] 안전 위험 요소 1-2개 식별
- [인사이트] 위험 수준과 영향
- [제안] 구체적 안전 조치 1-2개
- 50단어 이내 한국어
- 과적이 없으면 안전한 상태라고 명시"""

    return _call(prompt, max_tokens=350)


def generate_daily_highlight_insight(
    today_stats: Dict,
    yesterday_stats: Optional[Dict],
    week_avg: Optional[Dict],
) -> Optional[str]:
    """
    종합현황 탭: 오늘의 핵심 인사이트 (전일/주간 비교).

    Args:
        today_stats: 오늘 통계 {trips, passengers, peak_hour, avg_ci, max_pax}
        yesterday_stats: 어제 통계 (동일 구조, 선택)
        week_avg: 주간 평균 (선택)
    """
    data = {
        "today": today_stats,
    }

    if yesterday_stats:
        data["yesterday"] = yesterday_stats
        data["trip_change_pct"] = round(
            (today_stats.get("trips", 0) - yesterday_stats.get("trips", 1)) /
            max(yesterday_stats.get("trips", 1), 1) * 100, 1
        )

    if week_avg:
        data["week_avg"] = week_avg
        data["vs_week_avg_pct"] = round(
            (today_stats.get("passengers", 0) - week_avg.get("passengers", 1)) /
            max(week_avg.get("passengers", 1), 1) * 100, 1
        )

    prompt = f"""건설현장 호이스트 오늘의 핵심 인사이트를 생성해주세요.

데이터:
{data}

건설현장 컨텍스트:
- 호이스트 운행 패턴은 날짜별로 유사 (구조적)
- 전일 대비 큰 변화 → 특수 상황 (자재 반입, 콘크리트 타설 등)
- 주간 평균 대비 10% 이상 증가 → 주의 필요

규칙:
- 3~5개 핵심 포인트만 짧게
- 각 포인트 15자 이내
- bullet point 형식
- 전일/주간 비교 데이터가 있으면 변화율 언급
- 특이점 없으면 "정상 운영" 명시"""

    return _call(prompt, max_tokens=300)


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
