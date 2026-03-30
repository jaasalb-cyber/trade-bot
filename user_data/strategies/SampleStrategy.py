from pandas import DataFrame

from freqtrade.templates.sample_strategy import SampleStrategy as BaseSampleStrategy
from freqtrade.strategy import DecimalParameter, IntParameter
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
    startup_candle_count = 120
    max_ranked_entries = 3
    market_pairs = ("BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT")

    pullback_close_below_ema = DecimalParameter(1.001, 1.015, default=1.006, decimals=3, space="buy")
    pullback_close_above_ema = DecimalParameter(0.992, 1.0, default=0.998, decimals=3, space="buy")
    pullback_max_ema_distance = DecimalParameter(
        -0.008, -0.001, default=-0.0035, decimals=4, space="buy"
    )
    pullback_rsi_min = IntParameter(40, 52, default=45, space="buy")
    pullback_rsi_max = IntParameter(52, 62, default=56, space="buy")
    pullback_rsi_slope_min = DecimalParameter(0.0, 2.0, default=0.5, decimals=2, space="buy")
    pullback_vol_ratio_min = DecimalParameter(0.8, 1.2, default=0.95, decimals=2, space="buy")
    trend_adx_min = IntParameter(16, 28, default=20, space="buy")

    failed_pullback_loss = DecimalParameter(-0.01, -0.002, default=-0.003, decimals=3, space="sell")
    failed_pullback_max_age = IntParameter(20, 120, default=90, space="sell")
    profit_lock_min = DecimalParameter(0.004, 0.02, default=0.008, decimals=3, space="sell")

    def informative_pairs(self):
        return [(pair, self.timeframe) for pair in self.market_pairs]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)

        if self.dp:
            for market_pair in self.market_pairs:
                informative_df = self.dp.get_pair_dataframe(market_pair, self.timeframe)
                if informative_df.empty:
                    continue

                informative_df = informative_df.copy()
                pair_key = market_pair.split("/")[0].lower()
                informative_df[f"{pair_key}_ema50"] = informative_df["close"].ewm(
                    span=50, adjust=False
                ).mean()
                informative_df[f"{pair_key}_ema200"] = informative_df["close"].ewm(
                    span=200, adjust=False
                ).mean()
                informative_df[f"{pair_key}_return_12"] = informative_df["close"].pct_change(12)
                informative_df[f"{pair_key}_drawdown_24"] = (
                    informative_df["close"] / informative_df["high"].rolling(24).max()
                ) - 1.0
                informative_df[f"{pair_key}_trend_ok"] = (
                    (informative_df[f"{pair_key}_ema50"] > informative_df[f"{pair_key}_ema200"])
                    & (informative_df[f"{pair_key}_return_12"] > -0.03)
                    & (informative_df[f"{pair_key}_drawdown_24"] > -0.06)
                ).astype(int)

                dataframe = merge_informative_pair(
                    dataframe,
                    informative_df[
                        [
                            "date",
                            f"{pair_key}_ema50",
                            f"{pair_key}_ema200",
                            f"{pair_key}_return_12",
                            f"{pair_key}_drawdown_24",
                            f"{pair_key}_trend_ok",
                        ]
                    ],
                    self.timeframe,
                    self.timeframe,
                    append_timeframe=False,
                    suffix=pair_key,
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
            & (dataframe["adx"] > self.trend_adx_min.value)
            & (dataframe["atr_ratio"] < 0.035)
            & (dataframe["ema50_slope"] > 0.0)
            & (dataframe["ema200_slope"] >= 0.0)
        ).astype(int)
        dataframe["panic_regime"] = (
            (dataframe["drawdown_24"] < -0.03)
            & (dataframe["atr_ratio"] > 0.006)
        ).astype(int)
        dataframe["chop_regime"] = (
            (
                (dataframe["adx"] < 16)
                | (dataframe["bb_width"] < 0.018)
                | (dataframe["volume"] < dataframe["vol_mean"] * 0.8)
            )
            & (dataframe["panic_regime"] == 0)
        ).astype(int)
        market_trend_columns = [
            f"{pair.split('/')[0].lower()}_trend_ok_{pair.split('/')[0].lower()}"
            for pair in self.market_pairs
            if f"{pair.split('/')[0].lower()}_trend_ok_{pair.split('/')[0].lower()}" in dataframe.columns
        ]
        if market_trend_columns:
            dataframe["market_strength"] = dataframe[market_trend_columns].sum(axis=1)
            dataframe["market_regime_ok"] = (
                (dataframe["market_strength"] >= 2)
                | (
                    metadata["pair"] in self.market_pairs
                    and dataframe[
                        f"{metadata['pair'].split('/')[0].lower()}_trend_ok_{metadata['pair'].split('/')[0].lower()}"
                    ]
                    == 1
                )
            ).astype(int)
        else:
            dataframe["market_strength"] = 0
            dataframe["market_regime_ok"] = 1
        dataframe["setup_score"] = 0.0

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = None

        trend_pullback_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["trend_regime"] == 1)
            & (dataframe["chop_regime"] == 0)
            & (dataframe["market_regime_ok"] == 1)
            & (dataframe["market_strength"] >= 2)
            & (dataframe["close"] > dataframe["ema200"])
            & (dataframe["close"] > dataframe["ema50"] * self.pullback_close_above_ema.value)
            & (dataframe["close"] < dataframe["ema50"] * self.pullback_close_below_ema.value)
            & (dataframe["distance_to_ema50"] > self.pullback_max_ema_distance.value)
            & (dataframe["tema"] > dataframe["tema"].shift(1))
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["rsi"] > self.pullback_rsi_min.value)
            & (dataframe["rsi"] < self.pullback_rsi_max.value)
            & (dataframe["rsi_slope"] > self.pullback_rsi_slope_min.value)
            & (dataframe["vol_ratio"] > self.pullback_vol_ratio_min.value)
            & (dataframe["pct_change_3"] > -0.003)
            & (dataframe["recent_spike"] == 0)
        )

        dataframe.loc[trend_pullback_entry, ["enter_long", "enter_tag"]] = (
            1,
            "trend_pullback_entry",
        )
        dataframe.loc[trend_pullback_entry, "setup_score"] = (
            40
            + (dataframe["adx"] * 0.4)
            + ((0.01 - dataframe["distance_to_ema50"].abs()).clip(lower=0) * 800)
            + (dataframe["rsi_slope"] * 2)
            + (dataframe["market_strength"] * 2)
        )

        raw_trend_breakout_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["trend_regime"] == 1)
            & (dataframe["chop_regime"] == 0)
            & (dataframe["market_regime_ok"] == 1)
            & (dataframe["market_strength"] >= 3)
            & (dataframe["close"] > dataframe["ema50"] * 1.006)
            & (dataframe["close"] > dataframe["rolling_high_12"].shift(1) * 1.002)
            & (dataframe["close"] > dataframe["rolling_high_24"].shift(1) * 1.001)
            & (dataframe["ema50_slope"] > 0.002)
            & (dataframe["tema"] > dataframe["tema"].shift(1))
            & (dataframe["macd"] > dataframe["macdsignal"])
            & (dataframe["rsi"] > 58)
            & (dataframe["rsi"] < 66)
            & (dataframe["rsi_slope"] > 1.0)
            & (dataframe["vol_ratio"] > 1.2)
            & (dataframe["atr_ratio"] < 0.022)
            & (dataframe["recent_spike"] == 0)
        )
        trend_breakout_entry = raw_trend_breakout_entry & (dataframe["enter_long"] == 0)

        dataframe.loc[trend_breakout_entry, ["enter_long", "enter_tag"]] = (
            1,
            "trend_breakout_entry",
        )
        dataframe.loc[trend_breakout_entry, "setup_score"] = (
            46
            + (dataframe["adx"] * 0.5)
            + (dataframe["vol_ratio"] * 4)
            + (dataframe["rsi_slope"] * 2)
            + (dataframe["market_strength"] * 2)
            - (dataframe["atr_ratio"] * 200)
        )

        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        if side != "long" or not self.dp:
            return True

        ranked_candidates: list[tuple[str, float]] = []
        for whitelist_pair in self.dp.current_whitelist():
            df, _ = self.dp.get_analyzed_dataframe(whitelist_pair, self.timeframe)
            if df.empty:
                continue
            last_candle = df.iloc[-1]
            if int(last_candle.get("enter_long", 0)) != 1:
                continue
            ranked_candidates.append((whitelist_pair, float(last_candle.get("setup_score", 0.0))))

        if not ranked_candidates:
            return True

        ranked_candidates.sort(key=lambda item: item[1], reverse=True)
        allowed_pairs = {
            candidate_pair
            for candidate_pair, _score in ranked_candidates[: self.max_ranked_entries]
        }

        return pair in allowed_pairs

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

    def custom_exit(
        self,
        pair: str,
        trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ):
        if not self.dp:
            return None

        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or len(df) < 2:
            return None

        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        trade_age_minutes = (current_time - trade.open_date_utc).total_seconds() / 60
        entry_tag = trade.enter_tag or ""

        # Exit weak pullbacks early instead of waiting for the broader trend-loss signal.
        if entry_tag == "trend_pullback_entry":
            if (
                trade_age_minutes <= self.failed_pullback_max_age.value
                and current_profit < self.failed_pullback_loss.value
                and last_candle["close"] < last_candle["ema50"]
                and last_candle["macd"] < last_candle["macdsignal"]
                and last_candle["rsi_slope"] <= 0
            ):
                return "failed_pullback_exit"

        if entry_tag == "trend_breakout_entry":
            if (
                trade_age_minutes <= 180
                and current_profit < -0.006
                and (
                    last_candle["close"] < last_candle["ema50"]
                    or last_candle["macd"] < last_candle["macdsignal"]
                )
                and last_candle["rsi"] < 52
            ):
                return "failed_breakout_exit"

            if (
                trade_age_minutes >= 45
                and current_profit > 0.003
                and last_candle["tema"] < prev_candle["tema"]
                and last_candle["macd"] < last_candle["macdsignal"]
            ):
                return "breakout_protect_exit"

        # Once a trade is in profit, protect it if momentum starts fading.
        if current_profit > self.profit_lock_min.value:
            if (
                last_candle["tema"] < prev_candle["tema"]
                or last_candle["macd"] < last_candle["macdsignal"]
                or last_candle["rsi"] > 67
            ):
                return "profit_lock_exit"

        return None
