# 팩터 계산 규칙

## 팩터 가중치 (기본값)

| 팩터 | 가중치 | 구성 요소 |
|------|--------|-----------|
| Value | 40% | PER, PBR, PSR, 배당수익률 |
| Momentum | 30% | 1M/3M/6M 수익률, 52주 고점 대비 |
| Quality | 30% | ROE, 부채비율, 영업이익률, 이익성장률 |

## Value 팩터 계산

### PER (주가수익비율)
```python
# 계산
per = current_price / eps

# 점수화 (낮을수록 좋음 - 역순위)
# 0 이하, 100 이상 제외 (수익 없음 또는 비정상)
if 0 < per <= 100:
    score = (100 - percentile_rank) / 100
```

### PBR (주가순자산비율)
```python
# 계산
pbr = current_price / bps

# 점수화 (낮을수록 좋음 - 역순위)
# 0 이하 제외 (자본잠식)
if pbr > 0:
    score = (100 - percentile_rank) / 100
```

### PSR (주가매출비율)
```python
# 계산
psr = market_cap / revenue

# 점수화 (낮을수록 좋음 - 역순위)
score = (100 - percentile_rank) / 100
```

### 배당수익률
```python
# 계산
div_yield = dps / current_price * 100

# 점수화 (높을수록 좋음)
score = percentile_rank / 100
```

### Value 합성 점수
```python
value_score = (
    per_score * 0.30 +
    pbr_score * 0.30 +
    psr_score * 0.20 +
    div_score * 0.20
)
```

## Momentum 팩터 계산

### 기간별 수익률
```python
# 1개월 수익률
return_1m = (current - price_1m_ago) / price_1m_ago

# 3개월 수익률
return_3m = (current - price_3m_ago) / price_3m_ago

# 6개월 수익률
return_6m = (current - price_6m_ago) / price_6m_ago

# 최근 1개월 제외 (단기 과열 방지)
momentum = return_6m - return_1m  # 순수 추세
```

### 52주 고점 대비
```python
# 52주 고점
high_52w = max(prices[-252:])

# 고점 대비 비율
from_high = current / high_52w

# 점수화 (고점에 가까울수록 높은 점수)
score = from_high  # 0.0 ~ 1.0
```

### Momentum 합성 점수
```python
momentum_score = (
    return_1m_score * 0.15 +
    return_3m_score * 0.25 +
    return_6m_score * 0.35 +
    from_high_score * 0.25
)
```

## Quality 팩터 계산

### ROE (자기자본이익률)
```python
# 계산
roe = net_income / equity * 100

# 점수화 (높을수록 좋음)
# 음수 제외
if roe > 0:
    score = percentile_rank / 100
```

### 부채비율
```python
# 계산
debt_ratio = total_debt / equity * 100

# 점수화 (낮을수록 좋음 - 역순위)
# 200% 이상 경고
score = (100 - percentile_rank) / 100
```

### 영업이익률
```python
# 계산
op_margin = operating_income / revenue * 100

# 점수화 (높을수록 좋음)
if op_margin > 0:
    score = percentile_rank / 100
```

### 이익성장률
```python
# 계산 (YoY)
growth = (current_earnings - prev_earnings) / abs(prev_earnings) * 100

# 점수화 (높을수록 좋음)
score = percentile_rank / 100
```

### Quality 합성 점수
```python
quality_score = (
    roe_score * 0.35 +
    debt_score * 0.25 +
    margin_score * 0.20 +
    growth_score * 0.20
)
```

## 합성 점수 계산

### Z-Score 정규화
```python
def normalize_zscore(values):
    mean = np.mean(values)
    std = np.std(values)
    return [(v - mean) / std for v in values]
```

### 최종 합성 점수
```python
composite = (
    value_zscore * 0.40 +
    momentum_zscore * 0.30 +
    quality_zscore * 0.30
)

# 0-100 스케일 변환
final_score = (composite - min) / (max - min) * 100
```

## 필터링 규칙

### 제외 종목
```python
EXCLUDE_CONDITIONS = [
    per <= 0,           # 적자 기업
    per > 100,          # PER 비정상
    pbr <= 0,           # 자본잠식
    debt_ratio > 300,   # 과다 부채
    volume < 1000,      # 거래량 부족
    market_cap < 1000,  # 시가총액 1000억 미만
]
```

### 섹터 분산
```python
# 섹터당 최대 비중: 30%
# 섹터당 최대 종목: target_count // 4
# 최소 섹터 수: 3개
```

## 점수 범위 및 해석

| 점수 | 해석 |
|------|------|
| 80-100 | 최상위 (매수 우선) |
| 60-79 | 상위 (편입 고려) |
| 40-59 | 중립 |
| 20-39 | 하위 (편입 비권장) |
| 0-19 | 최하위 (제외) |
