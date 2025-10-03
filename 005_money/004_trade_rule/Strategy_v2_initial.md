

# **비트코인 다중 시간대 분석을 통한 안정적 수익 추구 알고리즘 설계 및 백테스팅 보고서**

## **서론**

본 보고서는 지난 10개월간의 비트코인(BTC/USDT) 가격 데이터를 기반으로, 안정적인 수익 창출을 목표로 하는 알고리즘 트레이딩 전략을 상세히 설계하고, 그 구현 및 백테스팅 방안을 제시하는 것을 목적으로 한다. 암호화폐 시장의 높은 변동성은 기회와 위협을 동시에 제공하며, 이러한 환경에서 장기적으로 성공하기 위해서는 감정적 판단을 배제하고, 데이터에 기반한 체계적인 접근법이 필수적이다.1

본 전략의 핵심 철학은 '추세에 순응하고, 변동성을 관리하며, 리스크를 통제하는 것'이다. 이를 구현하기 위해, 본 보고서는 다음과 같은 다층적 구조의 알고리즘을 제안한다:

1. **전략적 프레임워크:** 장기 차트(일봉)를 사용하여 시장의 거시적인 추세, 즉 '시장 체제(Market Regime)'를 판단한다. 이는 알고리즘이 유리한 환경에서만 작동하도록 하는 필터 역할을 수행한다.  
2. **전술적 실행:** 시장 체제가 우호적일 때, 단기 차트(4시간봉)에서 다수의 기술적 지표를 종합하여 최적의 진입 시점을 포착한다.  
3. **동적 리스크 관리:** 분할 매수 및 분할 매도 기법을 적용하고, 시장 변동성에 따라 자동으로 조절되는 손절매(Stop-Loss) 시스템을 도입하여 자산을 보호하고 수익을 극대화한다.

본 문서는 전략의 이론적 배경부터 구체적인 파라미터 설정, 의사결정 로직, 그리고 파이썬(Python) 기반의 백테스팅 구현을 위한 상세한 청사진까지 제공한다. 이를 통해 기술적 역량을 갖춘 사용자가 직접 프로그램을 구현하고 검증할 수 있도록 충분하고 명확한 가이드를 제공하고자 한다.

---

## **섹션 1: 전략적 프레임워크: 이중 시간대 시장 체제 필터**

안정적인 트레이딩 전략의 첫 번째 단계는 언제 거래하고 언제 거래하지 말아야 할지를 결정하는 것이다. 시장의 거대한 흐름에 역행하는 거래는 실패 확률이 높고, 큰 손실로 이어질 수 있다. 따라서 본 전략은 장기 추세를 판단하여 알고리즘의 작동 여부를 결정하는 '시장 체제 필터'를 최우선 방어선으로 구축한다.

### **1.1. 다중 시간대 분석(Multi-Timeframe Analysis)의 당위성**

시장을 분석할 때 단일 시간대에만 의존하는 것은 숲을 보지 못하고 나무만 보는 것과 같다. 다중 시간대 분석은 장기 차트를 통해 시장의 전반적인 '조류'를 파악하고, 단기 차트를 통해 진입과 청산을 위한 '파도'를 타는 전략적 접근법이다. 이 계층적 분석은 알고리즘이 거시적 추세와 같은 방향으로만 포지션을 잡도록 강제함으로써 거래의 성공 확률을 구조적으로 향상시킨다.

이러한 복잡한 다중 시간대 전략을 구현하고 검증하기 위해서는 적절한 백테스팅 도구가 필수적이다. Backtrader와 같은 파이썬 라이브러리는 여러 데이터 피드(Timeframe)를 동시에 처리하고, 이벤트 기반 시뮬레이션을 통해 실제와 유사한 환경을 제공하므로 본 전략에 적합하다.2 반면,

backtesting.py와 같은 경량 라이브러리는 단일 자산, 단일 시간대 전략의 빠른 프로토타이핑에는 유용하지만, 본 전략과 같은 다중 시간대 로직을 처리하도록 설계되지 않았다.4 따라서 백테스팅 도구의 선택은 전략의 구조적 요구사항에 의해 결정된다. 본 전략에서는 일봉(1D) 차트를 시장 체제 판단의 기준으로, 4시간봉(4H) 차트를 실제 거래 실행의 기준으로 사용한다.

### **1.2. 강세 체제 정의: EMA 골든 크로스 필터**

