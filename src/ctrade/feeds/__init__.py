"""Data feed modules for external market data sources."""

from ctrade.feeds.coinmarketcap import CoinMarketCapFeed
from ctrade.feeds.cvd import CVDFeed
from ctrade.feeds.derivatives import DerivativesFeed
from ctrade.feeds.market_sentiment import MarketSentimentFeed
from ctrade.feeds.onchain import OnChainFeed
from ctrade.feeds.sentiment import SentimentFeed
from ctrade.feeds.social_velocity import SocialVelocityFeed

__all__ = [
    "CVDFeed",
    "CoinMarketCapFeed",
    "DerivativesFeed",
    "MarketSentimentFeed",
    "OnChainFeed",
    "SentimentFeed",
    "SocialVelocityFeed",
]
