"""
Main Execution Script - Version 2

This script supports both backtesting and live trading modes:

BACKTEST MODE:
1. Load historical data from Binance (Daily + 4H)
2. Initialize Backtrader with strategy
3. Execute backtest
4. Generate performance report
5. Plot results

LIVE TRADING MODE:
1. Initialize trading bot with real-time data fetching
2. Authenticate with exchange
3. Run trading cycle on schedule (every 4H)
4. Execute trades based on strategy signals
5. Monitor and manage positions

Usage:
    # Backtesting
    python main_v2.py --mode backtest [--months 10] [--capital 10000] [--plot]

    # Live trading (dry-run)
    python main_v2.py --mode live --dry-run

    # Live trading (real - CAUTION!)
    python main_v2.py --mode live --live --symbol BTC --amount 50000
"""

import argparse
import backtrader as bt
import pandas as pd
import schedule
import time
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ver2.backtrader_strategy_v2 import BitcoinMultiTimeframeStrategy
from ver2.trading_bot_v2 import TradingBotV2
from ver2.config_v2 import get_version_config


def fetch_binance_data(symbol: str, interval: str, months: int) -> pd.DataFrame:
    """
    Fetch historical data from Binance.

    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        interval: Candlestick interval ('1d', '4h')
        months: Number of months of historical data

    Returns:
        DataFrame with OHLCV data
    """
    try:
        from binance.client import Client

        print(f"📥 Fetching {symbol} {interval} data for {months} months...")

        # Initialize Binance client (no API keys needed for public data)
        client = Client()

        # Calculate start date
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months*30)

        # Fetch klines
        klines = client.get_historical_klines(
            symbol,
            interval,
            start_date.strftime("%d %b %Y %H:%M:%S"),
            end_date.strftime("%d %b %Y %H:%M:%S")
        )

        # Convert to DataFrame
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        # Convert types
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        # Set timestamp as index
        df.set_index('timestamp', inplace=True)

        # Keep only OHLCV columns
        df = df[['open', 'high', 'low', 'close', 'volume']]

        print(f"✅ Loaded {len(df)} {interval} candles from {df.index[0]} to {df.index[-1]}")
        return df

    except ImportError:
        print("❌ Error: python-binance not installed. Install with: pip install python-binance")
        return None
    except Exception as e:
        print(f"❌ Error fetching data: {str(e)}")
        return None


def validate_data(df: pd.DataFrame, min_bars: int = 200) -> bool:
    """
    Validate data quality before backtesting.

    Args:
        df: DataFrame with OHLCV data
        min_bars: Minimum required bars

    Returns:
        True if data is valid
    """
    print(f"\n🔍 Validating data...")

    checks = {
        'Sufficient data': len(df) >= min_bars,
        'No missing values': not df.isnull().any().any(),
        'Chronological order': df.index.is_monotonic_increasing,
        'No duplicates': not df.index.duplicated().any(),
        'Volume present': (df['volume'] > 0).all(),
    }

    all_passed = True
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"   {status} {check_name}")
        if not passed:
            all_passed = False

    return all_passed


