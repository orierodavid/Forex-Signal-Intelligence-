from types import SimpleNamespace

from forex_intelligence.execution import AccountType, ExecutionRequest
from forex_intelligence.mt5_adapter import MT5Adapter, MT5Config


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def initialize(self, **kwargs):
        self.init_kwargs = kwargs
        return True

    def shutdown(self):
        self.closed = True

    def account_info(self):
        return SimpleNamespace(login=123, server="Exness-MT5Demo", trade_mode=0, balance=10000, equity=10000)

    def symbol_info(self, symbol):
        return SimpleNamespace(visible=True, symbol=symbol)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=1.1000, ask=1.1002)

    def order_send(self, request):
        self.last_request = request
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=77, position=88, price=request["price"])

    def last_error(self):
        return (0, "ok")


def adapter():
    return MT5Adapter(MT5Config(123, "secret", "Exness-MT5Demo"), FakeMT5())


def test_account_info_maps_demo_account():
    info = adapter().account_info()
    assert info.login == 123
    assert info.server == "Exness-MT5Demo"
    assert info.account_type is AccountType.DEMO


def test_connect_does_not_expose_password_in_result():
    mt5 = FakeMT5()
    a = MT5Adapter(MT5Config(123, "secret", "Exness-MT5Demo"), mt5)
    assert a.connect() is True
    assert mt5.init_kwargs["login"] == 123
    assert mt5.init_kwargs["server"] == "Exness-MT5Demo"


def test_submit_verifies_broker_acceptance():
    result = adapter().submit(ExecutionRequest("s1", "EURUSD", "BUY", 0.1, 1.1002, 1.0980, 1.1040))
    assert result.accepted is True
    assert result.order_id == 77
    assert result.position_id == 88
