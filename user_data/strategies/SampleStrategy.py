from pandas import DataFrame

from freqtrade.templates.sample_strategy import SampleStrategy as BaseSampleStrategy
from freqtrade.strategy.strategy_helper import merge_informative_pair


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
    startup_candle_count = 240

    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)

        if self.dp:
            btc_df = self.dp.get_pair_dataframe("BTC/USDT", self.timeframe)
            if not btc_df.empty:
                btc_df = btc_df.copy()
                btc_df["btc_ema50"] = btc_df["close"].ewm(span=50, adjust=False).mean()
                btc_df["btc_ema200"] = btc_df["close"].ewm(span=200, adjust=False).mean()
                btc_df["btc_return_12"] = btc_df["close"].pct_change(12)
                btc_df["btc_drawdown_24"] = (
                    btc_df["close"] / btc_df["high"].rolling(24).max()
                ) - 1.0
                btc_df["btc_trend_ok"] = (
                    (btc_df["btc_ema50"] > btc_df["btc_ema200"])
                    & (btc_df["btc_return_12"] > -0.03)
                    & (btc_df["btc_drawdown_24"] > -0.06)
                ).astype(int)
                dataframe = merge_informative_pair(
                    dataframe,
                    btc_df[
                        [
                            "date",
                            "btc_ema50",
                            "btc_ema200",
                            "btc_return_12",
                            "btc_drawdown_24",
                            "btc_trend_ok",
                        ]
                    ],
                    self.timeframe,
                    self.timeframe,
                    append_timeframe=False,
                    suffix="btc",
                )

        dataframe["ema50"] = dataframe["close"].ewm(span=50, adjust=False).mean()
        dataframe["ema200"] = dataframe["close"].ewm(span=200, adjust=False).mean()
        dataframe["ema50_slope"] = dataframe["ema50"].pct_change(5)
        dataframe["ema200_slope"] = dataframe["ema200"].pct_change(10)
        dataframe["vol_mean"] = dataframe["volume"].rolling(20).mean()
        dataframe["vol_ratio"] = dataframe["volume"] / dataframe["vol_mean"]
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
        dataframe["pct_change_12"] = dataframe["close"].pct_change(12)
        dataframe["rolling_low_3"] = dataframe["low"].rolling(3).min()
        dataframe["rolling_low_12"] = dataframe["low"].rolling(12).min()
        dataframe["rolling_high_24"] = dataframe["high"].rolling(24).max()
        dataframe["rolling_high_12"] = dataframe["high"].rolling(12).max()
        dataframe["drawdown_24"] = (
            dataframe["close"] / dataframe["rolling_high_24"]
        ) - 1.0
        dataframe["rebound_from_low"] = (
            dataframe["close"] / dataframe["rolling_low_3"]
        ) - 1.0
        dataframe["rebound_from_swing_low"] = (
            dataframe["close"] / dataframe["rolling_low_12"]
        ) - 1.0
        dataframe["distance_to_ema50"] = (dataframe["close"] / dataframe["ema50"]) - 1.0
        dataframe["distance_to_ema200"] = (dataframe["close"] / dataframe["ema200"]) - 1.0
        dataframe["recent_spike"] = (
            dataframe["candle_range"].rolling(5).max() > 0.03
        ).astype(int)
        dataframe["volatility_expansion"] = (
            dataframe["atr_ratio"] > dataframe["atr_ratio"].rolling(30).mean() * 1.25
        ).astype(int)
        dataframe["rsi_slope"] = dataframe["rsi"].diff(3)
        dataframe["trend_regime"] = (
            (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["adx"] > 20)
            & (dataframe["atr_ratio"] < 0.035)
            & (dataframe["ema50_slope"] > 0.0)
            & (dataframe["ema200_slope"] >= 0.0)
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
        if "btc_trend_ok_btc" in dataframe.columns:
            dataframe["market_regime_ok"] = (
                (dataframe["btc_trend_ok_btc"] == 1)
                | (metadata["pair"] == "BTC/USDT")
            ).astype(int)
        else:
            dataframe["market_regime_ok"] = 1

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = None

        trend_breakout_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["trend_regime"] == 1)
            & (dataframe["chop_regime"] == 0)
            & (dataframe["market_regime_ok"] == 1)
            & (dataframe["close"] > dataframe["bb_middleband"])
            & (dataframe["close"] > dataframe["rolling_high_12"].shift(1) * 0.998)
            & (dataframe["tema"] > dataframe["tema"].shift(1))
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["rsi"] > 50)
            & (dataframe["rsi"] < 66)
            & (dataframe["rsi_slope"] > 0)
            & (dataframe["vol_ratio"] > 1.05)
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
            & (dataframe["market_regime_ok"] == 1)
            & (dataframe["close"] > dataframe["ema200"])
            & (dataframe["close"] > dataframe["ema50"] * 0.995)
            & (dataframe["close"] < dataframe["ema50"] * 1.01)
            & (dataframe["distance_to_ema50"] > -0.006)
            & (dataframe["tema"] > dataframe["tema"].shift(1))
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["rsi"] > 42)
            & (dataframe["rsi"] < 58)
            & (dataframe["rsi_slope"] > 0)
            & (dataframe["recent_spike"] == 0)
        )

        dataframe.loc[trend_pullback_entry, ["enter_long", "enter_tag"]] = (
            1,
            "trend_pullback_entry",
        )

        panic_rebound_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["panic_regime"] == 1)
            & (dataframe["market_regime_ok"] == 1)
            & (dataframe["rebound_from_low"] > 0.01)
            & (dataframe["rebound_from_swing_low"] > 0.012)
            & (dataframe["pct_change_6"] < -0.035)
            & (dataframe["pct_change_3"] > -0.012)
            & (dataframe["pct_change_12"] < -0.025)
            & (dataframe["close"] > dataframe["close"].shift(1))
            & (dataframe["close"] > dataframe["bb_lowerband"])
            & (dataframe["tema"] > dataframe["tema"].shift(1))
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["rsi"] > 30)
            & (dataframe["rsi"] < 55)
            & (dataframe["rsi_slope"] > 0)
            & (dataframe["vol_ratio"] > 1.1)
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
            & (dataframe["ema50_slope"] <= 0)
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

        volatility_reversal_exit = (
            (dataframe["volume"] > 0)
            & (dataframe["volatility_expansion"] == 1)
            & (dataframe["candle_range"] > 0.025)
            & (dataframe["close"] < dataframe["open"])
            & (dataframe["rsi"] > 60)
        )

        dataframe.loc[volatility_reversal_exit, ["exit_long", "exit_tag"]] = (
            1,
            "volatility_reversal_exit",
        )

        return dataframe