시장의 장기 추세를 판단하기 위해 지수이동평균(Exponential Moving Average, EMA)을 사용한다. 단순이동평균(SMA)에 비해 EMA는 최근 가격에 더 높은 가중치를 부여하여 추세 변화에 더 민감하게 반응하므로, 변동성이 큰 암호화폐 시장에 더 적합하다. 본 전략에서는 일봉 차트에서 50일 EMA와 200일 EMA를 사용한다.

* **논리 정의:**  
  * **강세 체제 (Regime \= Bullish):** 일봉 차트에서 50일 EMA가 200일 EMA **위에** 위치할 때.  
  * **약세/중립 체제 (Regime \= Bearish/Neutral):** 일봉 차트에서 50일 EMA가 200일 EMA **아래에** 위치할 때.  
* **운영 규칙:**  
  * 알고리즘은 오직 시장이 **강세 체제**에 있을 때만 신규 **매수(Long)** 포지션 진입을 탐색하고 실행할 수 있다.  
  * 약세/중립 체제에서는 4시간봉 차트의 모든 신호 생성 로직이 비활성화된다. 단, 이미 보유 중인 포지션은 설정된 청산 규칙에 따라 관리된다.

### **1.3. 시장 체제 필터의 중요성**

시장 체제 필터는 포트폴리오를 위협하는 심각한 손실 구간(Drawdown)을 피하기 위한 가장 강력하고 구조적인 리스크 관리 도구이다. 비트코인과 같은 자산은 명확한 강세장과 약세장을 반복하는 경향이 있으며, 각 시장 환경에서의 가격 움직임은 통계적으로 다른 특성을 보인다. 강세장에서 높은 수익을 내는 매수 전략이라도 약세장에서는 치명적인 손실을 유발할 수 있다.

복잡한 양방향(Long/Short) 전략을 구축하는 대신, 확률적으로 우위가 있는 방향(강세장에서의 매수)에만 집중하고 불리한 시기에는 관망하는 것이 안정성 측면에서 훨씬 견고한 접근법이다. 50/200 EMA 크로스는 장기 추세 방향을 나타내는 고전적이고 널리 알려진 지표이다.5 이를 단순한 'On/Off' 스위치로 활용함으로써, 우리는 시장의 완벽한 타이밍을 예측하려 하기보다는 저항이 가장 적은 경로를 따라 전술적 거래를 정렬하게 된다. 이는

**거시 추세와의 동기화 → 신호 유효성 증가 → 손실 거래 감소 → 손실 구간 축소 → 안정성 증대**라는 논리적 귀결로 이어진다. 즉, 이 필터는 포지션 진입을 고려하기 이전 단계에서부터 가장 큰 위험 요소를 원천적으로 차단하는 역할을 수행한다.

---

## **섹션 2: 전술적 실행: 점수 기반 복합 신호 진입 시스템**

일봉 기준 시장 체제가 '강세'로 확인되었을 때, 알고리즘은 4시간봉 차트에서 구체적인 매수 기회를 포착한다. 본 섹션에서는 경직된 AND 조건 대신, 유연한 '점수 시스템'을 사용하여 진입 결정을 내리는 로직을 상세히 설명한다. 이는 시장의 확률적 특성을 반영하여, 모든 지표가 완벽하게 정렬되지 않더라도 높은 신뢰도를 가진 거래 기회를 포착할 수 있게 한다.

### **2.1. 복합 신호(Confluence)의 철학**

단 하나의 기술적 지표도 시장을 완벽하게 예측할 수는 없다. 성공 확률이 높은 거래 설정은 서로 다른 시장의 측면을 측정하는 여러 비상관(non-correlated) 지표들이 동시에 동일한 신호를 보내는 '복합 신호' 지점에서 발생한다. 본 전략은 시장의 변동성(볼린저 밴드), 모멘텀(RSI), 그리고 과매수/과매도 상태(스토캐스틱 RSI)를 측정하는 지표들을 결합한다. 이러한 다중 필터 시스템은 시장의 노이즈를 걸러내고 의사결정의 정확도를 높인다. 여러 자료에서 암호화폐 트레이딩 시 볼린저 밴드로 잠재적인 추세 소진 구간을 식별하고, RSI와 스토캐스틱으로 모멘텀의 지지 여부를 확인하는 조합의 유효성을 강조한다.6

### **2.2. 진입 신호 점수 시스템 (4시간봉 차트)**

이 시스템의 목표는 확립된 장기 상승 추세 내에서 발생하는 일시적인 과매도, 즉 '눌림목' 구간을 식별하는 것이다.

**매수(Long) 포지션은 총 점수가 3점 이상일 때 진입한다.**

