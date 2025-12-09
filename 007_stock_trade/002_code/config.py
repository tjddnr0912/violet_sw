import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TRADING_MODE = os.getenv("TRADING_MODE", "MOCK")
    ACCOUNT_NO = os.getenv("ACCOUNT_NO", "")

    @staticmethod
    def is_mock():
        return Config.TRADING_MODE == "MOCK"
