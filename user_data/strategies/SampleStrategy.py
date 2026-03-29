from pandas import DataFrame

from freqtrade.templates.sample_strategy import SampleStrategy as BaseSampleStrategy


class SampleStrategy(BaseSampleStrategy):
    """
    Regime-based local override of Freqtrade's SampleStrategy.

    This strategy trades only long and focuses on three states:
    - trend continuation when the market is healthy
    - trend pullbacks inside an established uptrend
    - panic rebounds after a sharp selloff once recovery begins
    It avoids chop where indicator signals are usually noisy.
    """

    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)

        dataframe["ema50"] = dataframe["close"].ewm(span=50, adjust=False).mean()
        dataframe["ema200"] = dataframe["close"].ewm(span=200, adjust=False).mean()
        dataframe["vol_mean"] = dataframe["volume"].rolling(20).mean()
        dataframe["candle_range"] = (
            (dataframe["high"] - dataframe["low"]) / dataframe["close"]
        )
        tr_components = DataFrame(
            {
                "hl": dataframe["high"] - dataframe["low"],
                "hc": (dataframe["high"] - dataframe["close"].shift(1)).abs(),
                "lc": (dataframe["low"] - dataframe["close"].shift(1)).abs(),
            }
        )
        dataframe["true_range"] = tr_components.max(axis=1)
        dataframe["atr"] = dataframe["true_range"].rolling(14).mean()
        dataframe["atr_ratio"] = dataframe["atr"] / dataframe["close"]
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
        dataframe["recent_spike"] = (
            dataframe["candle_range"].rolling(5).max() > 0.03
        ).astype(int)
        dataframe["trend_regime"] = (
            (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["adx"] > 20)
            & (dataframe["atr_ratio"] < 0.035)
        ).astype(int)
        dataframe["panic_regime"] = (
            (dataframe["drawdown_24"] < -0.05)
            & (dataframe["atr_ratio"] > 0.008)
        ).astype(int)
        dataframe["chop_regime"] = (
            (
                (dataframe["adx"] < 16)
                | (dataframe["bb_width"] < 0.018)
                | (dataframe["volume"] < dataframe["vol_mean"] * 0.8)
            )
            & (dataframe["panic_regime"] == 0)
        ).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = None

        trend_breakout_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["trend_regime"] == 1)
            & (dataframe["chop_regime"] == 0)
            & (dataframe["close"] > dataframe["bb_middleband"])
            & (dataframe["tema"] > dataframe["tema"].shift(1))
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["rsi"] > 50)
            & (dataframe["rsi"] < 66)
            & (dataframe["volume"] > dataframe["vol_mean"] * 1.05)
            & (dataframe["recent_spike"] == 0)
        )

        dataframe.loc[trend_breakout_entry, ["enter_long", "enter_tag"]] = (
            1,
            "trend_breakout_entry",
        )

        trend_pullback_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["trend_regime"] == 1)
            & (dataframe["chop_regime"] == 0)
            & (dataframe["close"] > dataframe["ema200"])
            & (dataframe["close"] > dataframe["ema50"] * 0.995)
            & (dataframe["close"] < dataframe["ema50"] * 1.01)
            & (dataframe["tema"] > dataframe["tema"].shift(1))
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["rsi"] > 42)
            & (dataframe["rsi"] < 58)
            & (dataframe["recent_spike"] == 0)
        )

        dataframe.loc[trend_pullback_entry, ["enter_long", "enter_tag"]] = (
            1,
            "trend_pullback_entry",
        )

        panic_rebound_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["panic_regime"] == 1)
            & (dataframe["rebound_from_low"] > 0.01)
            & (dataframe["pct_change_6"] < -0.035)
            & (dataframe["pct_change_3"] > -0.012)
            & (dataframe["close"] > dataframe["close"].shift(1))
            & (dataframe["tema"] > dataframe["tema"].shift(1))
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["rsi"] > 30)
            & (dataframe["rsi"] < 55)
        )

        dataframe.loc[panic_rebound_entry, ["enter_long", "enter_tag"]] = (
            1,
            "panic_rebound_entry",
        )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = None

        momentum_fade_exit = (
            (dataframe["volume"] > 0)
            & (dataframe["tema"] < dataframe["tema"].shift(1))
            & (dataframe["rsi"] > 68)
            & (dataframe["close"] > dataframe["bb_middleband"])
        )

        dataframe.loc[momentum_fade_exit, ["exit_long", "exit_tag"]] = (
            1,
            "momentum_fade_exit",
        )

        trend_loss_exit = (
            (dataframe["volume"] > 0)
            & (dataframe["close"] < dataframe["ema50"])
            & (dataframe["macd"] < dataframe["macdsignal"])
            & (dataframe["rsi"] < 46)
        )

        dataframe.loc[trend_loss_exit, ["exit_long", "exit_tag"]] = (
            1,
            "trend_loss_exit",
        )

        failed_rebound_exit = (
            (dataframe["volume"] > 0)
            & (dataframe["panic_regime"] == 1)
            & (dataframe["close"] < dataframe["ema50"])
            & (dataframe["tema"] < dataframe["tema"].shift(1))
        )

        dataframe.loc[failed_rebound_exit, ["exit_long", "exit_tag"]] = (
            1,
            "failed_rebound_exit",
        )

        return dataframe
