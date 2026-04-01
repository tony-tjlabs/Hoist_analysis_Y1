# 배포 보안 가이드

> **목적**: GitHub Public 배포 시 핵심 로직 보호
> **원칙**: **결과(캐시)만 배포, 로직은 비공개**

---

## 1. 보안 원칙

### Dev 환경 (로컬 전용)
- Raw CSV 데이터 처리
- Multi-evidence Classification 실행
- 전처리 → Parquet 캐시 생성
- **이 환경에서만** `src/analysis/`, `src/data/loader.py` 실행

### Release 환경 (GitHub Public)
- 전처리된 **캐시 데이터(Parquet)만** 포함
- UI 코드 + 차트 코드만 공개
- **CLOUD_MODE=true** → 전처리 기능 비활성화
- 사용자는 결과만 열람 가능

---

## 2. 파일 분류

### 공개 가능 (Release에 포함)
```
main.py                      ← Streamlit 진입점
src/tabs/*.py                ← UI 탭 (시각화 전용)
src/ui/*.py                  ← 차트, 컴포넌트, 스타일
src/utils/config.py          ← 기본 설정 (★ 분류 파라미터 제거 버전)
src/utils/constants.py       ← UI 상수
src/utils/converters.py      ← 타입 변환 유틸
src/data/schema.py           ← 데이터 스키마 (구조만)
src/data/cache_manager.py    ← 캐시 로드 전용
src/analysis/metrics.py      ← 집계 메트릭 (단순 통계)
data/cache/*.parquet         ← 전처리된 결과
requirements.txt
.streamlit/config.toml
```

### 비공개 (절대 배포 금지)
```
src/analysis/passenger_classifier.py   ← ★ 핵심 분류 로직
src/analysis/trip_extractor.py         ← Trip 추출 알고리즘
src/analysis/floor_estimator.py        ← 층 추정 알고리즘
src/data/loader.py                     ← Raw CSV 로더
src/tabs/pipeline_tab.py               ← 전처리 파이프라인 UI
docs/CLASSIFICATION_ALGORITHM.md       ← 알고리즘 문서
docs/DEPLOY_SECURITY.md                ← 이 문서
.artifacts/                            ← 에이전트 산출물
Y1_Hoist_Data_*/                       ← 원본 데이터
```

---

## 3. Release용 config.py

Release 배포 시 `config.py`에서 **분류 파라미터 제거**:

```python
# Release 버전 (파라미터 노출 방지)
CLOUD_MODE = True  # 항상 True

# 아래 파라미터들은 Release에서 제거
# EVIDENCE_WEIGHTS = {...}          ← 삭제
# CLASSIFICATION_THRESHOLDS = {...} ← 삭제
# HIGH_RSSI_THRESHOLD = ...         ← 삭제
# MIN_RSSI_DURATION_RATIO = ...     ← 삭제
```

---

## 4. Release용 pipeline_tab.py

Release에서는 전처리 기능 비활성화:

```python
def render_pipeline_tab(...):
    st.info("Cloud Mode: 사전 처리된 데이터를 사용합니다.")
    # 전처리 버튼 없음
    # 캐시 로드만 가능
```

---

## 5. .gitignore 구성

### Dev .gitignore (현재 SandBox)
```
# Raw data
Y1_Hoist_Data_*/

# Credentials
*.json
!.streamlit/*.json
.env

# Cache (Dev에서는 gitignore)
data/cache/

# Artifacts
.artifacts/
```

### Release .gitignore
```
# 핵심 로직 (있으면 안됨)
src/analysis/passenger_classifier.py
src/analysis/trip_extractor.py
src/analysis/floor_estimator.py
src/data/loader.py
src/tabs/pipeline_tab.py

# Raw data
Y1_Hoist_Data_*/

# Dev 문서
docs/CLASSIFICATION_ALGORITHM.md
docs/DEPLOY_SECURITY.md
.artifacts/

# Credentials
.env
*.json
!.streamlit/*.json
```

---

## 6. 배포 스크립트 (prepare_release.sh)

```bash
#!/bin/bash
# Dev → Release 복사 스크립트
# 핵심 로직을 제외하고 배포 가능한 파일만 복사

SRC="SandBox/Hoist_Analysis_Y1"
DST="Release/Hoist_Analysis_Y1"

# 1. 구조 생성
mkdir -p $DST/{src/{tabs,ui,utils,data,analysis},data/cache,.streamlit}

# 2. UI/표시 코드 복사
cp $SRC/main.py $DST/
cp $SRC/src/__init__.py $DST/src/
cp $SRC/src/tabs/__init__.py $DST/src/tabs/
cp $SRC/src/tabs/overview_tab.py $DST/src/tabs/
cp $SRC/src/tabs/hoist_tab.py $DST/src/tabs/
cp $SRC/src/tabs/floor_tab.py $DST/src/tabs/
cp $SRC/src/tabs/passenger_tab.py $DST/src/tabs/
# pipeline_tab.py는 스텁 버전으로 대체
cp $SRC/src/ui/*.py $DST/src/ui/
cp $SRC/src/utils/*.py $DST/src/utils/
cp $SRC/src/data/__init__.py $DST/src/data/
cp $SRC/src/data/schema.py $DST/src/data/
cp $SRC/src/data/cache_manager.py $DST/src/data/

# 3. 메트릭 (단순 집계만)
cp $SRC/src/analysis/__init__.py $DST/src/analysis/
cp $SRC/src/analysis/metrics.py $DST/src/analysis/

# 4. 캐시 데이터 복사
cp $SRC/data/cache/*.parquet $DST/data/cache/
cp $SRC/data/cache/cache_meta.json $DST/data/cache/

# 5. 설정
cp $SRC/.streamlit/config.toml $DST/.streamlit/
cp $SRC/requirements.txt $DST/

# 6. config.py에서 분류 파라미터 제거
sed -i '' '/EVIDENCE_WEIGHTS/,/^}/d' $DST/src/utils/config.py
sed -i '' '/CLASSIFICATION_THRESHOLDS/,/^}/d' $DST/src/utils/config.py
sed -i '' '/HIGH_RSSI_THRESHOLD/d' $DST/src/utils/config.py
sed -i '' '/MIN_RSSI_DURATION_RATIO/d' $DST/src/utils/config.py

# 7. CLOUD_MODE 강제 True
sed -i '' 's/CLOUD_MODE = .*/CLOUD_MODE = True/' $DST/src/utils/config.py

echo "Release 준비 완료: $DST"
echo "핵심 로직 파일 제외 확인:"
ls $DST/src/analysis/
```

---

## 7. 체크리스트

배포 전 반드시 확인:

- [ ] `src/analysis/passenger_classifier.py` 가 Release에 **없는지**
- [ ] `src/analysis/trip_extractor.py` 가 Release에 **없는지**
- [ ] `src/analysis/floor_estimator.py` 가 Release에 **없는지**
- [ ] `src/data/loader.py` 가 Release에 **없는지**
- [ ] `config.py`에서 `EVIDENCE_WEIGHTS` 등 파라미터가 **제거**되었는지
- [ ] `CLOUD_MODE = True` 로 설정되었는지
- [ ] `Y1_Hoist_Data_*/` 원본 데이터가 **없는지**
- [ ] `docs/CLASSIFICATION_ALGORITHM.md` 가 **없는지**
- [ ] `.artifacts/` 가 **없는지**
- [ ] `data/cache/*.parquet` 가 **있는지** (결과 데이터)
- [ ] Streamlit이 캐시만으로 정상 동작하는지 확인
