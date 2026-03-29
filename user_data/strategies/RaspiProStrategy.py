from datetime import datetime

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class RaspiProStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 200

    stoploss = -0.015
    minimal_roi = {
        "120": 0.0,
        "60": 0.015,
        "30": 0.03,
        "0": 0.05,
    }

    trailing_stop = False
    use_exit_signal = True

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "emergency_exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "stoploss_on_exchange": False,
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
        return min(1.0, max_leverage)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["vol_mean"] = dataframe["volume"].rolling(20).mean()
        dataframe["candle_range"] = (
            (dataframe["high"] - dataframe["low"]) / dataframe["close"]
        )
        dataframe["atr_ratio"] = dataframe["atr"] / dataframe["close"]
        dataframe["pct_change_1"] = dataframe["close"].pct_change()
        dataframe["pct_change_3"] = dataframe["close"].pct_change(3)
        dataframe["pct_change_6"] = dataframe["close"].pct_change(6)
        dataframe["rolling_low_3"] = dataframe["low"].rolling(3).min()
        dataframe["rolling_high_24"] = dataframe["high"].rolling(24).max()
        dataframe["drawdown_24"] = (
            dataframe["close"] / dataframe["rolling_high_24"]
        ) - 1.0
        dataframe["rebound_from_low"] = (
            dataframe["close"] / dataframe["rolling_low_3"]
        ) - 1.0

        # Pause new entries for 5 candles after any large expansion candle.
        dataframe["recent_spike"] = (
            dataframe["candle_range"].rolling(5).max() > 0.025
        ).astype(int)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        calm_trend_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["close"] > dataframe["ema200"])
            & (dataframe["close"] > dataframe["ema50"])
            & (dataframe["close"] < dataframe["ema50"] * 1.01)
            & (dataframe["candle_range"] < 0.015)
            & (dataframe["pct_change_1"] < 0.01)
            & (dataframe["pct_change_3"] < 0.02)
            & (dataframe["volume"] < dataframe["vol_mean"] * 2.0)
            & (dataframe["atr_ratio"] < 0.015)
            & (dataframe["recent_spike"] == 0)
            & (dataframe["rsi"] > 45)
            & (dataframe["rsi"] < 62)
        )

        dataframe.loc[
            calm_trend_entry,
            ["enter_long", "enter_tag"],
        ] = (1, "calm_trend_entry")

        dip_rebound_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["drawdown_24"] < -0.04)
            & (dataframe["pct_change_6"] < -0.03)
            & (dataframe["rebound_from_low"] > 0.008)
            & (dataframe["pct_change_1"] > 0.002)
            & (dataframe["close"] > dataframe["close"].shift(1))
            & (dataframe["rsi"] > 32)
            & (dataframe["rsi"] < 52)
        )

        dataframe.loc[
            dip_rebound_entry,
            ["enter_long", "enter_tag"],
        ] = (1, "dip_rebound_entry")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (
                    (dataframe["close"] > dataframe["ema50"] * 1.03)
                    & (dataframe["rsi"] > 70)
                )
                | (dataframe["close"] < dataframe["ema50"])
                | (dataframe["candle_range"] > 0.025)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "spike_protection_exit")
        return dataframe
