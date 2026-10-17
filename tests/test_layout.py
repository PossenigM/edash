from edash.config import DisplayConfig, GridConfig
from edash.render.layout import Box, grid_box


def test_grid_edges_and_gaps():
    display = DisplayConfig(grid=GridConfig(cols=12, rows=8, gap=8, margin=12))
    first = grid_box((0, 0), (1, 1), display)
    second = grid_box((1, 0), (1, 1), display)
    last = grid_box((11, 7), (1, 1), display)
    full = grid_box((0, 0), (12, 8), display)

    assert first.xy == (12, 12)
    assert second.x - first.right == 8
    assert (last.right, last.bottom) == (800 - 12, 480 - 12)
    assert full == Box(12, 12, 800 - 24, 480 - 24)


def test_adjacent_spans_line_up():
    display = DisplayConfig()
    left = grid_box((0, 0), (5, 2), display)
    right = grid_box((5, 0), (7, 2), display)
    assert right.x - left.right == display.grid.gap
    assert left.y == right.y and left.h == right.h


def test_rotated_display_uses_portrait_canvas():
    display = DisplayConfig(rotation=90)
    assert display.logical_size == (480, 800)
    assert grid_box((0, 0), (12, 8), display).right == 480 - display.grid.margin
