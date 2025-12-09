import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from kiwoom import Kiwoom
from strategy_manager import StrategyManager
from config import Config

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kiwoom Auto Trading Prototype")
        self.setGeometry(100, 100, 800, 600)

        self.kiwoom = Kiwoom()
        self.strategy = StrategyManager(self.kiwoom, Config)

        self.init_ui()
        self.connect_signals()
        
        # Auto Login
        QTimer.singleShot(1000, self.kiwoom.comm_connect)

    def init_ui(self):
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Top Control Panel
        control_layout = QHBoxLayout()
        
        self.btn_start = QPushButton("Start Strategy")
        self.btn_start.clicked.connect(self.start_strategy)
        control_layout.addWidget(self.btn_start)
        
        self.btn_account = QPushButton("Get Account Info")
        self.btn_account.clicked.connect(self.get_account_info)
        control_layout.addWidget(self.btn_account)
        
        layout.addLayout(control_layout)

        # Log Window
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(QLabel("System Logs"))
        layout.addWidget(self.log_text)

    def connect_signals(self):
        # Connect Strategy Logs to GUI
        self.strategy.log_signal.connect(self.update_log)
        
        # Connect Kiwoom Events (We need to bridge these if we want them in GUI log)
        # For now, we rely on stdout or add more signals in Kiwoom class
        pass

    def update_log(self, message):
        self.log_text.append(message)

    def start_strategy(self):
        self.update_log("Initializing Strategy...")
        self.strategy.start_strategy()

    def get_account_info(self):
        if Config.ACCOUNT_NO:
            self.update_log(f"Requesting info for account: {Config.ACCOUNT_NO}")
            self.kiwoom.get_account_info(Config.ACCOUNT_NO)
        else:
            self.update_log("Please set ACCOUNT_NO in .env file")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
