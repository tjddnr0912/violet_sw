import sys
from PyQt5.QtWidgets import *
from PyQt5.QAxContainer import *
from PyQt5.QtCore import *

class Kiwoom(QAxWidget):
    def __init__(self):
        super().__init__()
        self._create_kiwoom_instance()
        self._set_signal_slots()

    def _create_kiwoom_instance(self):
        """
        Kiwoom Open API Control Registration
        """
        self.setControl("KHOPENAPI.KHOpenAPICtrl.1")

    def _set_signal_slots(self):
        """
        Connect API signals to slots
        """
        self.OnEventConnect.connect(self._event_connect)
        self.OnReceiveTrData.connect(self._receive_tr_data)
        self.OnReceiveRealCondition.connect(self._receive_real_condition)
        self.OnReceiveChejanData.connect(self._receive_chejan_data)
        self.OnReceiveConditionVer.connect(self._receive_condition_ver)

    def comm_connect(self):
        """
        Login Request
        """
        self.dynamicCall("CommConnect()")
        self.login_event_loop = QEventLoop()
        self.login_event_loop.exec_()

    def _event_connect(self, err_code):
        """
        Login Callback
        """
        if err_code == 0:
            print("Connected to Kiwoom Server")
            self._load_condition_list()
        else:
            print(f"Connection Failed. Error Code: {err_code}")

        self.login_event_loop.exit()

    def _load_condition_list(self):
        self.dynamicCall("GetConditionLoad()")

    def _receive_condition_ver(self, ret, msg):
        """
        Condition Load Callback
        """
        if ret == 1:
            print("Condition List Loaded Successfully")
            self.condition_list = self.get_condition_list()
        else:
            print("Failed to Load Condition List")

    def get_condition_list(self):
        condition_list = self.dynamicCall("GetConditionNameList()")
        conditions = []
        if condition_list:
            condition_names = condition_list.split(";")
            for name in condition_names:
                if name:
                    index, condition_name = name.split("^")
                    conditions.append((int(index), condition_name))
        return conditions

    def send_condition(self, screen_no, condition_name, condition_index, search_type):
        """
        Send Condition Search Request
        search_type: 0 (General), 1 (Real-time)
        """
        ret = self.dynamicCall("SendCondition(QString, QString, int, int)", screen_no, condition_name, condition_index, search_type)
        if ret == 1:
            print(f"Condition Search Requested: {condition_name}")
        else:
            print(f"Condition Search Request Failed: {condition_name}")

    def _receive_real_condition(self, code, event_type, condition_name, condition_index):
        """
        Real-time Condition Search Callback
        event_type: "I" (Insert), "D" (Delete)
        """
        print(f"[RealTime Condition] Code: {code}, Type: {event_type}, Name: {condition_name}")
        # Signal to Strategy Manager (to be implemented via PyQt Signal if needed)

    def send_order(self, rqname, screen_no, acc_no, order_type, code, qty, price, hoga, origin_order_no):
        """
        Send Order
        order_type: 1:Buy, 2:Sell
        hoga: 00:Limit, 03:Market
        """
        ret = self.dynamicCall("SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                               rqname, screen_no, acc_no, order_type, code, qty, price, hoga, origin_order_no)
        if ret == 0:
            print(f"Order Sent Successfully: {code} {qty}ea")
        else:
            print(f"Order Sending Failed. Error Code: {ret}")

    def _receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        Chejan (Execution) Data Callback
        gubun: 0:Order/Execution, 1:Balance
        """
        if gubun == "0":
            order_no = self.dynamicCall("GetChejanData(int)", 9203)
            code = self.dynamicCall("GetChejanData(int)", 9001)
            order_status = self.dynamicCall("GetChejanData(int)", 913)
            print(f"[Chejan] Order No: {order_no}, Code: {code}, Status: {order_status}")

    def get_login_info(self, tag):
        """
        Get User Info
        TAG: "ACCOUNT_CNT", "ACCNO", "USER_ID", "USER_NAME", "KEY_BSECGB", "FIREW_SECGB"
        """
        ret = self.dynamicCall("GetLoginInfo(QString)", tag)
        return ret

    def set_input_value(self, id, value):
        self.dynamicCall("SetInputValue(QString, QString)", id, value)

    def comm_rq_data(self, rqname, trcode, next, screen_no):
        self.dynamicCall("CommRqData(QString, QString, int, QString)", rqname, trcode, next, screen_no)
        self.tr_event_loop = QEventLoop()
        self.tr_event_loop.exec_()

    def _comm_get_data(self, code, real_type, field_name, index, item_name):
        ret = self.dynamicCall("CommGetData(QString, QString, QString, int, QString)", code, real_type, field_name, index, item_name)
        return ret.strip()

    def _receive_tr_data(self, screen_no, rqname, trcode, record_name, next, unused1, unused2, unused3, unused4):
        if next == '2':
            self.remained_data = True
        else:
            self.remained_data = False

        if rqname == "opw00018_req":
            self._opw00018(rqname, trcode)
        elif rqname == "opt10081_req":
            self._opt10081(rqname, trcode)

        try:
            self.tr_event_loop.exit()
        except AttributeError:
            pass

    def get_account_info(self, account_no):
        self.set_input_value("계좌번호", account_no)
        self.set_input_value("비밀번호", "") # Password is usually handled by the auto-login setting or manual input in the tray
        self.set_input_value("비밀번호입력매체구분", "00")
        self.set_input_value("조회구분", "2")
        self.comm_rq_data("opw00018_req", "opw00018", 0, "2000")

    def _opw00018(self, rqname, trcode):
        total_purchase_price = self._comm_get_data(trcode, "", rqname, 0, "총매입금액")
        total_eval_price = self._comm_get_data(trcode, "", rqname, 0, "총평가금액")
        total_eval_profit_loss_price = self._comm_get_data(trcode, "", rqname, 0, "총평가손익금액")
        total_earning_rate = self._comm_get_data(trcode, "", rqname, 0, "총수익률(%)")
        estimated_deposit = self._comm_get_data(trcode, "", rqname, 0, "추정예탁자산")

        print(f"--- Account Info ---")
        print(f"Total Purchase: {total_purchase_price}")
        print(f"Total Eval: {total_eval_price}")
        print(f"Total Profit/Loss: {total_eval_profit_loss_price}")
        print(f"Total Earning Rate: {total_earning_rate}%")
        print(f"Estimated Deposit: {estimated_deposit}")

    def get_daily_data(self, code, date):
        self.set_input_value("종목코드", code)
        self.set_input_value("기준일자", date)
        self.set_input_value("수정주가구분", "1")
        self.comm_rq_data("opt10081_req", "opt10081", 0, "2000")

    def _opt10081(self, rqname, trcode):
        data_cnt = self.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
        
        print(f"--- Daily Data (Last {data_cnt} days) ---")
        for i in range(data_cnt):
            date = self._comm_get_data(trcode, "", rqname, i, "일자")
            open_price = self._comm_get_data(trcode, "", rqname, i, "시가")
            high_price = self._comm_get_data(trcode, "", rqname, i, "고가")
            low_price = self._comm_get_data(trcode, "", rqname, i, "저가")
            close_price = self._comm_get_data(trcode, "", rqname, i, "현재가")
            volume = self._comm_get_data(trcode, "", rqname, i, "거래량")
            
            print(f"[{date}] O:{open_price} H:{high_price} L:{low_price} C:{close_price} V:{volume}")
