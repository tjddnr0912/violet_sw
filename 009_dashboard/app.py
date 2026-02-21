"""
009_dashboard - Trading Dashboard Flask Application
"""
import os
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from data_loader import TradingDataLoader

load_dotenv()

app = Flask(__name__)
CORS(app)  # Blogger iframe 임베드를 위한 CORS 허용

# 데이터 로더 초기화
data_loader = TradingDataLoader()

# API Key 설정
API_KEY = os.getenv('DASHBOARD_API_KEY', '')


@app.before_request
def check_api_key():
    """v2 API에 대한 API Key 인증"""
    if request.path == '/health':
        return None
    if request.path.startswith('/api/v2/'):
        if not API_KEY:
            return None  # API Key 미설정 시 인증 비활성화
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not key or key != API_KEY:
            return jsonify({'status': 'error', 'error': 'Unauthorized'}), 401


def api_response(data):
    """v2 API 통일 응답 형식"""
    return jsonify({
        'status': 'ok',
        'data': data,
        'timestamp': datetime.now().isoformat(),
    })


# === 페이지 라우트 ===

@app.route('/')
def index():
    """메인 대시보드 페이지"""
    summary = data_loader.get_portfolio_summary()
    stock_positions = data_loader.get_stock_positions()
    crypto_regime = data_loader.get_crypto_regime()
    recent_trades = data_loader.get_recent_trades(limit=10)

    return render_template('index.html',
                          summary=summary,
                          stock_positions=stock_positions,
                          crypto_regime=crypto_regime,
                          recent_trades=recent_trades)


@app.route('/stock')
def stock_detail():
    """주식 상세 페이지"""
    stock_positions = data_loader.get_stock_positions()
    stock_state = data_loader.get_stock_state()

    return render_template('stock.html',
                          positions=stock_positions,
                          state=stock_state)


@app.route('/crypto')
def crypto_detail():
    """암호화폐 상세 페이지"""
    crypto_regime = data_loader.get_crypto_regime()
    crypto_perf = data_loader.get_crypto_performance()
    recent_trades = data_loader.get_recent_trades(limit=20)

    return render_template('crypto.html',
                          regime=crypto_regime,
                          performance=crypto_perf,
                          trades=recent_trades)


@app.route('/embed')
def embed():
    """iframe 임베드용 간소화 페이지"""
    summary = data_loader.get_portfolio_summary()
    return render_template('embed.html', summary=summary)


# === API 라우트 ===

@app.route('/api/summary')
def api_summary():
    """포트폴리오 요약 API"""
    return jsonify(data_loader.get_portfolio_summary())


@app.route('/api/stock/positions')
def api_stock_positions():
    """주식 포지션 API"""
    return jsonify(data_loader.get_stock_positions())


@app.route('/api/crypto/regime')
def api_crypto_regime():
    """암호화폐 레짐 API"""
    return jsonify(data_loader.get_crypto_regime())


@app.route('/api/crypto/trades')
def api_crypto_trades():
    """암호화폐 거래 내역 API"""
    return jsonify(data_loader.get_recent_trades(limit=20))


@app.route('/api/crypto/performance')
def api_crypto_performance():
    """암호화폐 성과 API"""
    return jsonify(data_loader.get_crypto_performance())


# === v2 API 라우트 (인증 필요) ===

@app.route('/api/v2/summary')
def api_v2_summary():
    """통합 포트폴리오 요약"""
    return api_response(data_loader.get_portfolio_summary())


@app.route('/api/v2/crypto/regime')
def api_v2_crypto_regime():
    """암호화폐 시장 레짐 상세"""
    return api_response(data_loader.get_crypto_regime())


@app.route('/api/v2/crypto/trades')
def api_v2_crypto_trades():
    """암호화폐 거래 내역"""
    limit = request.args.get('limit', 20, type=int)
    return api_response(data_loader.get_recent_trades(limit=limit))


@app.route('/api/v2/crypto/performance')
def api_v2_crypto_performance():
    """암호화폐 성과 통계"""
    return api_response(data_loader.get_crypto_performance())


@app.route('/api/v2/stock/positions')
def api_v2_stock_positions():
    """한국주식 현재 포지션"""
    return api_response(data_loader.get_stock_positions())


@app.route('/api/v2/stock/daily')
def api_v2_stock_daily():
    """한국주식 일일 자산 변동"""
    days = request.args.get('days', 30, type=int)
    return api_response(data_loader.get_stock_daily_history(days=days))


@app.route('/api/v2/stock/transactions')
def api_v2_stock_transactions():
    """한국주식 거래 내역"""
    limit = request.args.get('limit', 20, type=int)
    return api_response(data_loader.get_stock_transactions(limit=limit))


@app.route('/api/v2/system/status')
def api_v2_system_status():
    """봇 상태 (장 시간 + 데몬 상태 기반)"""
    return api_response(data_loader.get_system_status())


@app.route('/api/v2/crypto/coins')
def api_v2_crypto_coins():
    """코인별 성과 요약"""
    return api_response(data_loader.get_crypto_coin_summary())


@app.route('/api/v2/crypto/coins/<coin>/trades')
def api_v2_crypto_coin_trades(coin):
    """특정 코인 거래 내역"""
    limit = request.args.get('limit', 20, type=int)
    return api_response(data_loader.get_crypto_coin_trades(coin, limit=limit))


@app.route('/api/v2/crypto/price/<coin>')
def api_v2_crypto_price(coin):
    """실시간 코인 시세 (Bithumb)"""
    return api_response(data_loader.get_coin_price(coin))


@app.route('/api/v2/crypto/chart/<coin>')
def api_v2_crypto_chart(coin):
    """코인 캔들스틱 차트 데이터"""
    interval = request.args.get('interval', '1h')
    return api_response(data_loader.get_coin_chart(coin, interval=interval))


# === Health Check ===

@app.route('/health')
def health():
    """헬스 체크"""
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=5001, debug=debug_mode)