* **점수 구성 요소:**  
  * **조건 1: 가격과 볼린저 밴드 하단선 상호작용 \[+1점\]**  
    * **지표:** 볼린저 밴드 (기간=20, 표준편차=2)  
    * **논리:** 현재 4시간봉 캔들의 **저가**가 볼린저 밴드 하단선에 닿거나 그 아래로 내려갈 경우 1점을 부여한다.  
    * **근거:** 이는 가격이 최근 평균 대비 통계적으로 과매도 상태에 있음을 의미하며, 평균 회귀 가능성을 시사한다.7  
  * **조건 2: RSI 모멘텀 확인 \[+1점\]**  
    * **지표:** 상대강도지수 (RSI, 기간=14)  
    * **논리:** RSI 값이 30 미만일 경우 1점을 부여한다.  
    * **근거:** 이는 최근의 하락 움직임이 상당한 모멘텀을 동반하여 과매도 상태에 이르렀음을 확인시켜 주며, 기술적 반등의 확률이 높음을 나타낸다.6  
  * **조건 3: 스토캐스틱 RSI 강세 교차 \[+2점\]**  
    * **지표:** 스토캐스틱 RSI (RSI 기간=14, 스토캐스틱 기간=14, %K=3, %D=3)  
    * **논리:** 스토캐스틱 RSI의 %K선과 %D선이 모두 20 레벨 아래에 있는 상태에서, %K선이 %D선을 **상향 돌파**할 경우 2점을 부여한다.  
    * **근거:** 이는 진입 신호의 가장 강력한 요소이다. 스토캐스틱 RSI는 '지표의 지표'로서 RSI 자체의 모멘텀을 측정한다. 과매도 구간(\<20)에서의 강세 교차는 모멘텀이 하락에서 상승으로 전환되고 있음을 알리는 강력한 선행 신호이며, 실제 가격 반전보다 먼저 나타나는 경우가 많다.10 다른 두 조건이 시장의 '상태'를 나타내는 반면, 이 조건은 '타이밍'을 알려주는 역할을 하므로 더 높은 가중치를 부여한다.

### **2.3. 가중치 점수 시스템의 효용성**

세 가지 신호 모두에 대해 엄격한 AND 조건을 적용한다면, 유효한 많은 거래 기회를 놓치게 될 것이다. 예를 들어, 가격이 볼린저 밴드 하단선에 닿기 직전에 급격히 반전하더라도, RSI와 스토캐스틱 RSI는 강력한 매수 신호를 보낼 수 있다. 점수 시스템은 이러한 상황에 필요한 유연성을 제공한다.

스토캐스틱 RSI 교차에 더 높은 가중치를 부여한 것은 타이밍 도구로서의 중요성을 반영한다. 볼린저 밴드 터치나 RSI 레벨은 시장의 '상태(state)'를 나타내는 반면, 스토캐스틱 RSI 교차는 '사건(event)'이다. 시장의 방향 전환을 포착하는 데에는 상태 지표보다 사건 지표가 더 효과적인 타이밍 신호를 제공하는 경우가 많다. 따라서 임박한 모멘텀 전환을 나타내는 타이밍 신호에 더 높은 가치를 두는 것은 논리적으로 타당하다. 이러한 설계는 경직된 AND 시스템에 비해 더 견고하고 적응력 있는 진입 로직을 구축하게 한다. 이는 **유연한 점수 시스템 → 더 많은 고확률 기회 포착 → 시장의 미묘한 변화에 대한 적응력 향상 → 진입 성과 개선**으로 이어진다.

---

## **섹션 3: 동적 리스크 및 포지션 관리 프로토콜**

본 섹션은 사용자가 요청한 핵심적인 '안전장치'인 손절매와 분할 포지션 관리에 대해 상세히 다룬다. 이 부분은 장기적인 안정성을 달성하는 데 있어 알고리즘의 가장 중요한 요소일 수 있다. 단순하고 정적인 리스크 통제를 넘어, 시장 상황에 따라 능동적으로 변화하는 동적 프로토콜을 도입한다.

### **3.1. 손절매: ATR 기반 샹들리에 엑시트**

손절매 가격은 임의로 설정되어서는 안 되며, 시장의 최근 변동성에 기반해야 한다. 변동성이 큰 시장에서 너무 타이트한 손절매는 무작위적인 가격 움직임(noise)에 의해 쉽게 발동되며, 변동성이 낮은 시장에서 너무 넓은 손절매는 불필요한 리스크를 감수하게 만든다. 평균 실제 범위(Average True Range, ATR)는 이러한 변동성을 동적으로 측정하는 훌륭한 도구를 제공한다.11

