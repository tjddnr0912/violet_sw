from PyQt5.QtCore import QObject, pyqtSignal

class StrategyManager(QObject):
    # Signals to update GUI
    log_signal = pyqtSignal(str)
    
    def __init__(self, kiwoom, config):
        super().__init__()
        self.kiwoom = kiwoom
        self.config = config
        self.account_no = config.ACCOUNT_NO
        
        # Connect Kiwoom signals to Strategy logic
        # Note: In a real app, we might want to decouple this more, 
        # but for prototype, direct connection or via Kiwoom class wrapper is fine.
        # Here we assume Kiwoom class emits signals or we hook into its callbacks.
        # For now, we will rely on Kiwoom class printing to stdout, 
        # but in GUI integration, we need signals.
        pass

    def start_strategy(self):
        self.log_signal.emit("Starting Strategy...")
        
        # 1. Check Account
        if not self.account_no:
            self.log_signal.emit("Error: No Account Number configured.")
            return

        self.log_signal.emit(f"Using Account: {self.account_no}")

        # 2. Load Conditions
        conditions = self.kiwoom.get_condition_list()
        if not conditions:
            self.log_signal.emit("No conditions found. Please create one in HTS.")
            return

        self.log_signal.emit(f"Found {len(conditions)} conditions.")
        
        # 3. Activate First Condition (Prototype: Use the first available condition)
        first_condition = conditions[0]
        index, name = first_condition
        self.log_signal.emit(f"Activating Condition: {name} (Index: {index})")
        
        # Screen No "1000" for Real-time Condition Search
        self.kiwoom.send_condition("1000", name, index, 1)

    def buy_stock(self, code, qty=1):
        """
        Execute Buy Order (Market Price)
        """
        self.log_signal.emit(f"Attempting to Buy {code}, Qty: {qty}")
        # RQName, ScreenNo, AccNo, OrderType(1:Buy), Code, Qty, Price(0 for Market), Hoga(03:Market), OriginNo("")
        self.kiwoom.send_order("send_buy_order", "2000", self.account_no, 1, code, qty, 0, "03", "")

    def sell_stock(self, code, qty=1):
        """
        Execute Sell Order (Market Price)
        """
        self.log_signal.emit(f"Attempting to Sell {code}, Qty: {qty}")
        # OrderType(2:Sell)
        self.kiwoom.send_order("send_sell_order", "2000", self.account_no, 2, code, qty, 0, "03", "")
