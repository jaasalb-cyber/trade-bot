from datetime import datetime

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class RaspiProStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 200

    stoploss = -0.025
    minimal_roi = {
        "120": 0.0,
        "60": 0.015,
        "30": 0.03,
        "0": 0.05,
    }

    trailing_stop = True
    trailing_stop_positive = 0.012
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    use_exit_signal = True

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
    }

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return min(2.0, max_leverage)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["vol_mean"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema50"] > dataframe["ema200"])
                & (dataframe["rsi"] < 38)
                & (dataframe["volume"] > dataframe["vol_mean"])
            ),
            "enter_long",
        ] = 1

        dataframe.loc[
            (
                (dataframe["ema50"] < dataframe["ema200"])
                & (dataframe["rsi"] > 62)
                & (dataframe["volume"] > dataframe["vol_mean"])
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 68, "exit_long"] = 1
        dataframe.loc[dataframe["rsi"] < 32, "exit_short"] = 1
        return dataframe