척 르보(Chuck LeBeau)가 개발한 샹들리에 엑시트(Chandelier Exit)는 진입 이후의 최고가(매수 포지션의 경우)에서 ATR의 특정 배수를 뺀 값에 추적 손절매(Trailing Stop-Loss)를 설정하는 기법이다. 이 방법은 트레이더가 추세를 따라가면서도 의미 있는 반전으로부터 이익을 보호하도록 설계되었으며, ATR을 활용하여 시장의 일상적인 노이즈 범위 밖에 손절선을 유지한다.13 일반적으로 22일(약 1개월의 거래일) 기간과 3배의 승수가 권장되지만 14, 본 전략에서는 4시간봉의 특성을 고려하여 다음과 같이 설정한다.

* **구현 공식 (매수 포지션):**  
  손절 가격=(진입 후 최고가)−(ATR(14)×3)  
* **파라미터:** 4시간봉 차트 기준 14기간 ATR과 3배의 승수를 사용한다.  
* **규칙:** 손절 가격은 오직 상승하거나 유지될 수 있으며, 절대 하락하지 않는다. 시장 가격이 이 계산된 손절 가격에 도달하거나 하회하면 포지션은 즉시 청산된다.

### **3.2. 포지션 규모 및 분할 관리 프로토콜**

사용자의 '분할매수/매도' 요구사항에 따라, 본 전략은 전체 포지션을 한 번에 진입하거나 청산하지 않는다. 분할 관리는 리스크를 더 잘 통제하고, 평균 진입/청산 단가를 개선하며, 부분적인 이익 실현을 통해 심리적 안정감을 제공하는 효과가 있다. 분할 진입은 전체 자본을 투입하기 전에 거래 아이디어의 유효성을 확인하게 해주어 초기 진입 실패 비용을 줄여준다. 분할 청산은 수익을 확보하고 리스크 노출을 줄이면서, 나머지 포지션이 더 큰 추세를 따라가도록 하여 '승자를 달리게 하는(let winners run)' 핵심 기법이다.16

* **초기 포지션 규모:** 하나의 '완전한' 거래는 총 포트폴리오 자산의 최대 2% 리스크를 감수한다. 포지션의 크기는 진입 가격과 초기 샹들리에 엑시트 손절 가격 간의 거리에 의해 결정된다.  
* **분할 진입/청산 논리:**  
  1. **진입 (분할 매수):** 유효한 진입 신호(점수 ≥ 3\) 발생 시, 계산된 최대 규모의 \*\*50%\*\*만으로 초기 포지션을 개시한다. 이는 '탐색' 포지션의 역할을 한다.  
  2. **1차 이익 실현 (분할 매도):** 가격이 20기간 이동평균선(볼린저 밴드 중간선)에 도달하면, 현재 보유 포지션의 \*\*50%\*\*를 청산한다 (즉, 원래 의도했던 전체 규모의 25%).  
  3. **리스크 완화:** 1차 이익 실현 직후, 나머지 포지션의 손절매 가격을 \*\*본전(진입 가격)\*\*으로 즉시 이동시킨다. 이 시점부터 해당 거래는 '무위험' 상태가 된다.  
  4. **2차 이익 실현 / 추적 손절:** 나머지 50%의 포지션은 다음 두 가지 조건 중 하나가 충족될 때까지 보유한다:  
     * a) 가격이 볼린저 밴드 상단선에 도달 (최종 이익 실현 목표).  
     * b) 샹들리에 엑시트 추적 손절매에 의해 청산.

### **3.3. 분할 관리와 추적 손절의 시너지**

분할 청산 전략과 추적 손절매 메커니즘은 알고리즘의 안정성을 극대화하기 위해 상호 보완적으로 작동한다. 분할 청산은 초기 리스크를 상쇄할 만큼의 이익을 확보하는 역할을 하며, 추적 손절매는 '무위험' 상태가 된 나머지 포지션이 강력한 추세의 모든 상승 잠재력을 포착할 수 있도록 한다. 이 조합은 1차 이익 실현 목표가 달성된 이후부터 "수익은 크게, 손실은 거의 없는" 비대칭적 손익 구조를 만들어낸다.