def run_backtest(
    daily_data: pd.DataFrame,
    hourly_data: pd.DataFrame,
    initial_capital: float,
    plot: bool = False
) -> None:
    """
    Run backtest with Backtrader.

    Args:
        daily_data: Daily OHLCV data
        hourly_data: 4H OHLCV data
        initial_capital: Starting capital
        plot: Whether to plot results
    """
    print("\n" + "="*60)
    print("STARTING BACKTEST")
    print("="*60 + "\n")

    # Initialize Cerebro (Backtrader engine)
    cerebro = bt.Cerebro()

    # Add data feeds
    # Important: Daily must be first (datas[0]), 4H second (datas[1])
    data_daily = bt.feeds.PandasData(
        dataname=daily_data,
        name='BTC_DAILY'
    )
    data_4h = bt.feeds.PandasData(
        dataname=hourly_data,
        name='BTC_4H'
    )

    cerebro.adddata(data_daily)
    cerebro.adddata(data_4h)
    print(f"✅ Added data feeds: Daily ({len(daily_data)} bars), 4H ({len(hourly_data)} bars)")

    # Add strategy
    cerebro.addstrategy(BitcoinMultiTimeframeStrategy)
    print(f"✅ Added strategy: BitcoinMultiTimeframeStrategy")

    # Set initial capital
    cerebro.broker.setcash(initial_capital)
    print(f"✅ Set initial capital: ${initial_capital:.2f}")

    # Set commission (0.1% per trade)
    cerebro.broker.setcommission(commission=0.001)
    print(f"✅ Set commission: 0.1% per trade")

    # Add analyzers for performance metrics
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    print(f"✅ Added performance analyzers")

    # Run backtest
    print(f"\n{'='*60}")
    print(f"EXECUTING BACKTEST...")
    print(f"{'='*60}\n")

    starting_value = cerebro.broker.getvalue()
    results = cerebro.run()
    ending_value = cerebro.broker.getvalue()

    # Extract results
    strat = results[0]

    # Print performance report
    print_performance_report(
        strat,
        starting_value,
        ending_value
    )

    # Plot results if requested
    if plot:
        print("\n📊 Generating plot...")
        cerebro.plot(style='candlestick', volume=True)


def print_performance_report(strat, starting_value: float, ending_value: float):
    """
    Print comprehensive performance report.

    Args:
        strat: Strategy instance with analyzers
        starting_value: Starting portfolio value
        ending_value: Ending portfolio value
    """
    print("\n" + "="*60)
    print("PERFORMANCE REPORT")
    print("="*60)

    # Basic metrics
    total_return = ((ending_value - starting_value) / starting_value) * 100
    print(f"\n💰 PROFITABILITY:")
    print(f"   Starting Capital: ${starting_value:,.2f}")
    print(f"   Ending Capital: ${ending_value:,.2f}")
    print(f"   Net Profit: ${ending_value - starting_value:,.2f}")
    print(f"   Total Return: {total_return:+.2f}%")

    # Drawdown
    drawdown = strat.analyzers.drawdown.get_analysis()
    print(f"\n📉 RISK METRICS:")
    print(f"   Max Drawdown: {drawdown.max.drawdown:.2f}%")
    print(f"   Max MoneyDown: ${drawdown.max.moneydown:,.2f}")

    # Sharpe Ratio
    sharpe = strat.analyzers.sharpe.get_analysis()
    sharpe_ratio = sharpe.get('sharperatio', None)
    if sharpe_ratio is not None:
        print(f"   Sharpe Ratio: {sharpe_ratio:.2f}")
    else:
        print(f"   Sharpe Ratio: N/A (insufficient data)")

    # Trade statistics
    trades = strat.analyzers.trades.get_analysis()
    total_trades = trades.total.closed if trades.total.closed else 0

    if total_trades > 0:
        won_trades = trades.won.total if hasattr(trades, 'won') else 0
        lost_trades = trades.lost.total if hasattr(trades, 'lost') else 0
        win_rate = (won_trades / total_trades) * 100 if total_trades > 0 else 0

        print(f"\n📊 TRADE STATISTICS:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Winning Trades: {won_trades}")
        print(f"   Losing Trades: {lost_trades}")
        print(f"   Win Rate: {win_rate:.2f}%")

        if hasattr(trades, 'won') and won_trades > 0:
            avg_win = trades.won.pnl.average
            print(f"   Average Win: ${avg_win:.2f}")

        if hasattr(trades, 'lost') and lost_trades > 0:
            avg_loss = trades.lost.pnl.average
            print(f"   Average Loss: ${avg_loss:.2f}")

            if hasattr(trades, 'won') and won_trades > 0:
                win_loss_ratio = abs(avg_win / avg_loss)
                print(f"   Win/Loss Ratio: {win_loss_ratio:.2f}")
    else:
        print(f"\n📊 TRADE STATISTICS:")
        print(f"   Total Trades: 0 (No trades executed)")

    # Performance thresholds
    print(f"\n🎯 PERFORMANCE ASSESSMENT:")
    assessment_passed = True

    # Check Sharpe Ratio
    if sharpe_ratio is not None:
        if sharpe_ratio >= 1.5:
            print(f"   ✅ Sharpe Ratio: EXCELLENT ({sharpe_ratio:.2f} >= 1.5)")
        elif sharpe_ratio >= 1.0:
            print(f"   ⚠️  Sharpe Ratio: ACCEPTABLE ({sharpe_ratio:.2f} >= 1.0)")
        else:
            print(f"   ❌ Sharpe Ratio: POOR ({sharpe_ratio:.2f} < 1.0)")
            assessment_passed = False

    # Check Max Drawdown
    if drawdown.max.drawdown <= 15:
        print(f"   ✅ Max Drawdown: EXCELLENT ({drawdown.max.drawdown:.2f}% <= 15%)")
    elif drawdown.max.drawdown <= 20:
        print(f"   ⚠️  Max Drawdown: ACCEPTABLE ({drawdown.max.drawdown:.2f}% <= 20%)")
    else:
        print(f"   ❌ Max Drawdown: POOR ({drawdown.max.drawdown:.2f}% > 20%)")
        assessment_passed = False

    # Check Win Rate
    if total_trades > 0:
        if win_rate >= 55:
            print(f"   ✅ Win Rate: EXCELLENT ({win_rate:.2f}% >= 55%)")
        elif win_rate >= 50:
            print(f"   ⚠️  Win Rate: ACCEPTABLE ({win_rate:.2f}% >= 50%)")
        else:
            print(f"   ❌ Win Rate: POOR ({win_rate:.2f}% < 50%)")
            assessment_passed = False

    if assessment_passed:
        print(f"\n🏆 OVERALL: STRATEGY PASSED ALL THRESHOLDS")
    else:
        print(f"\n⚠️  OVERALL: STRATEGY NEEDS OPTIMIZATION")

    print("="*60 + "\n")


