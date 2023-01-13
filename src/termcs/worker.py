import re
from enum import Enum, auto
from functools import wraps
from time import time
from typing import Any, Callable, List

from binance.spot import Spot
from requests.exceptions import ConnectionError, ReadTimeout

###### API Weight constrains

STATS_REQ_PER_MINUTE = 1
PRICE_REQ_PER_MINUTE = round(60 / 3)

MONITOR_WEIGHT = round(60 / 3)  # calling client.time() every 3 secs
PRICE_WEIGHT = 2
STATS_WEIGHT = 40
TERMCS_WEIGHT = (
    STATS_WEIGHT * STATS_REQ_PER_MINUTE + PRICE_WEIGHT * PRICE_REQ_PER_MINUTE
)

# https://binance-docs.github.io/apidocs/spot/en/#limits
WEIGHT_LIMIT = 1200 - MONITOR_WEIGHT

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
    TIME requests will allways happen hence the subtraction of MONITOR_WEIGHT from the base limit,
    other requests depend on hasWeightFor anwser

    https://realpython.com/primer-on-python-decorators/#decorators-with-arguments
    """

    def decorator_request_wrapper(func: Callable) -> Any:
        @wraps(func)
        def catch(self) -> List:
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

        return catch

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
        self.asset_count = 0
        self.pair = Pair.BOTH
        self.buff = {}
        self.nan = []
        self.prepBuff()

    @request_wrapper(RequestType.PRICE)
    def getPrices(self) -> List:
        return self.client.ticker_price()

    @request_wrapper(RequestType.STATS)
    def getStats(self) -> List:
        return self.client.ticker_24hr()

    @request_wrapper(RequestType.TIME)
    def getWeightStatus(self) -> List:
        """
        calling the cheapest request just to grab the weight usage
        the grabbing itself done in the decorator
        """
        return self.client.time()

    def getChange(self, latest: float, ref: float) -> float:
        """calculate price change"""
        if latest - ref == 0:
            return 0

        return round((latest - ref) / ref * 100, 3)

    def resetBuff(self) -> None:
        self.buff.clear()

    def sortBuff(self) -> None:
        """sort dict according to 24H change percentage"""
        self.buff = {
            k: v
            for k, v in sorted(
                self.buff.items(), key=lambda asset: asset[1]["change24"], reverse=True
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

    def setPairTo(self, p: Pair) -> None:

        # if not self.hasWeightFor(RequestType.STATS):
        #     return

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

        tickers = self.getStats()
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

        self.sortBuff()

    def addAssetToBuff(self, asset: dict) -> None:
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
            "low": low,
            "high": high,
            "volume": vol,
            "low_change": self.getChange(price, low),
            "high_change": self.getChange(price, high),
        }

    def updateLatestPrices(self, table: List[dict]) -> None:
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

    def addTickers(self, tickers: List[dict]) -> None:
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

    def getAll(self) -> List[dict]:

        """
        fetch current prices & 24H statistics for BUSD | USDT pairs
        """

        tickers = []
        prices = []

        self.getWeightStatus()

        if self.update_time - time() < 0 or len(self.buff) == 0:
            tickers = self.getStats()
            self.update_time = time() + self.thresh

        if tickers:
            self.addTickers(tickers)
            self.sortBuff()
        else:
            prices = self.getPrices()
            self.updateLatestPrices(prices)

        self.asset_count = len(self.buff)
        return list(self.buff.values())