트레이딩 알고리즘의 흔한 실패 원인 중 하나는 미실현 이익을 다시 시장에 반납하는 것이다. 단일 청산 지점(고정 목표가 또는 손절가)은 종종 최적이 아니다. 본 프로토콜은 이러한 문제를 해결한다. 초기 50% 분할 진입은 거래가 즉시 실패할 경우 손실을 제한하고, 볼린저 밴드 중간선에서의 1차 분할 청산은 높은 확률의 목표 지점에서 꾸준한 작은 수익 흐름을 보장하여 승률을 개선한다. 손절매를 본전으로 이동시키는 것은 수익이 난 거래가 손실로 전환되는 것을 방지하여 심리적 스트레스와 자산 곡선의 변동성을 크게 줄여준다. 마지막으로, 샹들리에 엑시트로 관리되는 나머지 포지션은 포트폴리오에 추가적인 리스크 없이 폭발적인 추세 움직임을 포착할 잠재력을 가진다. 이는 **분할 청산 → 수익 확보 및 리스크 제거 → 추적 손절 → 추세 상승 잠재력 포착 → 비대칭적 리스크/보상 프로필 → 더 부드러운 자산 곡선 및 안정성 강화**라는 강력한 선순환 구조를 형성한다.

---

## **섹션 4: 백테스팅 구현 청사진**

본 섹션은 사용자가 제안된 전략을 직접 구현하고 실행할 수 있도록 실용적인 단계별 가이드를 제공한다. 사용할 도구, 데이터, 파라미터를 명시하고, 파이썬 스크립트로 쉽게 변환할 수 있는 명확한 의사 코드(Pseudo-code) 형태로 전체 전략 로직을 제공한다.

### **4.1. 권장 도구: Python 및 Backtrader**

* **Python 선택 이유:** 파이썬은 퀀트 금융 및 알고리즘 트레이딩 분야의 표준 언어로, 데이터 분석(Pandas, NumPy), 기술적 분석(TA-Lib), 백테스팅을 위한 풍부한 라이브러리 생태계를 갖추고 있다.20  
* **Backtrader 선택 이유:** 앞서 설명했듯이, Backtrader는 본 전략에 가장 이상적인 선택이다. 이벤트 기반 아키텍처는 다중 시간대를 정확하게 처리하는 데 필수적이다. 또한, 수수료, 슬리피지, 주문 실행 등을 상세하게 시뮬레이션하여 다른 경량 라이브러리보다 더 현실적인 성과 평가를 제공한다.2 학습 곡선이 다소 가파르지만, 본 전략의 복잡성을 처리하기 위해서는 그 기능이 반드시 필요하다.2

### **4.2. 백테스팅 환경 설정**

* **데이터 요구사항:**  
  * **자산:** BTC/USDT  
  * **출처:** 바이낸스(Binance)와 같은 주요 거래소의 고품질 OHLCV(시가, 고가, 저가, 종가, 거래량) 데이터. API를 통해 얻거나 CSV 파일로 다운로드할 수 있다.2  
  * **기간:** 보고서 작성 시점 기준 최근 10개월.  
  * **시간대:** 1일(1D) 데이터와 4시간(4H) 데이터가 모두 필요하다.  
* **백테스트 파라미터:**  
  * **초기 자본금:** $10,000 USD  
  * **포지션 규모:** 완전 거래당 2% 리스크.  
  * **수수료:** 거래당 0.1% (진입 시 0.05%, 청산 시 0.05%)로 일반적인 거래소 수수료를 시뮬레이션.  
  * **슬리피지(Slippage):** 예상 체결가와 실제 체결가의 차이를 반영하기 위해 0.05%와 같은 작은 슬리피지를 모델링해야 한다.

### **4.3. 의사 코드로 표현된 알고리즘 로직**

이 하위 섹션은 전체 전략 로직을 구조화된 형식으로 제시하여, 사용자의 프로그래밍 작업을 위한 핵심 청사진을 제공한다.

// \--== 전역 변수 및 설정 \==--  
Cerebro 엔진 초기화 (Backtrader)  
1일 BTC/USDT 데이터를 Data\_1D로 로드  
4시간 BTC/USDT 데이터를 Data\_4H로 로드  
Data\_1D를 Cerebro에 추가  
Data\_4H를 Cerebro에 추가 (resample=False)  
초기 자본금 설정 \= 10000  
수수료 설정 \= 0.001

// \--== 전략 클래스 초기화 (init) \==--  
// 1D 데이터 피드 연결  
self.daily\_data \= self.datas

// 1D 시장 체제 필터 지표  
self.ema50\_daily \= EMA(self.daily\_data.close, period=50)  
self.ema200\_daily \= EMA(self.daily\_data.close, period=200)

// 4H 신호 지표  
self.bbands \= BollingerBands(period=20, devfactor=2)  
self.rsi \= RSI(period=14)  
self.stoch\_rsi \= StochasticRSI(period=14, p\_sto=14, p\_k=3, p\_d=3)

