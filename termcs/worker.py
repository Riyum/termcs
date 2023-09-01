import json
import re
from enum import Enum, auto
from functools import wraps
from time import time, gmtime
from typing import Callable, Dict, List
from threading import Thread

from requests import get
from requests.exceptions import ConnectionError, Timeout
from websockets.sync.client import connect

from .utils import getChange

###### API Weight constrains
# https://binance-docs.github.io/apidocs/spot/en/#limits

STATS_REQ_PER_MINUTE = 1
STATS_WEIGHT = 80

PING_REQ_PER_MINUTE = 60 / 3
PING_WEIGHT = 1

TERMCS_WEIGHT = STATS_WEIGHT * STATS_REQ_PER_MINUTE + PING_WEIGHT * PING_REQ_PER_MINUTE

WEIGHT_LIMIT = 6000
######


class QuoteCurrency(Enum):
    BUSD = "busd"
    USDT = "usdt"
    BOTH = "both"


class RequestType(Enum):
    STATS = auto()
    PING = auto()


def request_wrapper(r_type: RequestType) -> Callable:
    """Deal with connection problems and monitor API weight status"""

    def decorator_request_wrapper(func: Callable) -> Callable:
        @wraps(func)
        def fetch(self) -> List:
            url = func(self)
            try:
                if self.hasWeightFor(r_type):
                    res = get(url, timeout=2)
                    self.used_weight = int(res.headers["x-mbx-used-weight"])
                else:
                    return []

                return res.json()

            except ConnectionError:
                """
                To prevent the occurrence of NoneType exceptions, an empty list
                is returned as calling app.exit does not immediately terminate the app
                """
                self.stop = True
                return []

            except Timeout:
                return []

        return fetch

    return decorator_request_wrapper


