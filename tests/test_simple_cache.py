from services.simple_cache import SimpleTTLCache


def test_simple_cache_returns_value_before_expiration():
    clock_value = {"now": 10.0}
    cache = SimpleTTLCache(clock=lambda: clock_value["now"])

    cache.set("asset_detail:2025-08-08", {"ok": True}, ttl_seconds=5)

    assert cache.get("asset_detail:2025-08-08") == {"ok": True}


def test_simple_cache_expires_value_after_ttl():
    clock_value = {"now": 10.0}
    cache = SimpleTTLCache(clock=lambda: clock_value["now"])
    cache.set("trade_calendar:SSE:2025-08-08", "value", ttl_seconds=5)

    clock_value["now"] = 15.1

    assert cache.get("trade_calendar:SSE:2025-08-08") is None


def test_simple_cache_clear_namespace_only_removes_matching_keys():
    cache = SimpleTTLCache()
    cache.set("asset_detail:2025-08-08", 1, ttl_seconds=30)
    cache.set("stock_history:000001.SZ", 2, ttl_seconds=30)

    cache.clear_namespace("asset_detail")

    assert cache.get("asset_detail:2025-08-08") is None
    assert cache.get("stock_history:000001.SZ") == 2
