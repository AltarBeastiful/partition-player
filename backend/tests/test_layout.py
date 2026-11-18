from partition_player.pipeline.layout import make_layout, measure_bounds

GEOMETRY = {
    "image": [1920, 2560],
    "chain": {"crop": [100, 200], "resize": [0.5, 0.5], "scale": 0.8, "k": 2.5},
    "systems": [
        {"index": 0, "unit": 10.0, "min_x": 100.0, "max_x": 1100.0, "top_y": 300.0, "staffs": 1,
         "bars": [101.0, 350.0, 600.0, 850.0, 1099.0], "measures": 4},
        {"index": 1, "unit": 10.0, "min_x": 100.0, "max_x": 1100.0, "top_y": 700.0, "staffs": 1,
         "bars": [350.0], "measures": 3},  # one barline missed: even split
    ],
    "staves": [
        {"index": 0, "system": 0, "voice": 0, "unit": 10.0, "min_x": 100.0, "max_x": 1100.0, "top_y": 300.0, "bottom_y": 340.0},
        {"index": 1, "system": 1, "voice": 0, "unit": 10.0, "min_x": 100.0, "max_x": 1100.0, "top_y": 700.0, "bottom_y": 740.0},
    ],
}


def test_bars_give_measure_bounds_when_they_agree():
    assert measure_bounds(GEOMETRY["systems"][0]) == [100.0, 350.0, 600.0, 850.0, 1100.0]
    assert measure_bounds(GEOMETRY["systems"][1]) == [100.0, 100.0 + 1000 / 3, 100.0 + 2000 / 3, 1100.0]


def test_layout_maps_to_review_pixels():
    review = {"width": 1800, "height": 2400, "scale": 0.5}
    layout = make_layout(GEOMETRY, review, measure_count=7)
    assert layout["width"] == 1800 and len(layout["systems"]) == 2
    s0, s1 = layout["systems"]
    # working x=100 -> upload (100/0.5 + 100)/0.8 = 375 -> review 187.5
    assert (s0["x0"], s0["x1"]) == (187.5, 1437.5)
    assert s0["top"] == (300 / 0.5 + 200) / 0.8 * 0.5 and s0["staves"][0]["bottom"] == (340 / 0.5 + 200) / 0.8 * 0.5
    assert [m["index"] for m in s0["measures"]] == [0, 1, 2, 3] and [m["index"] for m in s1["measures"]] == [4, 5, 6]
    assert s0["measures"][1] == {"index": 1, "x0": 500.0, "x1": 812.5}


def test_layout_spreads_measures_when_counts_disagree():
    review = {"width": 1800, "height": 2400, "scale": 0.5}
    layout = make_layout(GEOMETRY, review, measure_count=9)  # the score has two more than the systems say
    idx = [[m["index"] for m in s["measures"]] for s in layout["systems"]]
    assert idx == [[0, 1, 2, 3, 4], [5, 6, 7, 8]]