class Worker:
    """
    fetch market data from Binance

    Args:
        thresh(int): amount of seconds before the next 24H stast update
    """

    def __init__(self, thresh: int = 120) -> None:
        self.thresh = thresh
        self.pattern = re.compile(
            "^(?![A-Z]+(UP|DOWN|BULL|BEAR)(USDT|BUSD))([A-Z]+(USDT|BUSD)$)"
        )
        self.stop = False
        self.update_time = 0
        self.used_weight = 0
        self.quote_cur = QuoteCurrency.BOTH
        self.buff = {}
        self.nan = set()
        self.prepBuff()
        self.pair_count = len(self.buff)

    @request_wrapper(RequestType.PING)
    def ping(self) -> str:
        return "https://api.binance.com/api/v3/ping"

    @request_wrapper(RequestType.STATS)
    def fetchStats(self) -> str:
        return "https://api.binance.com/api/v3/ticker/24hr"

    def resetBuff(self) -> None:
        self.buff.clear()

    def sortBuff(self, key: str = "change24", rev=True) -> None:
        """sort the pairs in the buffer"""
        self.buff = {
            k: v
            for k, v in sorted(
                self.buff.items(), key=lambda asset: asset[1][key], reverse=rev
            )
        }

    def hasWeightFor(self, r_type: RequestType, user=False) -> bool:
        """return true if the request can be made according to the used weight"""
        if user:
            ans = WEIGHT_LIMIT - TERMCS_WEIGHT - self.used_weight
        else:
            ans = WEIGHT_LIMIT - self.used_weight

        if ans > STATS_WEIGHT and r_type == RequestType.STATS:
            return True
        if ans > PING_WEIGHT and r_type == RequestType.PING:
            return True

        return False

    def setQuoteCurrency(self, qc: QuoteCurrency) -> bool:

        if not self.hasWeightFor(RequestType.STATS, True):
            return False

        try:
            self.quote_cur = QuoteCurrency(qc)
        except ValueError:
            self.quote_cur = QuoteCurrency.BOTH

        if self.quote_cur == QuoteCurrency.BUSD:
            p = "^(?![A-Z]+(UP|DOWN|BULL|BEAR)(BUSD))([A-Z]+(BUSD)$)"
        elif self.quote_cur == QuoteCurrency.USDT:
            p = "^(?![A-Z]+(UP|DOWN|BULL|BEAR)(USDT))([A-Z]+(USDT)$)"
        else:
            p = "^(?![A-Z]+(UP|DOWN|BULL|BEAR)(USDT|BUSD))([A-Z]+(USDT|BUSD)$)"

        self.pattern = re.compile(p)
        self.resetBuff()
        self.prepBuff()
        return True

    def prepBuff(self) -> None:
        """
        called when buff was cleared.

        if self.pattern changed to both usdt & busd
        self.buff will contain the pair with the higher volume
        """

        tickers = self.fetchStats()
        self.update_time = time() + self.thresh

        for pair in tickers:

            sym = pair["symbol"]
            vol = int(float(pair["volume"]))

            if not self.pattern.search(sym):
                continue

            if vol == 0:
                self.nan.add(sym)
                continue

            base_cur = pair["symbol"][:-4]
            quote_cur = pair["symbol"][-4:]

            if base_cur in self.buff:
                if quote_cur != self.buff[base_cur]["quote_cur"]:
                    if vol > self.buff[base_cur]["volume"]:
                        self.addPairToBuff(pair)
                    continue
            else:
                self.addPairToBuff(pair)

    def addPairToBuff(self, pair: Dict) -> None:
        """add/update pair data"""

        sym = pair["symbol"]
        vol = int(float(pair["volume"]))

        if vol == 0:
            self.nan.add(sym)
            return

        base_cur = pair["symbol"][:-4]
        price = float(pair["lastPrice"])
        low = float(pair["lowPrice"])
        high = float(pair["highPrice"])

        self.buff[base_cur] = {
            "quote_cur": pair["symbol"][-4:],
            "price": price,
            "change24": float(pair["priceChangePercent"]),
            "high": high,
            "low": low,
            "high_change": getChange(price, high),
            "low_change": getChange(price, low),
            "volume": vol,
        }

    def updateLatestPrices(self, table: List[Dict]) -> None:
        """update latest prices & high/low change"""
        for pair in table:

            sym = pair["s"]
            base_cur = pair["s"][:-4]
            quote_cur = pair["s"][-4:]

            if self.pattern.search(sym) and sym not in self.nan:
                try:
                    if quote_cur != self.buff[base_cur]["quote_cur"]:
                        return
                    self.buff[base_cur]["price"] = float(pair["c"])
                    self.buff[base_cur]["low_change"] = getChange(
                        self.buff[base_cur]["price"], self.buff[base_cur]["low"]
                    )
                    self.buff[base_cur]["high_change"] = getChange(
                        self.buff[base_cur]["price"], self.buff[base_cur]["high"]
                    )
                except KeyError:
                    pass

    def addTickers(self, tickers: List[Dict]) -> None:
        """add/update 24H stats"""
        for pair in tickers:

            sym = pair["symbol"]
            base_cur = pair["symbol"][:-4]

            if self.pattern.search(sym) and sym not in self.nan:

                price = float(pair["lastPrice"])
                low = float(pair["lowPrice"])
                high = float(pair["highPrice"])

                try:
                    self.buff[base_cur]["price"] = price
                    self.buff[base_cur]["change24"] = float(pair["priceChangePercent"])
                    self.buff[base_cur]["low"] = low
                    self.buff[base_cur]["high"] = high
                    self.buff[base_cur]["volume"] = int(float(pair["volume"]))
                    self.buff[base_cur]["low_change"] = getChange(price, low)
                    self.buff[base_cur]["high_change"] = getChange(price, high)
                except KeyError:
                    if self.quote_cur != QuoteCurrency.BOTH:
                        self.addPairToBuff(pair)

    def getWorkerThread(self) -> Thread:
        """
        return a thread that will fetch the current prices & 24H statistics
        for BUSD | USDT pairs and store the result in self.buff
        """

        def filler() -> None:

            prices = []

            try:
                # connect to Binance websocket
                with connect("wss://stream.binance.com:443/ws") as websocket:
                    # subscribe to a stream
                    websocket.send(
                        json.dumps(
                            {
                                "method": "SUBSCRIBE",
                                "params": ["!miniTicker@arr"],
                                "id": 1,
                            }
                        )
                    )
                    # start populating self.buff with market data
                    while not self.stop:
                        if self.update_time - time() < 0:
                            self.addTickers(self.fetchStats())
                            self.update_time = time() + self.thresh
                        else:
                            if gmtime(time()).tm_sec % 3 == 0:
                                self.ping()
                            try:
                                prices = json.loads(websocket.recv(timeout=2))
                            except TimeoutError:
                                pass
                            if type(prices) != dict:
                                self.updateLatestPrices(prices)

                        self.pair_count = len(self.buff)
                        prices.clear()

            except Exception:
                self.stop = True

        return Thread(target=filler, daemon=True)
