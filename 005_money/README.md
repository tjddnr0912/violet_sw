# Bithumb Elite Trading Bot

**Version**: 2.0 (Elite Strategy Update)
**Status**: Production Ready ✅
**Last Updated**: 2025-10-02

빗썸 거래소 API를 활용한 Python 기반 암호화폐 자동매매 봇입니다. 8개의 기술적 지표를 활용한 엘리트 전략과 시장 국면 감지 기능을 탑재했습니다.

---

## 🌟 Key Features

### 🎯 Elite Trading Strategy (v2.0)
- **8개 기술적 지표**: MA, RSI, MACD, Bollinger Bands, Stochastic, ATR, ADX, Volume
- **가중치 기반 신호 시스템**: 각 지표의 신호를 가중치로 조합하여 최종 결정
- **시장 국면 감지**: ADX 기반 추세장/횡보장 자동 감지
- **ATR 기반 리스크 관리**: 동적 손절/익절가 자동 계산
- **다중 시간대 지원**: 30m, 1h, 6h, 12h, 24h (각각 최적화된 파라미터)

### 💻 User Interface
- **GUI 모드**: Tkinter 기반 실시간 모니터링 대시보드
  - 4개 탭: 거래 현황, 실시간 차트, 신호 히스토리, 거래 내역
  - LED 지표 시스템 (8개 지표 실시간 표시)
  - 실시간 캔들스틱 차트 (v3.0 - 완전 재구축)
  - 전략 프리셋 셀렉터
- **CLI 모드**: 헤드리스 백그라운드 실행
  - 스케줄링 기반 자동 실행 (15분 간격 기본)
  - 완전한 로그 기록

### 🛡️ Safety Features
- **모의 거래 모드**: 실제 자금 없이 전략 테스트
- **다층 안전장치**:
  - 일일 거래 한도 (기본값: 10회)
  - 일일 최대 손실률 (기본값: 3%)
  - 연속 손실 한도 (기본값: 3회)
  - 긴급 정지 기능
- **ATR 기반 동적 포지션 사이징**: 변동성에 따른 자동 조절

### 📊 Comprehensive Logging
- **다중 채널 로깅 시스템**:
  - 거래 결정 로그 (전략 분석 결과)
  - 거래 실행 로그 (실제 주문 내역)
  - 에러 로그 (시스템 오류)
  - 거래 내역 (JSON + Markdown)
- **FIFO 수익 계산**: 매도 시 선입선출 방식으로 정확한 손익 계산
- **일일 로그 로테이션**: 자동 파일 관리 (30일 보관)

### 🔐 Security
- 환경변수 기반 API 키 관리
- `.env` 파일 지원 (`.gitignore` 보호)
- 잔고 조회 기능 의도적 비활성화 (보안 강화)
- Public API만 사용 (Private API는 테스트 파일에만 존재)

---

## 📖 Documentation Hub

This project has comprehensive documentation for different audiences:

### For Users

📘 **[Quick Start Guide](QUICK_START_GUIDE.md)**
- 5분 빠른 시작
- GUI 사용법
- 전략 선택 가이드

📙 **[Comprehensive User Manual](COMPREHENSIVE_USER_MANUAL.md)**
- 완전한 사용자 가이드 (한국어)
- GUI 전체 기능 설명
- 매매 전략 상세 분석

📗 **[Chart User Guide](CHART_USER_GUIDE.md)**
- 차트 위젯 사용법
- 지표 해석 방법
- 실시간 차트 활용

### For Developers

📕 **[Architecture Documentation](ARCHITECTURE.md)**
- 시스템 아키텍처 상세 설명
- 컴포넌트 구조 및 데이터 흐름
- 디자인 패턴 및 확장 포인트

📔 **[API Reference](API_REFERENCE.md)**
- 완전한 API 문서
- 모든 함수 및 클래스 레퍼런스
- 코드 예제 포함

📓 **[Developer Onboarding Guide](DEVELOPER_ONBOARDING.md)**
- 개발 환경 셋업
- 코드베이스 투어
- 첫 기여 가이드
- 공통 개발 작업

### For Strategy Tuning

📐 **[Strategy Configuration & Tuning Guide](STRATEGY_TUNING_GUIDE.md)**
- 전략 파라미터 최적화
- 지표 가중치 조정
- 인터벌별 설정
- 고급 최적화 기법

### Troubleshooting

🔧 **[Troubleshooting & FAQ Guide](TROUBLESHOOTING_FAQ.md)**
- 일반적인 문제 해결
- FAQ (자주 묻는 질문)
- 긴급 대응 절차
- 예방적 유지보수