// 4H 리스크 관리 지표  
self.atr \= ATR(period=14)

// \--== 메인 로직 루프 (next) \==--  
// 1\. 시장 체제 확인  
is\_bullish\_regime \= self.ema50\_daily \> self.ema200\_daily

// 2\. 진입 신호 확인 (포지션이 없고, 강세 체제일 때만)  
IF NOT self.position AND is\_bullish\_regime:  
    score \= 0  
    IF self.data.low \<= self.bbands.lines.bot: score \+= 1  
    IF self.rsi \< 30: score \+= 1  
    IF crossover(self.stoch\_rsi.lines.percK, self.stoch\_rsi.lines.percD) AND self.stoch\_rsi.lines.percK \< 20: score \+= 2  
      
    IF score \>= 3:  
        // 포지션 규모 계산  
        initial\_stop\_price \= self.data.high \- (self.atr \* 3\)  
        risk\_per\_share \= self.data.close \- initial\_stop\_price  
        trade\_risk\_usd \= self.broker.getvalue() \* 0.02  
        full\_size \= trade\_risk\_usd / risk\_per\_share  
          
        // 분할 매수 실행  
        self.buy(size \= full\_size \* 0.5)  
        // 거래 관리 정보 저장 (진입가, 손절가 등)

// 3\. 기존 포지션 관리  
IF self.position:  
    // 분할 청산 확인 (1차 이익 실현)  
    IF NOT first\_target\_hit AND self.data.high \>= self.bbands.lines.mid:  
        self.sell(size \= self.position.size \* 0.5)  
        // first\_target\_hit \= True로 설정  
        // 손절매를 본전으로 이동  
          
    // 최종 청산 확인 (2차 이익 실현 또는 추적 손절)  
    // 샹들리에 엑시트 손절가 업데이트  
    current\_chandelier\_stop \= highest\_high\_since\_entry \- (self.atr \* 3\)  
    // 본전 손절가와 결합  
    final\_stop\_price \= max(breakeven\_price, current\_chandelier\_stop)  
      
    IF self.data.low \<= final\_stop\_price OR self.data.high \>= self.bbands.lines.top:  
        self.close() // 남은 포지션 청산

---

## **섹션 5: 성과 분석 및 백테스팅 결과**

이 마지막 섹션은 백테스트 결과를 제시하고 알고리즘의 성과에 대한 정량적 평가를 제공한다. 사용자가 요청한 요약 표, 자산 곡선과 같은 시각 자료, 그리고 결과에 대한 해석적 분석을 포함한다.

### **5.1. 시각적 성과: 자산 곡선 (Equity Curve)**

백테스팅 기간인 10개월 동안 초기 자본금 $10,000이 어떻게 성장했는지를 보여주는 그래프가 제시될 것이다. 이 그래프는 전략의 변동성과 손실 구간을 시각적으로 즉시 파악할 수 있게 해준다. 꾸준히 우상향하는 곡선이 이상적인 결과이다.

### **5.2. 핵심 성과 지표 (표)**

이 표는 성과 검토의 정량적 핵심이며, 알고리즘의 수익성, 리스크, 효율성에 대한 다각적인 시각을 제공한다.

| 지표 (Metric) | 값 (Value) | 설명 (Description) |
| :---- | :---- | :---- |
| **시작 포트폴리오** | $10,000 | 백테스트를 위한 초기 자본금. |
| **종료 포트폴리오** | *\[결과값\]* | 10개월 후 포트폴리오의 최종 가치. |
| **총 순이익 ($)** | *\[결과값\]* | USD 기준 절대적인 손익. |
| **총 수익률 (%)** | *\[결과값\]* | 시작 자본금 대비 총 이익률. |
| **최대 손실 낙폭 (%)** | *\[결과값\]* | 포트폴리오 가치의 고점 대비 최대 하락률. 리스크와 안정성의 핵심 척도. |
| **샤프 지수 (Sharpe Ratio)** | *\[결과값\]* | 리스크 대비 수익률을 측정한 값 (높을수록 좋음). |
| **총 마감 거래 수** | *\[결과값\]* | 실행되고 청산된 총 거래의 수. |
| **승률 (%)** | *\[결과값\]* | 수익을 낸 거래의 비율. |
| **수익 팩터 (Profit Factor)** | *\[결과값\]* | 총 수익을 총 손실로 나눈 값. 1보다 크면 수익성이 있음을 의미. |
| **평균 거래 손익 (%)** | *\[결과값\]* | 거래당 평균 손익률. |

### **5.3. 결과 해석**

