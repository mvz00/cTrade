"""FinBERT-based sentiment classifier for crypto text.

Lazy-loads the ProsusAI/finbert model on first use.  Falls back to a
simple keyword-based classifier if ``transformers`` or ``torch`` cannot
be imported (e.g. on low-RAM machines or if the packages are missing).
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from ctrade.core.enums import SentimentLabel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword fallback lists (used when FinBERT cannot load)
# ---------------------------------------------------------------------------

_BULLISH_KEYWORDS = frozenset({
    "bull", "bullish", "surge", "soar", "rally", "breakout", "moon",
    "pump", "gain", "rise", "jump", "climb", "uptrend", "buy",
    "adoption", "institutional", "etf", "approval", "all-time high",
    "ath", "accumulation", "whale buy", "upgrade", "partnership",
})

_BEARISH_KEYWORDS = frozenset({
    "bear", "bearish", "crash", "dump", "plunge", "sell-off", "selloff",
    "tank", "drop", "fall", "decline", "downtrend", "sell", "ban",
    "hack", "exploit", "rug", "scam", "fraud", "regulation", "sec",
    "lawsuit", "liquidation", "fear", "capitulation", "correction",
})


class SentimentClassifier:
    """Singleton wrapper around FinBERT for crypto text classification.

    The model is **lazy-loaded** on the first call to :meth:`classify` or
    :meth:`classify_batch`.  This avoids a multi-second startup delay and
    ~440 MB memory hit until sentiment analysis is actually needed.

    If the model cannot be loaded (missing packages, OOM, etc.) the
    classifier silently falls back to keyword matching and logs a warning.
    """

    _instance: ClassVar[SentimentClassifier | None] = None

    def __init__(self) -> None:
        self._pipeline = None
        self._model_name = "ProsusAI/finbert"
        self._loaded = False
        self._using_fallback = False

    # ---- singleton --------------------------------------------------------

    @classmethod
    def get_instance(cls) -> SentimentClassifier:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ---- properties -------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def using_fallback(self) -> bool:
        return self._using_fallback

    @property
    def model_name(self) -> str:
        return "keyword-fallback" if self._using_fallback else self._model_name

    # ---- loading ----------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Lazy-load the transformers pipeline.  Runs once."""
        if self._loaded:
            return
        try:
            from transformers import pipeline as hf_pipeline  # type: ignore[import-untyped]

            self._pipeline = hf_pipeline(
                "sentiment-analysis",
                model=self._model_name,
                tokenizer=self._model_name,
                device=-1,  # CPU only
                truncation=True,
                max_length=512,
            )
            self._loaded = True
            self._using_fallback = False
            logger.info("FinBERT model loaded successfully")
        except Exception as exc:
            logger.warning(
                "FinBERT unavailable, falling back to keyword classifier: %s", exc
            )
            self._loaded = True
            self._using_fallback = True

    # ---- public API -------------------------------------------------------

    def classify(self, text: str) -> tuple[SentimentLabel, float]:
        """Classify a single text string.

        Returns ``(label, score)`` where *score* is on a 0-1 scale:
        * 1.0 = very positive / bullish
        * 0.5 = neutral
        * 0.0 = very negative / bearish
        """
        self._ensure_loaded()

        if self._using_fallback:
            return self._keyword_classify(text)

        return self._finbert_classify(text)

    def classify_batch(
        self, texts: list[str]
    ) -> list[tuple[SentimentLabel, float]]:
        """Classify a batch of texts for efficiency."""
        self._ensure_loaded()

        if self._using_fallback:
            return [self._keyword_classify(t) for t in texts]

        return self._finbert_classify_batch(texts)

    # ---- FinBERT implementation -------------------------------------------

    def _finbert_classify(self, text: str) -> tuple[SentimentLabel, float]:
        result = self._pipeline(text)[0]  # type: ignore[index]
        return self._map_finbert_result(result)

    def _finbert_classify_batch(
        self, texts: list[str]
    ) -> list[tuple[SentimentLabel, float]]:
        if not texts:
            return []
        results = self._pipeline(texts)  # type: ignore[misc]
        return [self._map_finbert_result(r) for r in results]

    @staticmethod
    def _map_finbert_result(result: dict) -> tuple[SentimentLabel, float]:
        """Map FinBERT output to ``(SentimentLabel, 0-1 score)``.

        FinBERT returns ``{"label": "positive"|"negative"|"neutral", "score": 0-1}``.
        We convert this so that:
        * positive with confidence *c* → score = 0.5 + c × 0.5  (range 0.5-1.0)
        * negative with confidence *c* → score = 0.5 - c × 0.5  (range 0.0-0.5)
        * neutral → score = 0.5
        """
        raw_label = result["label"].lower()
        confidence = float(result["score"])

        if raw_label == "positive":
            label = SentimentLabel.POSITIVE
            score = 0.5 + confidence * 0.5
        elif raw_label == "negative":
            label = SentimentLabel.NEGATIVE
            score = 0.5 - confidence * 0.5
        else:
            label = SentimentLabel.NEUTRAL
            score = 0.5

        return label, round(max(0.0, min(1.0, score)), 4)

    # ---- Keyword fallback -------------------------------------------------

    @staticmethod
    def _keyword_classify(text: str) -> tuple[SentimentLabel, float]:
        """Simple keyword-based classifier as a fallback."""
        lower = text.lower()
        words = set(re.findall(r"[a-z\-]+", lower))

        bullish_hits = len(words & _BULLISH_KEYWORDS)
        bearish_hits = len(words & _BEARISH_KEYWORDS)
        total = bullish_hits + bearish_hits

        if total == 0:
            return SentimentLabel.NEUTRAL, 0.5

        ratio = bullish_hits / total  # 0 = all bearish, 1 = all bullish

        # Map ratio to 0-1 score (with dampening — keywords aren't very precise)
        if ratio > 0.6:
            label = SentimentLabel.POSITIVE
            score = 0.5 + min(0.3, (ratio - 0.5) * 0.6)
        elif ratio < 0.4:
            label = SentimentLabel.NEGATIVE
            score = 0.5 - min(0.3, (0.5 - ratio) * 0.6)
        else:
            label = SentimentLabel.NEUTRAL
            score = 0.5

        return label, round(max(0.0, min(1.0, score)), 4)