### Additional Documentation

- **[Elite Strategy Implementation Summary](ELITE_STRATEGY_IMPLEMENTATION_SUMMARY.md)**: 엘리트 전략 구현 요약
- **[Elite Strategy Quick Reference](ELITE_STRATEGY_QUICK_REFERENCE.md)**: 엘리트 전략 빠른 참조
- **[GUI Features List](GUI_FEATURES_LIST.md)**: GUI 기능 상세 목록
- **[Chart Rebuild Report](CHART_REBUILD_REPORT.md)**: 차트 v3.0 재구축 보고서

---

## 🚀 Quick Start

### Installation

```bash
# 1. Navigate to project directory
cd 005_money

# 2. Create virtual environment
python3 -m venv .venv

# 3. Activate virtual environment
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# 4. Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# 1. Copy example environment file
cp .env.example .env

# 2. Edit .env and add your API keys (optional for dry-run)
# BITHUMB_CONNECT_KEY=your_connect_key
# BITHUMB_SECRET_KEY=your_secret_key
```

**Important**: For development and testing, API keys are NOT required if using dry-run mode.

### Run the Bot

#### GUI Mode (Recommended)
```bash
# Automatic setup and launch
./run_gui.sh

# Or directly
python gui_app.py
```

#### CLI Mode (Headless)
```bash
# Automatic setup and launch
./run.sh

# Or directly (dry-run mode)
python main.py --dry-run

# Live trading (USE WITH CAUTION!)
python main.py --live
```

### First Steps

1. **Start with dry-run**: Always test strategies without real money first
2. **Observe for 1 week**: Watch how signals are generated
3. **Tune parameters**: Adjust based on performance (see Strategy Guide)
4. **Start small**: Begin live trading with minimum amounts
5. **Monitor closely**: Check logs and performance daily

---

## 📁 Project Structure

```
005_money/
├── main.py                      # CLI entry point
├── gui_app.py                   # GUI entry point
├── run.py / run.sh              # Automated setup scripts
├── run_gui.py / run_gui.sh      # GUI setup scripts
│
├── config.py                    # Central configuration (150+ parameters)
├── config_manager.py            # Runtime config updates
│
├── trading_bot.py               # Main trading orchestrator
├── gui_trading_bot.py           # GUI-specific trading adapter
├── strategy.py                  # Elite strategy engine (8 indicators)
├── bithumb_api.py               # Bithumb API wrapper
│
├── chart_widget.py              # Real-time chart (v3.0)
├── signal_history_widget.py     # Signal history display
├── portfolio_manager.py         # Portfolio tracking
├── logger.py                    # Logging system
│
├── logs/                        # Log files
│   ├── trading_YYYYMMDD.log    # Daily trading logs
│   ├── trading_history.md       # Transaction history (markdown)
│   └── ...
│
├── pybithumb/                   # Third-party Bithumb library
│
├── tests/                       # Test files
│   ├── test_*.py               # Unit/integration tests
│   └── ...
│
├── docs/ (via README links)     # Documentation
│   ├── ARCHITECTURE.md
│   ├── API_REFERENCE.md
│   ├── STRATEGY_TUNING_GUIDE.md
│   ├── DEVELOPER_ONBOARDING.md
│   ├── TROUBLESHOOTING_FAQ.md
│   └── ...
│
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
├── .gitignore                   # Git ignore rules
└── README.md                    # This file
```

---

## 🔧 Technology Stack

### Core
- **Python**: 3.7+
- **Pandas**: Data manipulation
- **NumPy**: Numerical computing
- **Matplotlib**: Chart visualization
- **Tkinter**: GUI framework
- **Requests**: HTTP API calls
- **Schedule**: Task scheduling

### APIs
- **Bithumb Public API**: Market data
- **Bithumb Private API**: Trading (intentionally not used for security)

### Development
- **Git**: Version control
- **Virtual Environment**: Dependency isolation
- **Bash Scripts**: Deployment automation

---

## ⚙️ Configuration Overview

### Main Config File: `config.py`

