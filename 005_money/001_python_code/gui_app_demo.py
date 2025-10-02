#!/usr/bin/env python3
"""
빗썸 자동매매 봇 GUI 데모 - REDESIGNED VERSION
Dependencies 없이 실행 가능한 데모 버전

REDESIGN IMPROVEMENTS:
1. Console-style log at bottom (150px) - NOT filling right side ✓
2. Compact left panel with 2-column layout - NO scrolling needed ✓
3. Better visual hierarchy and spacing ✓
4. Color-coded log messages (INFO=blue, WARNING=orange, ERROR=red) ✓
5. Optimized window size (1400x850) ✓

NEW LAYOUT:
┌─────────────────────────────────────────────────────────┐
│  Top: Control Panel (Start/Stop, Status)                │
├──────────────────┬──────────────────────────────────────┤
│ Left: Compact    │  Main: Tabbed Content                │
│ Controls         │  - Chart                             │
│ (380px)          │  - Signals                           │
│ NO SCROLLING!    │  - History                           │
├──────────────────┴──────────────────────────────────────┤
│  Bottom: Console Log (150px, scrollable)                │
│  > [12:34:56] Bot started...                            │
└─────────────────────────────────────────────────────────┘
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
import random


class TradingBotGUIDemo:
    """
    Redesigned GUI Demo - Shows the improved layout
    """

    def __init__(self, root):
        self.root = root
        self.root.title("🤖 빗썸 자동매매 봇 - Redesigned UI Demo")

        # Optimized window size
        self.root.geometry("1400x850")
        self.root.minsize(1200, 700)

        # State
        self.is_running = False
        self.demo_price = 50000000  # 50M KRW

        # Setup
        self.setup_styles()
        self.create_widgets()

        # Start demo updates
        self.update_demo()

    def setup_styles(self):
        """GUI styles"""
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('Title.TLabel', font=('Arial', 10, 'bold'))
        style.configure('Status.TLabel', font=('Arial', 9))
        style.configure('Console.TLabel', font=('Monaco', 9))

    def create_widgets(self):
        """Create GUI with new 3-row layout"""
        # Configure root grid: [0] Control, [1] Main, [2] Console
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=0)  # Fixed (control)
        self.root.rowconfigure(1, weight=1)  # Expandable (main)
        self.root.rowconfigure(2, weight=0)  # Fixed 150px (console)

        # ===== ROW 0: Control Panel =====
        self.create_control_panel(self.root)

        # ===== ROW 1: Main Content =====
        main_frame = ttk.Frame(self.root, padding="10 5 10 5")
        main_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=0)  # Left panel (fixed)
        main_frame.columnconfigure(1, weight=1)  # Tabs (expandable)
        main_frame.rowconfigure(0, weight=1)

        # Left panel
        left_container = ttk.Frame(main_frame)
        left_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 8))
        self.create_left_panel(left_container)

        # Right tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.create_tabs()

        # ===== ROW 2: Console Log =====
        self.create_console_log(self.root)

    def create_control_panel(self, parent):
        """Top control panel - BEFORE: Was inside main frame, NOW: Separate row"""
        control_frame = ttk.LabelFrame(parent, text="🎮 봇 제어", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=10)

        # Buttons
        self.start_button = ttk.Button(
            control_frame, text="🚀 봇 시작", command=self.start_bot, width=12
        )
        self.start_button.grid(row=0, column=0, padx=(0, 5))

        self.stop_button = ttk.Button(
            control_frame, text="⏹ 봇 정지", command=self.stop_bot,
            state=tk.DISABLED, width=12
        )
        self.stop_button.grid(row=0, column=1, padx=5)

        # Status
        self.status_var = tk.StringVar(value="⚪ 대기 중")
        status_label = ttk.Label(
            control_frame, textvariable=self.status_var,
            font=('Arial', 11, 'bold'), foreground='gray'
        )
        status_label.grid(row=0, column=2, padx=(30, 20))

        # Mode
        self.mode_var = tk.StringVar(value="🟡 모의 거래 모드 (Demo)")
        mode_label = ttk.Label(
            control_frame, textvariable=self.mode_var,
            style='Title.TLabel', foreground='orange'
        )
        mode_label.grid(row=0, column=3, padx=(0, 20))

    def create_left_panel(self, parent):
        """
        BEFORE: Scrollable panel with all controls stacked vertically
        AFTER: Compact 2-column layout, all visible without scrolling!
        """
        parent.columnconfigure(0, weight=1)

        # ===== Panel 1: Status (Compact) =====
        status_frame = ttk.LabelFrame(parent, text="📊 거래 상태", padding="8")
        status_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 8))

        self.coin_var = tk.StringVar(value="BTC")
        self.price_var = tk.StringVar(value="50,000,000 KRW")
        self.holdings_var = tk.StringVar(value="0.00123456")

        # 2-column layout
        ttk.Label(status_frame, text="코인:", style='Title.TLabel').grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(status_frame, textvariable=self.coin_var).grid(
            row=0, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        ttk.Label(status_frame, text="현재가:", style='Title.TLabel').grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(status_frame, textvariable=self.price_var).grid(
            row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        ttk.Label(status_frame, text="보유:", style='Title.TLabel').grid(
            row=2, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(status_frame, textvariable=self.holdings_var).grid(
            row=2, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        # ===== Panel 2: Settings (Compact) =====
        settings_frame = ttk.LabelFrame(parent, text="⚙️ 설정", padding="8")
        settings_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 8))

        ttk.Label(settings_frame, text="코인:", style='Title.TLabel').grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        coin_combo = ttk.Combobox(
            settings_frame, values=('BTC', 'ETH', 'XRP'), width=8, state='readonly'
        )
        coin_combo.set('BTC')
        coin_combo.grid(row=0, column=1, sticky=tk.W, padx=(5, 0), pady=2)

        ttk.Label(settings_frame, text="캔들:", style='Title.TLabel').grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        interval_combo = ttk.Combobox(
            settings_frame, values=('30m', '1h', '6h', '12h'), width=8, state='readonly'
        )
        interval_combo.set('1h')
        interval_combo.grid(row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2)

        apply_btn = ttk.Button(settings_frame, text="📝 적용", width=10)
        apply_btn.grid(row=2, column=0, columnspan=2, pady=(8, 0))

        # ===== Panel 3: Market Regime (Compact) =====
        regime_frame = ttk.LabelFrame(parent, text="🔵 시장 국면", padding="8")
        regime_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 8))

        self.regime_var = tk.StringVar(value="🔵 추세장 (Trending)")
        ttk.Label(regime_frame, textvariable=self.regime_var,
                 font=('Arial', 9, 'bold'), foreground='blue').pack()

        # ===== Panel 4: Signal (Compact) =====
        signal_frame = ttk.LabelFrame(parent, text="🎯 종합 신호", padding="8")
        signal_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 8))

        self.signal_var = tk.StringVar(value="HOLD")
        self.signal_label = ttk.Label(
            signal_frame, textvariable=self.signal_var,
            font=('Arial', 14, 'bold'), foreground='gray'
        )
        self.signal_label.pack()

        self.strength_var = tk.StringVar(value="강도: 0.00")
        ttk.Label(signal_frame, textvariable=self.strength_var).pack()

        # ===== Panel 5: Risk (Compact) =====
        risk_frame = ttk.LabelFrame(parent, text="⚠️ 리스크", padding="8")
        risk_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 8))

        ttk.Label(risk_frame, text="손절:", style='Title.TLabel').grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(risk_frame, text="48,500,000원 (-3.0%)",
                 foreground='red', font=('Arial', 8)).grid(
            row=0, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        ttk.Label(risk_frame, text="익절:", style='Title.TLabel').grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(risk_frame, text="52,500,000원 (+5.0%)",
                 foreground='green', font=('Arial', 8)).grid(
            row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        # ===== Panel 6: Profit (Compact) =====
        profit_frame = ttk.LabelFrame(parent, text="💰 수익", padding="8")
        profit_frame.grid(row=5, column=0, sticky=(tk.W, tk.E))

        self.profit_var = tk.StringVar(value="+125,000 KRW")
        self.trades_var = tk.StringVar(value="3회")

        ttk.Label(profit_frame, text="오늘:", style='Title.TLabel').grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(profit_frame, textvariable=self.profit_var,
                 foreground='green', font=('Arial', 9, 'bold')).grid(
            row=0, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        ttk.Label(profit_frame, text="거래:", style='Title.TLabel').grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(profit_frame, textvariable=self.trades_var).grid(
            row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

    def create_tabs(self):
        """Create content tabs"""
        # Tab 1: Summary
        summary_tab = ttk.Frame(self.notebook)
        self.notebook.add(summary_tab, text='거래 현황')

        info_text = scrolledtext.ScrolledText(
            summary_tab, height=30, wrap=tk.WORD, font=('Monaco', 10), padding=10
        )
        info_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        info_text.insert(tk.END, "=== 빗썸 자동매매 봇 - Redesigned UI Demo ===\n\n")
        info_text.insert(tk.END, "주요 개선사항:\n\n")
        info_text.insert(tk.END, "1. 로그 창을 하단으로 이동 (150px 고정, 스크롤 가능)\n")
        info_text.insert(tk.END, "   BEFORE: 오른쪽 전체를 차지하던 로그\n")
        info_text.insert(tk.END, "   AFTER: 하단 콘솔 스타일 (10-15줄 표시)\n\n")
        info_text.insert(tk.END, "2. 왼쪽 패널 재구성 (2열 레이아웃, 스크롤 불필요)\n")
        info_text.insert(tk.END, "   BEFORE: 세로로 길게 나열, 스크롤 필요\n")
        info_text.insert(tk.END, "   AFTER: 컴팩트한 2열 레이아웃, 한눈에 보임\n\n")
        info_text.insert(tk.END, "3. 메인 콘텐츠 영역 확대\n")
        info_text.insert(tk.END, "   차트와 신호 히스토리가 더 넓게 표시됨\n\n")
        info_text.insert(tk.END, "4. 색상 코딩된 로그 메시지\n")
        info_text.insert(tk.END, "   INFO=파랑, WARNING=주황, ERROR=빨강\n\n")
        info_text.insert(tk.END, "5. 최적화된 창 크기 (1400x850)\n\n")
        info_text.insert(tk.END, "봇을 시작하면 실시간 데이터가 업데이트됩니다.\n")
        info_text.config(state=tk.DISABLED)

        # Tab 2: Chart
        chart_tab = ttk.Frame(self.notebook)
        self.notebook.add(chart_tab, text='📊 실시간 차트')
        ttk.Label(chart_tab, text="차트가 여기에 표시됩니다\n(더 넓은 공간 확보!)",
                 font=('Arial', 14), foreground='gray').pack(expand=True)

        # Tab 3: Signals
        signal_tab = ttk.Frame(self.notebook)
        self.notebook.add(signal_tab, text='📋 신호 히스토리')
        ttk.Label(signal_tab, text="신호 히스토리가 여기에 표시됩니다",
                 font=('Arial', 14), foreground='gray').pack(expand=True)

        # Tab 4: History
        history_tab = ttk.Frame(self.notebook)
        self.notebook.add(history_tab, text='📜 거래 내역')
        ttk.Label(history_tab, text="거래 내역이 여기에 표시됩니다",
                 font=('Arial', 14), foreground='gray').pack(expand=True)

    def create_console_log(self, parent):
        """
        KEY IMPROVEMENT: Console-style log at bottom!
        BEFORE: Full right panel (took 50% of horizontal space)
        AFTER: Bottom strip (150px height, scrollable)
        """
        log_container = ttk.Frame(parent)
        log_container.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=10, pady=(5, 10))
        log_container.columnconfigure(0, weight=1)

        # Header
        header_frame = ttk.Frame(log_container)
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))

        ttk.Label(header_frame, text="📝 Console Log (하단 고정 150px)",
                 style='Title.TLabel').pack(side=tk.LEFT)

        clear_btn = ttk.Button(header_frame, text="🗑 Clear",
                              command=self.clear_logs, width=8)
        clear_btn.pack(side=tk.RIGHT)

        # Log frame - FIXED HEIGHT 150px
        log_frame = ttk.Frame(log_container, height=150)
        log_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
        log_frame.grid_propagate(False)  # DON'T expand!
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # Console text widget
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=10, wrap=tk.WORD,
            font=('Monaco', 9), bg='#f5f5f5'
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Color tags
        self.log_text.tag_configure("INFO", foreground="#0066cc")
        self.log_text.tag_configure("WARNING", foreground="#ff8800")
        self.log_text.tag_configure("ERROR", foreground="#cc0000")
        self.log_text.tag_configure("SUCCESS", foreground="#00aa00")

        # Add welcome message
        self.add_log("INFO", "빗썸 자동매매 봇 GUI 시작됨")
        self.add_log("INFO", "Redesigned layout loaded successfully")

    # ===== Demo Methods =====

    def start_bot(self):
        """Start demo bot"""
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_var.set("🟢 실행 중")

        self.add_log("SUCCESS", "거래 봇이 시작되었습니다 (Demo Mode)")
        self.add_log("INFO", "시장 데이터 분석 중...")

    def stop_bot(self):
        """Stop demo bot"""
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_var.set("🔴 정지됨")

        self.add_log("WARNING", "거래 봇이 정지되었습니다")

    def add_log(self, level, message):
        """Add log message with color coding"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_text.insert(tk.END, log_entry + "\n", level)
        self.log_text.see(tk.END)

        # Limit to last 100 lines
        line_count = int(self.log_text.index('end-1c').split('.')[0])
        if line_count > 100:
            self.log_text.delete('1.0', f'{line_count-100}.0')

    def clear_logs(self):
        """Clear log window"""
        self.log_text.delete(1.0, tk.END)
        self.add_log("INFO", "로그가 지워졌습니다")

    def update_demo(self):
        """Update demo data"""
        if self.is_running:
            # Simulate price changes
            change = random.randint(-100000, 100000)
            self.demo_price += change
            self.price_var.set(f"{self.demo_price:,} KRW")

            # Random signal changes
            if random.random() < 0.1:  # 10% chance
                signals = ['BUY', 'SELL', 'HOLD']
                colors = {'BUY': 'red', 'SELL': 'blue', 'HOLD': 'gray'}
                signal = random.choice(signals)
                self.signal_var.set(signal)
                self.signal_label.config(foreground=colors[signal])

                strength = random.uniform(-1, 1)
                self.strength_var.set(f"강도: {strength:+.2f}")

                if signal != 'HOLD':
                    log_level = "INFO"
                    icon = "🔵" if signal == "BUY" else "🔴"
                    self.add_log(log_level, f"{icon} {signal} 신호 감지 - BTC @ {self.demo_price:,}원")

        # Schedule next update
        self.root.after(2000, self.update_demo)


def main():
    """Run demo application"""
    root = tk.Tk()
    app = TradingBotGUIDemo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
