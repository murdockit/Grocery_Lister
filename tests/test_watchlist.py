from app.watchlist import load_watchlist


def test_load_watchlist_normalizes_terms(tmp_path):
    path = tmp_path / "watchlist.yaml"
    path.write_text(
        """
items:
  - name: chicken thighs
    good_price: 2.00
    unit: lb
categories:
  - fresh fruit
max_list_size: 5
min_discount_pct: 20
""",
        encoding="utf-8",
    )

    watchlist = load_watchlist(path)

    assert watchlist.search_terms == ["chicken thighs", "fresh fruit"]
    assert watchlist.items[0].good_price == 2
    assert watchlist.max_list_size == 5


def test_blocklist_filters_search_terms(tmp_path):
    path = tmp_path / "watchlist.yaml"
    path.write_text(
        """
items:
  - name: chicken thighs
  - name: liver
categories:
  - fresh fruit
blocklist:
  - liver
""",
        encoding="utf-8",
    )

    watchlist = load_watchlist(path)

    assert watchlist.search_terms == ["chicken thighs", "fresh fruit"]
    assert watchlist.is_blocked("Kroger Chicken Liver Pate")
    assert not watchlist.is_blocked("Kroger Chicken Thighs")
