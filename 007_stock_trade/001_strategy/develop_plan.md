# Develop Plan: Kiwoom API Auto Trading System

## Goal Description
Build a robust automated trading system using Python and Kiwoom Securities Open API. The system will employ "Quantum Trading" strategies (quantitative/algorithmic), utilize Kiwoom's Condition Search for stock selection, and feature a GUI for real-time monitoring and control.

## User Review Required
> [!IMPORTANT]
> **Kiwoom API Constraints**: The Open API is 32-bit only. Python must be 32-bit, or a 32-bit virtual environment is required. This often complicates development on modern 64-bit systems (especially macOS/Apple Silicon, though Kiwoom is Windows-centric. *Note: If the user is on Mac, they might need to use a Windows VM or remote desktop, as Kiwoom API is Windows-only. I will assume the user has a way to run this, or I should warn them.*)
> **Update**: The user is on macOS. **Kiwoom Open API does NOT run natively on macOS.** It requires Windows. The user might be using a VM (Parallels, VMWare) or a remote Windows server. I will proceed with the code structure, but this is a critical constraint.

## Proposed Changes

### Phase 1: Environment & Basic Connection
#### [NEW] `002_code/kiwoom.py`
- Implement `Kiwoom` class using `QAxWidget` (PyQt5).
- Login functionality (`CommConnect`).
- Event loop handling for asynchronous callbacks.

### Phase 2: Account & Data Retrieval
#### [MODIFY] `002_code/kiwoom.py`
- Add methods to get account info (`GetLoginInfo`, `Opw00018`).
- Add methods to request daily/minute stock data (`Opt10081`, `Opt10080`).

### Phase 3: Strategy & Stock Selection
#### [NEW] `002_code/strategy_manager.py`
- Implement logic to load and activate Kiwoom Condition Search (`GetConditionLoad`, `SendCondition`).
- Handle real-time condition search results (`OnReceiveRealCondition`).

### Phase 4: Order Execution
#### [NEW] `002_code/order_manager.py`
- Implement `SendOrder` for Buy/Sell.
- Implement logic for Split Buying, Stop Loss, and Trailing Stop.
- Handle `OnReceiveChejanData` (Execution confirmation).

### Phase 5: GUI Development
#### [NEW] `002_code/main_gui.py`
- Build the main window using PyQt5.
- **Widgets**:
    - **Log Window**: Display system logs.
    - **Stock List**: Table showing stocks found by strategy.
    - **Account Info**: Real-time balance and P&L.
    - **Trade History**: List of executed trades.
- Connect GUI signals to `Kiwoom` class slots.

### Phase 6: Logging & History
#### [NEW] `002_code/logger.py`
- Setup Python `logging` module.
- Save logs to `003_log/`.
- Database (SQLite) integration for trade history persistence (optional but recommended).

## Verification Plan

### Automated Tests
- Since Kiwoom API requires a live Windows GUI environment and active login, standard unit tests are difficult.
- We will create **mock objects** for the Kiwoom API to test the logic (Strategy, Order Management) in isolation.
- `tests/test_strategy.py`: Test signal generation logic.

### Manual Verification
- **Login Test**: Verify `CommConnect` launches the login window and returns 0.
- **Data Test**: Request Samsung Electronics (005930) price and verify output.
- **Order Test**: (CAUTION) Execute a small buy order on a test account (Mock Investment Server) to verify `SendOrder`.
