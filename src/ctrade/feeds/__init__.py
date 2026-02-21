"""Data feed modules for external market data sources."""

from ctrade.feeds.coinmarketcap import CoinMarketCapFeed
from ctrade.feeds.onchain import OnChainFeed
from ctrade.feeds.sentiment import SentimentFeed

__all__ = ["CoinMarketCapFeed", "OnChainFeed", "SentimentFeed"]