```python
# Trading Configuration
TRADING_CONFIG = {
    'target_ticker': 'BTC',
    'trade_amount_krw': 10000,
    'stop_loss_percent': 5.0,
    'take_profit_percent': 10.0,
}

# Strategy Configuration
STRATEGY_CONFIG = {
    'candlestick_interval': '1h',  # Default: 1-hour candles

    # Indicator Parameters (Classic)
    'short_ma_window': 20,
    'long_ma_window': 50,
    'rsi_period': 14,

    # Elite Indicator Parameters
    'macd_fast': 8,
    'macd_slow': 17,
    'macd_signal': 9,
    'atr_period': 14,
    'stoch_k_period': 14,
    'adx_period': 14,

    # Signal Weights (must sum to 1.0)
    'signal_weights': {
        'macd': 0.35,      # Highest (trend + momentum)
        'ma': 0.25,        # Trend confirmation
        'rsi': 0.20,       # Overbought/oversold
        'bb': 0.10,        # Mean reversion
        'volume': 0.10     # Confirmation
    },

    # Decision Thresholds
    'confidence_threshold': 0.6,   # Minimum confidence (0-1)
    'signal_threshold': 0.5,       # Minimum signal strength (-1 to 1)

    # Interval Presets (30m, 1h, 6h, 12h, 24h)
    'interval_presets': {...}
}

# Safety Configuration
SAFETY_CONFIG = {
    'dry_run': False,              # Paper trading mode
    'max_daily_trades': 10,
    'emergency_stop': False,
}

# Scheduling Configuration
SCHEDULE_CONFIG = {
    'check_interval_minutes': 15,  # Check every 15 minutes
}
```

**See [Strategy Tuning Guide](STRATEGY_TUNING_GUIDE.md) for detailed parameter explanations.**

---

## 📊 Strategy Overview

### Elite Trading Strategy (v2.0)

The bot uses a sophisticated weighted signal system:

1. **Calculate 8 Indicators**:
   - MA (Moving Average): Trend direction
   - RSI (Relative Strength Index): Overbought/oversold
   - MACD: Momentum and trend
   - Bollinger Bands: Volatility and mean reversion
   - Stochastic: Secondary momentum
   - ATR (Average True Range): Volatility measurement
   - ADX (Average Directional Index): Trend strength
   - Volume: Confirmation

2. **Generate Weighted Signals**:
   - Each indicator produces a signal (-1.0 to +1.0)
   - Multiply by configured weights
   - Sum to get overall signal strength
   - Calculate confidence (0.0 to 1.0)

3. **Decision Logic**:
   ```
   IF overall_signal >= 0.5 AND confidence >= 0.6:
       BUY
   ELIF overall_signal <= -0.5 AND confidence >= 0.6:
       SELL
   ELSE:
       HOLD
   ```

4. **Market Regime Adaptation**:
   - Detect Trending vs Ranging markets
   - Adjust strategy weights dynamically
   - Recommend appropriate strategy preset

5. **ATR-Based Risk Management**:
   - Calculate stop-loss: Entry - (ATR × 2.0)
   - Calculate take-profits: TP1 (1.5x ATR), TP2 (2.5x ATR)
   - Adjust position size based on volatility

**For detailed strategy explanation, see [Strategy Tuning Guide](STRATEGY_TUNING_GUIDE.md).**

---

## 🎛️ Strategy Presets

The GUI includes 5 pre-configured strategies:

### 1. Balanced Elite (Default)
**Use**: All-weather strategy, starting point
**Weights**: MACD 0.35, MA 0.25, RSI 0.20, BB 0.10, Volume 0.10
**Best For**: Learning the system, uncertain conditions

### 2. Trend Following
**Use**: Strong trends (ADX > 25)
**Weights**: MACD 0.45, MA 0.35, RSI 0.10, BB 0.05, Volume 0.05
**Best For**: Bull/bear runs

### 3. Mean Reversion
**Use**: Sideways markets (ADX < 20)
**Weights**: MACD 0.20, MA 0.15, RSI 0.30, BB 0.25, Volume 0.10
**Best For**: Range-bound consolidation

### 4. MACD + RSI Filter
**Use**: Clear trends with confirmation
**Weights**: MACD 0.50, MA 0.15, RSI 0.25, BB 0.05, Volume 0.05
**Best For**: Conservative, high-quality signals

### 5. Custom
**Use**: Advanced users with specific requirements
**Configuration**: User-defined weights in `config.py`

---

## 🖥️ GUI Overview

### Tabs

**1. 거래 현황 (Trading Status)**
- Bot control (Start/Stop)
- Strategy settings and presets
- 8 indicator LED panels
- Market regime analysis
- Comprehensive signal display
- ATR-based risk levels
- Real-time logs

**2. 📊 실시간 차트 (Real-time Chart)**
- Candlestick chart (v3.0 rebuild)
- 8 indicator checkboxes (toggle on/off)
- Dynamic subplot layout
- MA lines, Bollinger Bands overlays
- RSI, MACD, Volume subplots
- Stochastic, ATR, ADX info box