# ========== LIVE TRADING MODE ==========

def run_live_trading(bot: TradingBotV2, check_interval_seconds: int = 14400):
    """
    Run live trading mode with scheduled execution.

    Args:
        bot: TradingBotV2 instance
        check_interval_seconds: Seconds between trading cycles (default: 14400 = 4H)
    """
    print("\n" + "="*60)
    print("LIVE TRADING MODE")
    print("="*60)

    # Authenticate
    if not bot.authenticate():
        print("❌ Authentication failed. Exiting.")
        return

    print("\n📊 Trading Bot Configuration:")
    print(f"  Strategy: {bot.strategy.VERSION_DISPLAY_NAME}")
    print(f"  Check Interval: {check_interval_seconds}s ({check_interval_seconds/3600:.1f}h)")
    print(f"  Target Ticker: {bot.global_config.get('trading', {}).get('target_ticker', 'BTC')}")
    print(f"  Trade Amount: {bot.global_config.get('trading', {}).get('trade_amount_krw', 50000):,} KRW")

    safety_config = bot.global_config.get('safety', {})
    if safety_config.get('dry_run', True):
        print("\n🔧 MODE: DRY-RUN (No real trades)")
    else:
        print("\n🔴 MODE: LIVE TRADING (Real money at risk!)")

    print("\n⏰ Starting scheduled trading...")
    print(f"  First cycle will run immediately")
    print(f"  Subsequent cycles every {check_interval_seconds/3600:.1f} hours")
    print("\n  Press Ctrl+C to stop\n")

    # Run first cycle immediately
    try:
        bot.run_trading_cycle()
    except Exception as e:
        print(f"❌ Error in initial trading cycle: {e}")

    # Schedule subsequent cycles
    schedule.every(check_interval_seconds).seconds.do(bot.run_trading_cycle)

    # Run scheduler loop
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

    except KeyboardInterrupt:
        print("\n\n⏹️  Trading stopped by user")

        # Generate final report
        print("\n" + "="*60)
        print("FINAL REPORT")
        print("="*60)
        print(bot.generate_daily_report())


