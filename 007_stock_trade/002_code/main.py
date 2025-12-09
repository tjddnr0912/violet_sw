import sys
from PyQt5.QtWidgets import QApplication
from kiwoom import Kiwoom

if __name__ == "__main__":
    app = QApplication(sys.argv)
    kiwoom = Kiwoom()
    kiwoom.comm_connect()
    
    # Print Account Info after login
    account_cnt = kiwoom.get_login_info("ACCOUNT_CNT")
    account_list = kiwoom.get_login_info("ACCNO")
    
    print(f"Account Count: {account_cnt}")
    print(f"Account List: {account_list}")

    sys.exit(app.exec_())
