# Hoist Analysis Y1 - Cloud Release

건설현장 호이스트 운행 분석 대시보드

## 배포 방법 (Streamlit Cloud)

1. GitHub에 이 폴더를 push
2. Streamlit Cloud에서 deploy
3. secrets.toml에 APP_PASSWORD 설정:
   ```toml
   APP_PASSWORD = "your_password_here"
   ```
4. (선택) LLM 기능 사용 시:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run main.py
```

기본 비밀번호: `wonderful2$` (환경변수 APP_PASSWORD로 변경 가능)

## 포함 데이터

- `data/cache/20260326_trips.parquet` - 운행 데이터 (1,606건)
- `data/cache/20260326_passengers.parquet` - 탑승자 데이터 (4,669건)
- `data/cache/20260326_sward.parquet` - S-Ward 센서 데이터

## 탭 구성

1. **종합 현황** - KPI, 건물별 현황, 혼잡도 인사이트
2. **운행 분석** - 듀얼 뷰, 시간대별 혼잡도, 호이스트 비교
3. **탑승자 분석** - Multi-Evidence 분류, 업체별 분포
4. **층별 분석** - Sankey 다이어그램, 유입/유출 분석

## 보안

- 이 버전은 분류/추출 알고리즘을 포함하지 않습니다
- 캐시된 결과 데이터만 사용합니다
- 대기시간 분석은 T-Ward 데이터가 없어 비활성화됩니다

---
TJLABS Research | v2.0 Cloud Release