**3. 📋 신호 히스토리 (Signal History)**
- Historical signal tracking
- Timestamp, decision, confidence
- Individual indicator values snapshot

**4. 거래 내역 (Transaction History)**
- All trades with detailed information
- FIFO profit calculation
- Export functionality

**See [GUI Features List](GUI_FEATURES_LIST.md) for complete feature documentation.**

---

## 📈 Chart Widget (v3.0)

Recently rebuilt (2025-10-02) for improved performance and reliability:

### Features
- **Pure matplotlib** implementation (no mplfinance dependency)
- **8 indicator checkboxes** with instant toggle
- **Dynamic subplot layout** (adjusts based on active indicators)
- **Fixed x-axis compression** issue from previous versions
- **Real-time updates** without page refresh

### Indicators on Chart
- **Main chart overlays**: MA lines, Bollinger Bands
- **Subplot 1**: RSI with 30/70 levels
- **Subplot 2**: MACD line, signal line, histogram
- **Subplot 3**: Volume bar chart (color-coded)
- **Info box**: Stochastic K/D, ATR value/%, ADX trend strength

**See [Chart User Guide](CHART_USER_GUIDE.md) for usage details.**

---

## 🔐 Security Best Practices

### API Key Management
1. ✅ **Use environment variables**:
   ```bash
   export BITHUMB_CONNECT_KEY="your_key"
   export BITHUMB_SECRET_KEY="your_secret"
   ```

2. ✅ **Use .env file** (never commit to Git):
   ```
   BITHUMB_CONNECT_KEY=your_key
   BITHUMB_SECRET_KEY=your_secret
   ```

3. ❌ **Never hardcode** in `config.py`:
   ```python
   # DON'T DO THIS
   BITHUMB_CONNECT_KEY = "actual_key_here"  # ❌
   ```

### API Key Permissions
When creating Bithumb API keys:
- ✅ **Asset inquiry** (자산 조회): Enable for balance checks
- ⚠️ **Trading** (거래): Only enable if doing live trading
- ❌ **Withdrawal** (출금): **NEVER** enable

### Trading Safety
- Always start with **dry-run mode**
- Test strategies for **1-2 weeks** minimum
- Start live trading with **small amounts**
- Use **separate API key** for bot (not main account)
- **Monitor closely** especially in first few days
- Set **conservative limits** initially

---

## 🧪 Testing

### Dry-Run Mode
```bash
# Test without real money
python main.py --dry-run

# GUI dry-run (default)
python gui_app.py
```

### Test Scripts
```bash
# Test API connection
python test_api_connection.py

# Test strategy analysis
python test_elite_gui.py

# Test chart rendering
python test_chart_gui.py
```

### Manual Testing Checklist
- [ ] Bot starts without errors
- [ ] Logs are created
- [ ] GUI displays all tabs
- [ ] Chart renders correctly
- [ ] Indicators toggle on/off
- [ ] Signals generate properly
- [ ] Dry-run trades execute
- [ ] Bot stops gracefully

---

## 📝 Logging System

### Log Files

**Location**: `logs/`

**Files**:
- `trading_YYYYMMDD.log`: Daily trading logs
- `trading_history.md`: Transaction history (markdown table)
- `transaction_history.json`: Transaction history (JSON)

### Log Levels
- **INFO**: Normal operations (decisions, trades)
- **WARNING**: Potential issues (low balance, near limits)
- **ERROR**: Failures (API errors, exceptions)
- **DEBUG**: Detailed debugging (enable in config)

### Viewing Logs
```bash
# Watch real-time logs
tail -f logs/trading_$(date +%Y%m%d).log

# View last 100 lines
tail -100 logs/trading_$(date +%Y%m%d).log

# Search for errors
grep -i "error" logs/trading_*.log

# Find all BUY decisions
grep "Decision: BUY" logs/trading_*.log
```

---

## ⚠️ Important Warnings

### Financial Risk
- **This bot can lose money**: Cryptocurrency trading is high risk
- **No guarantees**: Past performance doesn't predict future results
- **Start small**: Only invest what you can afford to lose
- **Monitor actively**: Don't leave bot unsupervised for extended periods
- **Understand limits**: Bot can't predict market crashes or black swan events

### Technical Limitations
- **Single exchange**: Only Bithumb supported
- **Single coin**: One cryptocurrency at a time
- **Market orders only**: No limit orders or advanced order types
- **Polling-based**: 15-minute default intervals (not tick-by-tick)
- **No backtesting**: Historical strategy testing not implemented

