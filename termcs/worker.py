import re
from enum import Enum, auto
from functools import wraps
from time import time
from typing import Any, Callable, List, Dict

from binance.spot import Spot
from requests.exceptions import ConnectionError, ReadTimeout

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


class Pair(Enum):
    BUSD = auto()
    USDT = auto()
    BOTH = auto()


class RequestType(Enum):
    PRICE = auto()
    STATS = auto()
    TIME = auto()


def request_wrapper(r_type: RequestType) -> Any:
    """
    Deal (violently) with connection problems and monitor API weight status
    TIME requests will always happen hence the subtraction of MONITOR_WEIGHT from the base limit,
    other requests depend on hasWeightFor answer

    https://realpython.com/primer-on-python-decorators/#decorators-with-arguments
    """

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
                since calling app.exit do not terminates the app instantly
                an empty list is returned to avoid NoneType exceptions
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
        self.stats_update = False
        self.update_time = 0
        self.used_weight = 0
        self.pair = Pair.BOTH
        self.buff = {}
        self.nan = []
        self.prepBuff()
        self.asset_count = len(self.buff)

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

    def getChange(self, latest: float, ref: float) -> float:
        """calculate price change"""
        if latest - ref == 0:
            return 0

        return round((latest - ref) / ref * 100, 3)

    def resetBuff(self) -> None:
        self.buff.clear()

    def sortBuff(self, key: str = "change24", rev=True) -> None:
        """sort the assets in the buffer"""
        self.buff = {
            k: v
            for k, v in sorted(
                self.buff.items(), key=lambda asset: asset[1][key], reverse=rev
            )
        }

    def getAssets(self) -> List[Dict]:
        """return a list of the assets"""
        return list(self.buff.values())

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

    def setPair(self, p: Pair) -> None:

        if not self.hasWeightFor(RequestType.STATS):
            return

        self.pair = p
        if p == Pair.BUSD:
            self.pattern = re.compile(
                "^(?![A-Z]+(UP|DOWN|BULL|BEAR)(BUSD))([A-Z]+(BUSD)$)"
            )
        elif p == Pair.USDT:
            self.pattern = re.compile(
                "^(?![A-Z]+(UP|DOWN|BULL|BEAR)(USDT))([A-Z]+(USDT)$)"
            )
        elif p == Pair.BOTH:
            self.pattern = re.compile(
                "^(?![A-Z]+(UP|DOWN|BULL|BEAR)(USDT|BUSD))([A-Z]+(USDT|BUSD)$)"
            )

        self.resetBuff()
        self.prepBuff()

    def prepBuff(self) -> None:
        """
        called if self.pattern changed to both usdt & busd
        self.buff will contain the pair with the highest volume
        """
        if self.pair != Pair.BOTH:
            return

        tickers = self.fetchStats()
        self.update_time = time() + self.thresh

        tmp = set()

        for asset in tickers:

            sym = asset["symbol"]
            name = asset["symbol"][:-4]
            vol = int(float(asset["volume"]))

            if not self.pattern.search(sym):
                continue

            if vol == 0:
                self.nan.append(sym)
                continue

            if name in tmp:
                suffix = asset["symbol"][-4:]
                k = f"{name}USDT" if suffix == "BUSD" else f"{name}BUSD"
                vol_b = self.buff[k]["volume"]

                if vol > vol_b:
                    self.buff[sym] = self.buff.pop(k)
                    self.addAssetToBuff(asset)
            else:
                tmp.add(name)
                self.addAssetToBuff(asset)

    def addAssetToBuff(self, asset: Dict) -> None:
        """add/update asset data"""
        sym = asset["symbol"]
        vol = int(float(asset["volume"]))

        if vol == 0:
            self.nan.append(sym)
            return

        price = float(asset["lastPrice"])
        low = float(asset["lowPrice"])
        high = float(asset["highPrice"])

        self.buff[sym] = {
            "symbol": sym,
            "asset_name": asset["symbol"][:-4],
            "price": price,
            "change24": float(asset["priceChangePercent"]),
            "high": high,
            "low": low,
            "high_change": self.getChange(price, high),
            "low_change": self.getChange(price, low),
            "volume": vol,
        }

    def updateLatestPrices(self, table: List[Dict]) -> None:
        """update latest prices & high/low change"""
        for asset in table:

            sym = asset["symbol"]

            if self.pattern.search(sym) and sym not in self.nan:
                try:
                    self.buff[sym]["price"] = float(asset["price"])
                    self.buff[sym]["low_change"] = self.getChange(
                        self.buff[sym]["price"], self.buff[sym]["low"]
                    )
                    self.buff[sym]["high_change"] = self.getChange(
                        self.buff[sym]["price"], self.buff[sym]["high"]
                    )
                except KeyError:
                    pass

    def addTickers(self, tickers: List[Dict]) -> None:
        """add/update 24H stats"""
        for asset in tickers:

            sym = asset["symbol"]

            if self.pattern.search(sym) and sym not in self.nan:

                price = float(asset["lastPrice"])
                low = float(asset["lowPrice"])
                high = float(asset["highPrice"])

                try:
                    self.buff[sym]["price"] = price
                    self.buff[sym]["change24"] = float(asset["priceChangePercent"])
                    self.buff[sym]["low"] = low
                    self.buff[sym]["high"] = high
                    self.buff[sym]["volume"] = int(float(asset["volume"]))
                    self.buff[sym]["low_change"] = self.getChange(price, low)
                    self.buff[sym]["high_change"] = self.getChange(price, high)
                except KeyError:
                    if self.pair != Pair.BOTH:
                        self.addAssetToBuff(asset)

    def fetchAll(self) -> None:

        """
        fetch current prices & 24H statistics for BUSD | USDT pairs
        store the result in self.buff
        """

        tickers = []
        prices = []
        self.stats_update = False

        self.fetchWeightStatus()

        if self.update_time - time() < 0 or len(self.buff) == 0:
            tickers = self.fetchStats()
            self.update_time = time() + self.thresh
            self.stats_update = True

        if tickers:
            self.addTickers(tickers)
        else:
            prices = self.fetchPrices()
            self.updateLatestPrices(prices)

        self.asset_count = len(self.buff)
