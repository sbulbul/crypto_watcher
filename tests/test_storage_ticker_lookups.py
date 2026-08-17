import time

from storage import list_ticker_lookups, save_ticker_lookup


def test_save_and_list_ticker_lookups_round_trip(temp_db):
    looked_up_at = time.time()

    lookup_id = save_ticker_lookup(
        ticker="AAPL",
        price=231.42,
        price_type="live",
        recommendation="Hold",
        looked_up_at=looked_up_at,
    )

    assert lookup_id is not None

    rows = list_ticker_lookups(limit=10)

    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["price"] == 231.42
    assert rows[0]["price_type"] == "live"
    assert rows[0]["recommendation"] == "Hold"
    assert rows[0]["looked_up_at"] == looked_up_at


def test_list_ticker_lookups_orders_most_recent_first(temp_db):
    save_ticker_lookup(
        ticker="AAPL", price=100.0, price_type="live",
        recommendation="Buy", looked_up_at=1_000.0,
    )
    save_ticker_lookup(
        ticker="MSFT", price=200.0, price_type="last_close",
        recommendation="Sell", looked_up_at=2_000.0,
    )

    rows = list_ticker_lookups(limit=10)

    assert [row["ticker"] for row in rows] == ["MSFT", "AAPL"]


def test_list_ticker_lookups_respects_limit(temp_db):
    for index in range(5):
        save_ticker_lookup(
            ticker=f"T{index}", price=10.0 + index, price_type="live",
            recommendation="Hold", looked_up_at=float(index),
        )

    rows = list_ticker_lookups(limit=2)

    assert len(rows) == 2