def main():
    """Main entry point for Version 2 execution."""
    parser = argparse.ArgumentParser(
        description='Bitcoin Multi-Timeframe Trading Strategy v2.0'
    )

    # Mode selection
    parser.add_argument(
        '--mode',
        type=str,
        choices=['backtest', 'live'],
        default='backtest',
        help='Execution mode: backtest or live (default: backtest)'
    )

    # Backtesting arguments
    parser.add_argument(
        '--months',
        type=int,
        default=10,
        help='[BACKTEST] Number of months of historical data (default: 10)'
    )
    parser.add_argument(
        '--capital',
        type=float,
        default=10000.0,
        help='[BACKTEST] Initial capital in USD (default: 10000)'
    )
    parser.add_argument(
        '--plot',
        action='store_true',
        help='[BACKTEST] Plot results after backtest'
    )

    # Live trading arguments
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='[LIVE] Run in dry-run mode (simulated trades, default: True)'
    )
    parser.add_argument(
        '--live',
        action='store_true',
        help='[LIVE] Run with real trades (CAUTION: Real money at risk!)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=14400,
        help='[LIVE] Check interval in seconds (default: 14400 = 4H)'
    )

    # Common arguments
    parser.add_argument(
        '--symbol',
        type=str,
        default='BTCUSDT',
        help='Trading pair symbol (default: BTCUSDT for backtest, BTC for live)'
    )
    parser.add_argument(
        '--amount',
        type=int,
        default=50000,
        help='[LIVE] Trade amount in KRW (default: 50000)'
    )

    args = parser.parse_args()

    print("="*60)
    print("Bitcoin Multi-Timeframe Trading Strategy v2.0")
    print(f"Mode: {args.mode.upper()}")
    print("="*60)

    if args.mode == 'backtest':
        # BACKTEST MODE
        print(f"\nConfiguration:")
        print(f"  Symbol: {args.symbol}")
        print(f"  Lookback Period: {args.months} months")
        print(f"  Initial Capital: ${args.capital:,.2f}")
        print(f"  Plot Results: {args.plot}")

        # Fetch daily data
        daily_data = fetch_binance_data(args.symbol, '1d', args.months)
        if daily_data is None or not validate_data(daily_data, min_bars=200):
            print("❌ Daily data validation failed. Exiting.")
            return

        # Fetch 4H data
        hourly_data = fetch_binance_data(args.symbol, '4h', args.months)
        if hourly_data is None or not validate_data(hourly_data, min_bars=50):
            print("❌ 4H data validation failed. Exiting.")
            return

        # Run backtest
        run_backtest(daily_data, hourly_data, args.capital, args.plot)
        print("\n✅ Backtest complete!")

    elif args.mode == 'live':
        # LIVE TRADING MODE

        # Determine dry-run mode
        dry_run = not args.live  # If --live flag is set, disable dry-run

        if not dry_run:
            print("\n🔴 WARNING: You are about to run LIVE TRADING with real money!")
            print("🔴 This will execute real buy/sell orders on Bithumb exchange.")
            confirmation = input("\nType 'I UNDERSTAND THE RISKS' to continue: ")
            if confirmation != 'I UNDERSTAND THE RISKS':
                print("❌ Live trading cancelled.")
                return

        # Adjust symbol for Bithumb (BTC instead of BTCUSDT)
        symbol = args.symbol if args.symbol != 'BTCUSDT' else 'BTC'

        # Create configuration override
        config_override = {
            'EXECUTION_CONFIG': {
                'mode': 'live',
                'dry_run': dry_run,
            },
            'TRADING_CONFIG': {
                'symbol': symbol,
                'trade_amount_krw': args.amount,
            },
            'SAFETY_CONFIG': {
                'dry_run': dry_run,
                'emergency_stop': False,
            },
            'SCHEDULE_CONFIG': {
                'check_interval_seconds': args.interval,
            }
        }

        # Initialize trading bot
        print("\n🤖 Initializing Trading Bot V2...")
        bot = TradingBotV2(config_override=config_override)

        # Run live trading
        run_live_trading(bot, check_interval_seconds=args.interval)

    else:
        print(f"❌ Unknown mode: {args.mode}")


if __name__ == '__main__':
    main()
