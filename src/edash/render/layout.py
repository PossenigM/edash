from __future__ import annotations

from dataclasses import dataclass

from edash.config import DisplayConfig, GridConfig


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def xy(self) -> tuple[int, int]:
        return self.x, self.y

    @property
    def rect(self) -> tuple[int, int, int, int]:
        """Inclusive corner coordinates, as Pillow's draw functions expect."""
        return self.x, self.y, self.right - 1, self.bottom - 1

    def inset(self, dx: int, dy: int | None = None) -> Box:
        dy = dx if dy is None else dy
        return Box(self.x + dx, self.y + dy, max(0, self.w - 2 * dx), max(0, self.h - 2 * dy))

    def split_top(self, height: int) -> tuple[Box, Box]:
        height = max(0, min(height, self.h))
        return Box(self.x, self.y, self.w, height), Box(self.x, self.y + height, self.w, self.h - height)

    def overlaps(self, other: Box) -> bool:
        return self.x < other.right and other.x < self.right and self.y < other.bottom and other.y < self.bottom

    def fits_in(self, width: int, height: int) -> bool:
        return self.x >= 0 and self.y >= 0 and self.right <= width and self.bottom <= height

    def __str__(self) -> str:
        return f"[{self.x}, {self.y}, {self.w}, {self.h}]"


def check_grid_placement(pos: tuple[int, int], size: tuple[int, int], grid: GridConfig) -> list[str]:
    problems = []
    (col, row), (cols, rows) = pos, size
    if cols < 1 or rows < 1:
        problems.append(f"size {list(size)} must be at least [1, 1]")
    if col < 0 or row < 0:
        problems.append(f"pos {list(pos)} must not be negative")
    if col + cols > grid.cols or row + rows > grid.rows:
        problems.append(f"pos {list(pos)} + size {list(size)} exceeds the {grid.cols}x{grid.rows} grid")
    return problems


def grid_box(pos: tuple[int, int], size: tuple[int, int], display: DisplayConfig) -> Box:
    """Pixel box for a grid placement; neighbouring widgets are separated by exactly ``gap``."""
    width, height = display.logical_size
    g = display.grid
    cell_w = (width - 2 * g.margin - (g.cols - 1) * g.gap) / g.cols
    cell_h = (height - 2 * g.margin - (g.rows - 1) * g.gap) / g.rows
    x0 = round(g.margin + pos[0] * (cell_w + g.gap))
    y0 = round(g.margin + pos[1] * (cell_h + g.gap))
    x1 = round(g.margin + (pos[0] + size[0]) * (cell_w + g.gap) - g.gap)
    y1 = round(g.margin + (pos[1] + size[1]) * (cell_h + g.gap) - g.gap)
    return Box(x0, y0, x1 - x0, y1 - y0)
