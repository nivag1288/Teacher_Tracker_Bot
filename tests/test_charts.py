import base64
import pytest
from visualization.charts import hourly_heatmap, daily_trend, user_bar


def _is_valid_b64_png(s: str) -> bool:
    try:
        data = base64.b64decode(s)
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    except Exception:
        return False


# ── hourly_heatmap ────────────────────────────────────────────────────────────

def test_heatmap_returns_nonempty_string():
    data = [{"hour": 9, "weekday": 1, "count": 5}]
    result = hourly_heatmap(data)
    assert isinstance(result, str)
    assert len(result) > 100


def test_heatmap_returns_valid_png():
    data = [{"hour": 9, "weekday": 1, "count": 5}]
    assert _is_valid_b64_png(hourly_heatmap(data))


def test_heatmap_empty_data():
    result = hourly_heatmap([])
    assert _is_valid_b64_png(result)


def test_heatmap_full_week():
    data = [
        {"hour": h, "weekday": d, "count": h + d}
        for d in range(7)
        for h in range(24)
    ]
    assert _is_valid_b64_png(hourly_heatmap(data))


def test_heatmap_no_filesystem_side_effects(tmp_path):
    data = [{"hour": 0, "weekday": 0, "count": 1}]
    hourly_heatmap(data)
    assert list(tmp_path.iterdir()) == []


# ── daily_trend ───────────────────────────────────────────────────────────────

def test_daily_trend_returns_nonempty_string():
    data = [{"date": "2024-01-01", "count": 10}, {"date": "2024-01-02", "count": 15}]
    result = daily_trend(data)
    assert isinstance(result, str)
    assert len(result) > 100


def test_daily_trend_returns_valid_png():
    data = [{"date": "2024-01-01", "count": 10}]
    assert _is_valid_b64_png(daily_trend(data))


def test_daily_trend_empty_data():
    assert _is_valid_b64_png(daily_trend([]))


def test_daily_trend_single_point():
    data = [{"date": "2024-06-15", "count": 42}]
    assert _is_valid_b64_png(daily_trend(data))


def test_daily_trend_many_points():
    data = [{"date": f"2024-01-{i+1:02d}", "count": i * 3} for i in range(30)]
    assert _is_valid_b64_png(daily_trend(data))


def test_daily_trend_no_filesystem_side_effects(tmp_path):
    data = [{"date": "2024-01-01", "count": 5}]
    daily_trend(data)
    assert list(tmp_path.iterdir()) == []


# ── user_bar ──────────────────────────────────────────────────────────────────

def test_user_bar_returns_nonempty_string():
    data = [{"author_name": "Alice", "count": 50}, {"author_name": "Bob", "count": 30}]
    result = user_bar(data)
    assert isinstance(result, str)
    assert len(result) > 100


def test_user_bar_returns_valid_png():
    data = [{"author_name": "Alice", "count": 10}]
    assert _is_valid_b64_png(user_bar(data))


def test_user_bar_empty_data():
    assert _is_valid_b64_png(user_bar([]))


def test_user_bar_single_user():
    data = [{"author_name": "Solo", "count": 100}]
    assert _is_valid_b64_png(user_bar(data))


def test_user_bar_many_users():
    data = [{"author_name": f"User{i}", "count": 100 - i * 5} for i in range(10)]
    assert _is_valid_b64_png(user_bar(data))


def test_user_bar_no_filesystem_side_effects(tmp_path):
    data = [{"author_name": "Alice", "count": 5}]
    user_bar(data)
    assert list(tmp_path.iterdir()) == []