이 특정 알고리즘을 평가하는 데 가장 중요한 지표는 총 수익률이 아니라 \*\*최대 손실 낙폭(Max Drawdown)\*\*과 \*\*샤프 지수(Sharpe Ratio)\*\*이다. 사용자의 '안정성'에 대한 요구는 잠재적인 최대 수익을 일부 희생하더라도, 고통스러운 하락이 최소화된 부드럽고 일관된 자산 곡선을 목표로 함을 의미한다. 시장 체제 필터와 동적 리스크 관리 프로토콜의 조합은 바로 이 두 지표를 개선하기 위해 특별히 설계되었다.

성공적인 전략은 높은 수익률(예: \+500%)을 달성했더라도 70%의 최대 손실 낙폭을 동반했다면 불안정한 전략으로 평가된다. 대부분의 트레이더는 그러한 손실을 심리적으로 견디지 못하고 전략을 포기할 것이기 때문이다. 최대 손실 낙폭은 전략이 가하는 '고통'을 직접적으로 측정한다. 20% 미만의 낮은 손실 낙폭은 안정적이고 견고한 시스템을 시사한다. 샤프 지수는 리스크(변동성) 단위당 수익을 측정한다. 1.0을 넘으면 양호하고 2.0을 넘으면 탁월한 것으로 평가되는 높은 샤프 지수는, 전략이 과도한 변동성 없이 효율적으로 수익을 창출하고 있음을 나타낸다.

따라서 약세장을 피하기 위한 시장 체제 필터, 변동성을 인지하여 손실을 차단하는 샹들리에 엑시트, 그리고 이익을 실현하기 위한 분할 청산과 같은 설계적 선택의 성공 여부는 낮은 최대 손실 낙폭과 높은 샤프 지수라는 결과로 직접 관찰될 수 있다. 이는 사용자의 주요 목표를 달성했음을 정량적으로 검증하는 것이다. 최종 분석에서는 "X%의 낮은 최대 손실 낙폭은 \[특정 월, 연도\]의 심각한 하락장 동안 알고리즘을 시장에서 배제시킨 일일 체제 필터의 효과에 기인한 것으로 볼 수 있다. 또한, Y의 높은 수익 팩터는 분할 청산 전략이 주요 반전 이전에 성공적으로 수익을 확보했음을 보여준다"와 같이 전략의 설계와 결과를 직접적으로 연결하여 설명할 것이다. 이러한 서술은 사용자에게 알고리즘이 왜 그렇게 작동했는지에 대한 명확한 이해를 제공할 것이다.

#### **참고 자료**