### Maintenance
- **Keep updated**: Regularly `git pull` for latest version
- **Monitor logs**: Check for errors daily
- **Review performance**: Analyze trades weekly
- **Update config**: Adjust strategy as markets change
- **Backup data**: Save transaction history periodically

---

## 🤝 Contributing

Contributions are welcome! Please see [Developer Onboarding Guide](DEVELOPER_ONBOARDING.md) for:
- Development environment setup
- Coding standards
- Testing procedures
- Pull request process

### Quick Contribution Guide

1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/your-feature`
3. **Make changes** and add tests
4. **Test thoroughly** (dry-run mode)
5. **Commit**: `git commit -m "feat: your feature description"`
6. **Push**: `git push origin feature/your-feature`
7. **Create Pull Request**

---

## 📚 Additional Resources

### Internal Documentation
- [Architecture Documentation](ARCHITECTURE.md)
- [API Reference](API_REFERENCE.md)
- [Strategy Tuning Guide](STRATEGY_TUNING_GUIDE.md)
- [Developer Onboarding](DEVELOPER_ONBOARDING.md)
- [Troubleshooting FAQ](TROUBLESHOOTING_FAQ.md)

### External Resources
- **Bithumb API Documentation**: https://apidocs.bithumb.com/
- **Technical Analysis**: Investopedia (indicators and patterns)
- **Python Pandas**: https://pandas.pydata.org/docs/
- **Python Matplotlib**: https://matplotlib.org/stable/contents.html

### Community
- **Issues**: Report bugs or request features
- **Discussions**: Ask questions and share experiences
- **Wiki**: FAQs and tips

---

## 📄 License

This project is for **educational and research purposes only**. Use at your own risk. The developers are not responsible for any financial losses incurred through the use of this software.

**Disclaimer**: Trading cryptocurrencies carries significant risk. This bot is a tool, not a guarantee of profit. Always conduct thorough testing, start with small amounts, and never invest more than you can afford to lose.

---

## 🆕 Recent Updates

### Version 2.0 (Elite Strategy) - 2025-10-01
- ✨ Added 4 new indicators: MACD, ATR, Stochastic, ADX
- ✨ Implemented weighted signal system (replaces binary voting)
- ✨ Added market regime detection (Trending/Ranging/Transitional)
- ✨ Added ATR-based risk management (dynamic stops)
- ✨ Changed default interval from 24h to 1h
- ✨ Added interval presets with optimized parameters
- ✨ Added 5 strategy presets (Balanced, Trend Following, Mean Reversion, MACD+RSI, Custom)
- 🐛 Fixed chart x-axis compression (v3.0 rebuild)
- 📚 Comprehensive documentation overhaul

### Version 1.0 - 2025-09-28
- 🎉 Initial release
- 📊 4 indicators: MA, RSI, Bollinger Bands, Volume
- 🖥️ CLI and GUI interfaces
- 📝 Multi-channel logging system
- 🔒 Security features and dry-run mode

---

## 🙏 Acknowledgments

- **pybithumb library**: https://github.com/sharebook-kr/pybithumb
- **Bithumb Exchange**: API access
- **Open source community**: Python libraries and tools
- **Technical Analysis pioneers**: Wilder (RSI, ATR, ADX), Bollinger (BB), Appel (MACD)

---

## 📞 Support

**Need help?**

1. Check [Troubleshooting & FAQ Guide](TROUBLESHOOTING_FAQ.md)
2. Review [Documentation Hub](#-documentation-hub) for relevant guides
3. Search [Issues](../../issues) (if using GitHub)
4. Create new issue with details:
   - What you're trying to do
   - What happened (with error messages)
   - Log snippets (last 50 lines)
   - Your environment (Python version, OS)
   - Steps to reproduce

---

## ✅ Quick Reference

### Start Bot (Dry-Run)
```bash
./run.sh --dry-run          # CLI mode
./run_gui.sh                # GUI mode
```

### Check Logs
```bash
tail -f logs/trading_$(date +%Y%m%d).log
```

### Change Strategy
```bash
# Edit config.py
nano config.py
# Or use GUI strategy selector
```

### Emergency Stop
```bash
# Ctrl+C in terminal, or
# Click "⏹ 봇 정지" in GUI
```

### Get Help
```bash
python main.py --help
```

---

**Happy Trading! 🚀**

*Remember: Test thoroughly in dry-run mode before live trading. Start small. Monitor closely. Trade responsibly.*

---

**Project Version**: 2.0 (Elite Strategy)
**Documentation Version**: 1.0
**Last Updated**: 2025-10-02
**Status**: Production Ready ✅
