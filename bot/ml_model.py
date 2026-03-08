"""
Machine Learning Price Prediction Model.
Uses Random Forest and Gradient Boosting ensemble.
Predicts short-term price movement probability.
"""
import numpy as np
import pandas as pd
import time
from dataclasses import dataclass
from bot.logger import log, C
from bot.config import config

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    log.warning("sklearn not installed. pip install scikit-learn")

import ta


@dataclass
class MLPrediction:
    up_probability: float = 0.5
    down_probability: float = 0.5
    confidence: float = 0.0       # 0-100
    prediction: str = "NEUTRAL"   # UP, DOWN, NEUTRAL
    model_accuracy: float = 0.0   # last training accuracy


class MLModel:
    def __init__(self):
        self.rf_model = None
        self.gb_model = None
        self.scaler = StandardScaler() if HAS_SKLEARN else None
        self.is_trained = False
        self.last_train_time = 0
        self.last_accuracy = 0
        self.feature_names = []

    def _build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract ML features from klines DataFrame."""
        features = pd.DataFrame()
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # Price features
        features["returns_1"] = close.pct_change(1)
        features["returns_3"] = close.pct_change(3)
        features["returns_5"] = close.pct_change(5)
        features["returns_10"] = close.pct_change(10)
        features["returns_20"] = close.pct_change(20)

        # Volatility
        features["volatility_5"] = close.rolling(5).std() / close
        features["volatility_20"] = close.rolling(20).std() / close
        features["range_pct"] = (high - low) / close

        # RSI
        features["rsi"] = ta.momentum.RSIIndicator(close, window=14).rsi()
        features["rsi_change"] = features["rsi"].diff(3)

        # MACD
        macd = ta.trend.MACD(close)
        features["macd_hist"] = macd.macd_diff()
        features["macd_hist_change"] = features["macd_hist"].diff(3)

        # EMAs
        ema20 = ta.trend.EMAIndicator(close, window=20).ema_indicator()
        ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator()
        features["ema_ratio"] = ema20 / ema50
        features["price_vs_ema20"] = (close - ema20) / ema20

        # Bollinger
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        features["bb_position"] = (close - bb.bollinger_lband()) / (bb.bollinger_hband() - bb.bollinger_lband())
        features["bb_width"] = (bb.bollinger_hband() - bb.bollinger_lband()) / close

        # ATR
        atr = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()
        features["atr_pct"] = atr / close

        # Volume
        features["volume_ratio"] = volume / volume.rolling(20).mean()
        features["volume_change"] = volume.pct_change(3)

        # Buy pressure
        taker_buy = df["taker_buy_base"].astype(float)
        features["buy_pressure"] = taker_buy / volume

        # Stochastic RSI
        stoch = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
        features["stoch_k"] = stoch.stochrsi_k()

        # Higher timeframe momentum (using larger rolling windows)
        features["trend_20"] = (close - close.rolling(20).mean()) / close.rolling(20).mean()
        features["trend_50"] = (close - close.rolling(50).mean()) / close.rolling(50).mean()

        self.feature_names = features.columns.tolist()
        return features

    def _build_labels(self, df: pd.DataFrame, lookahead: int = 5) -> pd.Series:
        """Create labels: 1 if price goes up in next N candles, 0 if down."""
        future_return = df["close"].shift(-lookahead) / df["close"] - 1
        # 1 = up more than 0.1%, 0 = down more than 0.1%, drop neutral
        labels = pd.Series(np.where(future_return > 0.001, 1,
                                    np.where(future_return < -0.001, 0, np.nan)))
        return labels

    def train(self, df: pd.DataFrame) -> float:
        """Train the ML models on historical data."""
        if not HAS_SKLEARN:
            log.warning("Cannot train ML - sklearn not installed")
            return 0.0

        if df is None or len(df) < 100:
            log.warning("Not enough data for ML training")
            return 0.0

        try:
            features = self._build_features(df)
            labels = self._build_labels(df)

            # Combine and drop NaN
            combined = pd.concat([features, labels.rename("target")], axis=1).dropna()
            if len(combined) < 50:
                return 0.0

            X = combined.drop("target", axis=1)
            y = combined["target"]

            # Split
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

            # Scale
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            # Train Random Forest
            self.rf_model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
            self.rf_model.fit(X_train_scaled, y_train)
            rf_acc = self.rf_model.score(X_test_scaled, y_test)

            # Train Gradient Boosting
            self.gb_model = GradientBoostingClassifier(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42)
            self.gb_model.fit(X_train_scaled, y_train)
            gb_acc = self.gb_model.score(X_test_scaled, y_test)

            # Combined accuracy
            accuracy = (rf_acc + gb_acc) / 2
            self.last_accuracy = accuracy
            self.is_trained = True
            self.last_train_time = time.time()

            log.info(f"ML trained: RF={C.green(f'{rf_acc:.1%}')} GB={C.green(f'{gb_acc:.1%}')} Avg={C.white(f'{accuracy:.1%}')}")
            return accuracy

        except Exception as e:
            log.error(f"ML training error: {e}")
            return 0.0

    def predict(self, df: pd.DataFrame) -> MLPrediction:
        """Predict price direction using trained models."""
        result = MLPrediction()

        if not self.is_trained or not HAS_SKLEARN:
            return result

        try:
            features = self._build_features(df)
            if features.empty:
                return result

            # Get latest features
            latest = features.iloc[-1:].dropna(axis=1)
            if latest.empty:
                return result

            # Ensure same features as training
            missing = set(self.feature_names) - set(latest.columns)
            for col in missing:
                latest[col] = 0
            latest = latest[self.feature_names]

            scaled = self.scaler.transform(latest)

            # Random Forest prediction
            rf_proba = self.rf_model.predict_proba(scaled)[0]
            rf_up = rf_proba[1] if len(rf_proba) > 1 else 0.5

            # Gradient Boosting prediction
            gb_proba = self.gb_model.predict_proba(scaled)[0]
            gb_up = gb_proba[1] if len(gb_proba) > 1 else 0.5

            # Ensemble (average)
            result.up_probability = (rf_up + gb_up) / 2
            result.down_probability = 1 - result.up_probability

            # Confidence = how far from 50/50
            result.confidence = abs(result.up_probability - 0.5) * 200  # 0-100

            # Prediction
            if result.up_probability > 0.55:
                result.prediction = "UP"
            elif result.down_probability > 0.55:
                result.prediction = "DOWN"
            else:
                result.prediction = "NEUTRAL"

            result.model_accuracy = self.last_accuracy

            return result

        except Exception as e:
            log.error(f"ML prediction error: {e}")
            return result

    def should_retrain(self) -> bool:
        """Check if model needs retraining."""
        if not self.is_trained:
            return True
        hours_since = (time.time() - self.last_train_time) / 3600
        return hours_since >= config.ML_RETRAIN_HOURS