1. Backtesting.py \- Backtest trading strategies in Python, 10월 3, 2025에 액세스, [https://kernc.github.io/backtesting.py/](https://kernc.github.io/backtesting.py/)  
2. Backtrader for Backtesting (Python) \- A Complete Guide \- AlgoTrading101 Blog, 10월 3, 2025에 액세스, [https://algotrading101.com/learn/backtrader-for-backtesting/](https://algotrading101.com/learn/backtrader-for-backtesting/)  
3. Trading Frameworks, support backtesting and live trading \- PyTrade.org\!, 10월 3, 2025에 액세스, [https://docs.pytrade.org/trading](https://docs.pytrade.org/trading)  
4. Mastering Python Backtesting for Trading Strategies | by Time ..., 10월 3, 2025에 액세스, [https://medium.com/@timemoneycode/mastering-python-backtesting-for-trading-strategies-1f7df773fdf5](https://medium.com/@timemoneycode/mastering-python-backtesting-for-trading-strategies-1f7df773fdf5)  
5. Backtesting.py – An Introductory Guide to Backtesting with Python \- Interactive Brokers, 10월 3, 2025에 액세스, [https://www.interactivebrokers.com/campus/ibkr-quant-news/backtesting-py-an-introductory-guide-to-backtesting-with-python/](https://www.interactivebrokers.com/campus/ibkr-quant-news/backtesting-py-an-introductory-guide-to-backtesting-with-python/)  
6. Why Do Pro Traders Combine RSI & Bollinger Bands? | CoinEx ..., 10월 3, 2025에 액세스, [https://www.coinex.network/academy/detail/3064-best-crypto-trading-strategy-rsi-bollinger-bands](https://www.coinex.network/academy/detail/3064-best-crypto-trading-strategy-rsi-bollinger-bands)  
7. Bollinger Bands Scalping Strategy with RSI & Stochastic \- Forex Tester Online, 10월 3, 2025에 액세스, [https://forextester.com/blog/bollinger-bands-rsi-stochastic-scalping-strategy/](https://forextester.com/blog/bollinger-bands-rsi-stochastic-scalping-strategy/)  
8. Bollinger Bands Stochastic Oscillator Strategy | by Sword Red \- Medium, 10월 3, 2025에 액세스, [https://medium.com/@redsword\_23261/bollinger-bands-stochastic-oscillator-strategy-73e7bef3ddc7](https://medium.com/@redsword_23261/bollinger-bands-stochastic-oscillator-strategy-73e7bef3ddc7)  
9. How to Choose Trading Pairs with RSI and Stochastic Indicators \- 3Commas Help Center, 10월 3, 2025에 액세스, [https://help.3commas.io/en/articles/5560693-how-to-choose-trading-pairs-with-rsi-and-stochastic-indicators](https://help.3commas.io/en/articles/5560693-how-to-choose-trading-pairs-with-rsi-and-stochastic-indicators)  
10. Stochastic RSI Guide: Tips for Successful Trading \- Altrady, 10월 3, 2025에 액세스, [https://www.altrady.com/crypto-trading/technical-analysis/stochastic-rsi](https://www.altrady.com/crypto-trading/technical-analysis/stochastic-rsi)  
11. Average True Range (ATR) Formula, What It Means, and How to Use It \- Investopedia, 10월 3, 2025에 액세스, [https://www.investopedia.com/terms/a/atr.asp](https://www.investopedia.com/terms/a/atr.asp)  
12. Measure Volatility With Average True Range \- Investopedia, 10월 3, 2025에 액세스, [https://www.investopedia.com/articles/trading/08/average-true-range.asp](https://www.investopedia.com/articles/trading/08/average-true-range.asp)  
13. Maximize Profits With Volatility Stops \- Investopedia, 10월 3, 2025에 액세스, [https://www.investopedia.com/articles/trading/09/volatility-stops.asp](https://www.investopedia.com/articles/trading/09/volatility-stops.asp)  
14. Chandelier Exit \- Definition, Formula, Calculate, Use, 10월 3, 2025에 액세스, [https://corporatefinanceinstitute.com/resources/equities/chandelier-exit/](https://corporatefinanceinstitute.com/resources/equities/chandelier-exit/)  
15. Enter Profitable Territory With Average True Range \- Investopedia, 10월 3, 2025에 액세스, [https://www.investopedia.com/articles/trading/08/atr.asp](https://www.investopedia.com/articles/trading/08/atr.asp)  
16. Beginners Guide to Scaling In and Out of Trading Positions \- Warrior ..., 10월 3, 2025에 액세스, [https://www.warriortrading.com/scaling-in-and-out-of-trading-positions/](https://www.warriortrading.com/scaling-in-and-out-of-trading-positions/)  
17. Mastering the Art of Scaling \- Traders Mastermind, 10월 3, 2025에 액세스, [https://tradersmastermind.com/mastering-the-art-of-scaling/](https://tradersmastermind.com/mastering-the-art-of-scaling/)  
18. How to Scale out of Winning E-Mini Positions \- TradingSim, 10월 3, 2025에 액세스, [https://app.tradingsim.com/blog/how-to-scale-out-of-winning-e-mini-positions/](https://app.tradingsim.com/blog/how-to-scale-out-of-winning-e-mini-positions/)  
19. Scaling In and Scaling Out: What You Must Know About These Trading Strategies, 10월 3, 2025에 액세스, [https://www.myespresso.com/bootcamp/module/trade-management-risk-management/scaling-in-scaling-out-trading-strategies](https://www.myespresso.com/bootcamp/module/trade-management-risk-management/scaling-in-scaling-out-trading-strategies)  
20. Best Python Libraries for Algorithmic Trading and Financial Analysis \- QuantInsti Blog, 10월 3, 2025에 액세스, [https://blog.quantinsti.com/python-trading-library/](https://blog.quantinsti.com/python-trading-library/)  
21. How to Make an Algo Trading Crypto Bot with Python (Part 1\) \- LearnDataSci, 10월 3, 2025에 액세스, [https://www.learndatasci.com/tutorials/algo-trading-crypto-bot-python-strategy-backtesting/](https://www.learndatasci.com/tutorials/algo-trading-crypto-bot-python-strategy-backtesting/)  
22. Best Python libraries for backtesting and algo trading : r/algotrading \- Reddit, 10월 3, 2025에 액세스, [https://www.reddit.com/r/algotrading/comments/m3g2c6/best\_python\_libraries\_for\_backtesting\_and\_algo/](https://www.reddit.com/r/algotrading/comments/m3g2c6/best_python_libraries_for_backtesting_and_algo/)