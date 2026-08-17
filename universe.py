import json
import time
from pathlib import Path

import requests

from config import DEFAULT_VS_CURRENCY, STABLE_SYMBOLS, UNIVERSE_CACHE_SECONDS

COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
CACHE_PATH = Path(__file__).resolve().parent / "data" / "crypto_universe.json"


def load_cache(limit=250, allow_short=False, allow_stale=False):
    try:
        if not CACHE_PATH.exists():
            return None

        with CACHE_PATH.open("r", encoding="utf-8") as file:
            cache = json.load(file)

        if not allow_stale and time.time() - cache.get("created_at", 0) > UNIVERSE_CACHE_SECONDS:
            return None

        coins = cache.get("coins", [])
        if not allow_short and len(coins) < limit:
            return None

        return coins
    except Exception:
        return None


def save_cache(coins):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", encoding="utf-8") as file:
        json.dump({"created_at": time.time(), "coins": coins}, file, indent=2)


def is_tradeable_coin(coin):
    symbol = str(coin.get("symbol", "")).upper()
    if not symbol or symbol in STABLE_SYMBOLS:
        return False

    if coin.get("current_price") is None or coin.get("total_volume") is None:
        return False

    return float(coin.get("total_volume") or 0) > 0


def fetch_crypto_universe(limit=250):
    pages = max(1, min((limit + 249) // 250, 4))
    coins = []

    for page in range(1, pages + 1):
        try:
            response = requests.get(
                COINGECKO_MARKETS_URL,
                params={
                    "vs_currency": DEFAULT_VS_CURRENCY,
                    "order": "volume_desc",
                    "per_page": 250,
                    "page": page,
                    "sparkline": "false",
                    "price_change_percentage": "1h,24h,7d",
                },
                timeout=20,
            )
            if response.status_code == 429 and coins:
                break
            response.raise_for_status()
            coins.extend(response.json())
        except Exception:
            if coins:
                break
            raise

    cleaned = []
    seen = set()

    for coin in coins:
        symbol = str(coin.get("symbol", "")).upper()
        if symbol in seen or not is_tradeable_coin(coin):
            continue

        seen.add(symbol)
        cleaned.append({
            "id": coin.get("id"),
            "symbol": symbol,
            "ticker": f"{symbol}-USD",
            "name": coin.get("name") or symbol,
            "rank": coin.get("market_cap_rank"),
            "price": coin.get("current_price"),
            "market_cap": coin.get("market_cap") or 0,
            "volume_24h": coin.get("total_volume") or 0,
            "change_1h": coin.get("price_change_percentage_1h_in_currency"),
            "change_24h": coin.get("price_change_percentage_24h_in_currency"),
            "change_7d": coin.get("price_change_percentage_7d_in_currency"),
        })

    return cleaned[:limit]


def get_crypto_universe(limit=250):
    cached = load_cache(limit=limit)
    if cached:
        return cached[:limit]

    try:
        coins = fetch_crypto_universe(limit=max(limit, 250))
        if coins:
            save_cache(coins)
    except Exception:
        coins = load_cache(limit=limit, allow_short=True, allow_stale=True) or []

    if not coins:
        coins = load_cache(limit=limit, allow_short=True, allow_stale=True) or []

    return coins[:limit]
