import re
from enum import Enum, auto
from functools import wraps
from time import time
from typing import Any, Callable, List, Dict

from binance.spot import Spot
from requests.exceptions import ConnectionError, ReadTimeout

from .utils import getChange

###### API Weight constrains
# https://binance-docs.github.io/apidocs/spot/en/#limits

STATS_REQ_PER_MINUTE = 1
PRICE_REQ_PER_MINUTE = round(60 / 3)
TIME_REQ_PER_MINUTE = round(60 / 3)

TIME_WEIGHT = 1
PRICE_WEIGHT = 2
STATS_WEIGHT = 40

TERMCS_WEIGHT = (
    STATS_WEIGHT * STATS_REQ_PER_MINUTE + PRICE_WEIGHT * PRICE_REQ_PER_MINUTE
)

WEIGHT_LIMIT = 1200 - TIME_WEIGHT * TIME_REQ_PER_MINUTE
######


class QuoteCurrency(Enum):
    BUSD = "busd"
    USDT = "usdt"
    BOTH = "both"


class RequestType(Enum):
    PRICE = auto()
    STATS = auto()
    TIME = auto()


def request_wrapper(r_type: RequestType) -> Any:
    """Deal (violently) with connection problems and monitor API weight status"""

    def decorator_request_wrapper(func: Callable) -> Any:
        @wraps(func)
        def fetch(self) -> List:
            try:
                if r_type == RequestType.TIME or self.hasWeightFor(r_type):
                    res = func(self)
                    self.used_weight = int(res["limit_usage"]["x-mbx-used-weight"])
                else:
                    res = {"data": []}

                return res["data"]
            except (ConnectionError, ReadTimeout):
                """
                To prevent the occurrence of NoneType exceptions, an empty list
                is returned as calling app.exit does not immediately terminate the app
                """
                self.kill = True
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
        self.client = Spot(timeout=3, show_limit_usage=True)
        self.kill = False
        self.update_time = 0
        self.used_weight = 0
        self.quote_cur = QuoteCurrency.BOTH
        self.buff = {}
        self.nan = set()
        self.prepBuff()
        self.pair_count = len(self.buff)

    @request_wrapper(RequestType.PRICE)
    def fetchPrices(self) -> List:
        return self.client.ticker_price()

    @request_wrapper(RequestType.STATS)
    def fetchStats(self) -> List:
        return self.client.ticker_24hr()

    @request_wrapper(RequestType.TIME)
    def fetchWeightStatus(self) -> List:
        """calling the cheapest request just to grab the weight usage"""
        return self.client.time()

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

        if ans > PRICE_WEIGHT and r_type == RequestType.PRICE:
            return True
        if ans > STATS_WEIGHT and r_type == RequestType.STATS:
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
        called if self.pattern changed to both usdt & busd
        self.buff will contain the pair with the higher volume
        """
        if self.quote_cur != QuoteCurrency.BOTH:
            return

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

            sym = pair["symbol"]
            base_cur = pair["symbol"][:-4]

            if self.pattern.search(sym) and sym not in self.nan:
                try:
                    self.buff[base_cur]["price"] = float(pair["price"])
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

    def fetchAll(self) -> None:

        """
        fetch current prices & 24H statistics for BUSD | USDT pairs
        store the result in self.buff
        """

        tickers = []
        prices = []

        self.fetchWeightStatus()

        if self.update_time - time() < 0 or len(self.buff) == 0:
            tickers = self.fetchStats()
            self.update_time = time() + self.thresh

        if tickers:
            self.addTickers(tickers)
        else:
            prices = self.fetchPrices()
            self.updateLatestPrices(prices)

        self.pair_count = len(self.buff)
