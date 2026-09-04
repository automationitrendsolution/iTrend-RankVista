"""Line chart geometry: paths, gaps, axis ticks and hover payloads."""

from __future__ import annotations

import json

from apps.analytics import charts

LABELS = ["Jan", "Feb", "Mar", "Apr"]


def test_no_data_reports_nothing_to_draw():
    assert charts.build(labels=[], series=[]).has_data is False
    assert charts.build(labels=LABELS, series=[]).has_data is False


def test_all_zero_series_is_not_plotted():
    """A flat zero line would divide by a zero axis maximum."""
    chart = charts.build(labels=LABELS, series=[{"year": "2025", "values": [0, 0, 0, 0]}])
    assert chart.has_data is False


def test_single_series_spans_the_plot_area():
    chart = charts.build(labels=LABELS, series=[{"year": "2025", "values": [10, 20, 30, 40]}])
    assert chart.has_data
    row = chart.series[0]
    assert row.name == "2025"
    assert row.total == 100
    assert row.path.startswith("M ")
    assert row.points[0]["x"] == charts.PAD_LEFT
    assert row.points[-1]["x"] == charts.WIDTH - charts.PAD_RIGHT
    # The peak lands on the top gridline at worst, never above the plot area.
    assert row.points[-1]["y"] >= charts.PAD_TOP
    assert row.points[0]["y"] <= charts.HEIGHT - charts.PAD_BOTTOM


def test_gaps_break_the_line_instead_of_inventing_points():
    chart = charts.build(labels=LABELS, series=[{"year": "2025", "values": [5, None, None, 9]}])
    row = chart.series[0]
    assert row.path.count("M") == 2
    assert [point["i"] for point in row.points] == [0, 3]


def test_series_keep_distinct_colours():
    series = [{"year": str(2020 + n), "values": [n + 1] * 4} for n in range(4)]
    colours = {row.color for row in charts.build(labels=LABELS, series=series).series}
    assert len(colours) == 4


def test_points_carry_their_bucket_for_aligned_hover():
    """Hover matches series on the bucket index, so a short year drops out cleanly."""
    chart = charts.build(
        labels=LABELS,
        series=[
            {"year": "2025", "values": [1, 2, 3, 4]},
            {"year": "2026", "values": [9, 8, None, None]},
        ],
    )
    long_year, short_year = chart.series
    assert [point["i"] for point in short_year.points] == [0, 1]
    assert max(point["i"] for point in long_year.points) == 3
    assert json.loads(short_year.hover)[0]["series"] == "2026"


def test_axis_ticks_are_readable_and_positioned():
    chart = charts.build(labels=LABELS, series=[{"year": "2025", "values": [0, 400_000, 900_000, 1_117_926]}])
    assert [tick["label"] for tick in chart.y_ticks] == ["0", "312.5K", "625K", "937.5K", "1.25M"]
    assert chart.y_ticks[0]["pct"] > chart.y_ticks[-1]["pct"]
    assert chart.left_pct == round(charts.PAD_LEFT / charts.WIDTH * 100, 3)


def test_dense_axes_are_thinned():
    labels = [f"W{n + 1}" for n in range(53)]
    chart = charts.build(labels=labels, series=[{"year": "2025", "values": list(range(1, 54))}])
    assert len(chart.x_ticks) <= 14
    assert chart.x_ticks[0]["label"] == "W1"


def test_explicit_total_wins_over_the_plotted_sum():
    chart = charts.build(
        labels=LABELS, series=[{"year": "2025", "values": [1, None, 3, 4], "total": 999}]
    )
    assert chart.series[0].total == 999


def test_nice_ceiling_keeps_headroom_tight():
    assert charts._nice_ceiling(1_117_926) == 1_250_000
    assert charts._nice_ceiling(98) == 100
    assert charts._nice_ceiling(0) == 1.0
