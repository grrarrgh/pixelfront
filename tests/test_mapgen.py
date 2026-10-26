"""Map generator checks, run over many seeds.

    python -m unittest discover tests        (from the project folder)

Every generated map must be fully traversable: each tile is either open ground that can be
reached from the bases, or impassable cliff. Cliffs never stand alone, and every ramp is a
proper RAMP_W-wide cut square into a straight cliff wall, leading from low ground up onto a
plateau top.
"""
import os
import random
import sys
import unittest
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pixelfront.world import (generate, CLIFF, RAMP, HIGH, LOW, RIM, RAMP_W, N4)   # noqa: E402

SEEDS = range(60)


def flood(world, start, passable):
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in N4:
            p = (x + dx, y + dy)
            if p not in seen and world.in_bounds(*p) and passable(*p):
                seen.add(p)
                q.append(p)
    return seen


class MapGeneratorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps = [(seed, *generate(random.Random(seed))) for seed in SEEDS]

    def tiles(self, world):
        return ((x, y) for y in range(world.h) for x in range(world.w))

    def test_everything_open_is_reachable(self):
        """All open ground (low ground, plateau tops, ramps) is one connected area."""
        for seed, world, bases, points in self.maps:
            start = (bases[0][0] + 1, bases[0][1] + 1)
            reach = flood(world, start, world.walkable)
            stranded = [p for p in self.tiles(world) if world.walkable(*p) and p not in reach]
            self.assertEqual(stranded, [], f"seed {seed}: open tiles nobody can reach")
            for x, y in bases:
                self.assertIn((x + 1, y + 1), reach, f"seed {seed}: base {(x, y)} cut off")
            for p in points:
                self.assertIn(p, reach, f"seed {seed}: derrick {p} cut off")

    def test_only_cliffs_block(self):
        """The only impassable terrain is cliff; nothing else blocks movement."""
        for seed, world, _, _ in self.maps:
            for x, y in self.tiles(world):
                blocked = not world.walkable(x, y)
                self.assertEqual(blocked, world.tile(x, y) == CLIFF,
                                 f"seed {seed}: tile {(x, y)} blocked={blocked} but tile={world.tile(x, y)}")

    def test_no_lone_cliffs(self):
        """All high ground joins the rocky rim around the map."""
        for seed, world, _, _ in self.maps:
            w, h = world.w, world.h
            rim = [(x, y) for x, y in self.tiles(world) if x < RIM or y < RIM or x >= w - RIM or y >= h - RIM]
            joined = set()
            for p in rim:
                if p not in joined:
                    joined |= flood(world, p, lambda x, y: world.level(x, y) == HIGH)
            lone = [p for p in self.tiles(world) if world.level(*p) == HIGH and p not in joined]
            self.assertEqual(lone, [], f"seed {seed}: cliffs standing on their own")

    def test_plateau_tops_have_cliff_faces(self):
        """A plateau top never touches low ground directly: there's always a cliff (or ramp) between."""
        for seed, world, _, _ in self.maps:
            for x, y in self.tiles(world):
                if world.level(x, y) == HIGH and world.tile(x, y) != CLIFF:
                    for dx, dy in N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                        n = (x + dx, y + dy)
                        if world.in_bounds(*n) and world.level(*n) == LOW:
                            self.assertEqual(world.tile(*n), RAMP,
                                             f"seed {seed}: plateau {(x, y)} touches low ground at {n}")

    def test_ramps_are_aligned(self):
        """Each ramp tile has the plateau top straight behind it and open low ground straight in
        front; ramps are RAMP_W wide and flanked by cliff, i.e. cut square into a wall."""
        for seed, world, _, _ in self.maps:
            seen = set()
            for p in self.tiles(world):
                if world.tile(*p) != RAMP or p in seen:
                    continue
                group = flood(world, p, lambda x, y: world.tile(x, y) == RAMP)
                seen |= group
                dx, dy = world.ramp_dir(*p)
                for x, y in group:
                    self.assertEqual(world.ramp_dir(x, y), (dx, dy), f"seed {seed}: ramp {p} bends")
                    top, foot = (x + dx, y + dy), (x - dx, y - dy)
                    self.assertTrue(world.level(*top) == HIGH and world.tile(*top) != CLIFF,
                                    f"seed {seed}: ramp tile {(x, y)} doesn't lead onto a plateau top")
                    self.assertTrue(world.level(*foot) == LOW and world.walkable(*foot),
                                    f"seed {seed}: ramp tile {(x, y)} doesn't start on open low ground")
                self.assertEqual(len(group), RAMP_W, f"seed {seed}: ramp at {p} is {len(group)} wide")
                # In a straight line across the slope, with cliff at both ends.
                along = {x * dx + y * dy for x, y in group}
                self.assertEqual(len(along), 1, f"seed {seed}: ramp at {p} isn't straight")
                side = (dy, dx)
                across = sorted(x * side[0] + y * side[1] for x, y in group)
                lo, hi = across[0], across[-1]
                (x0, y0) = next(q for q in group if q[0] * side[0] + q[1] * side[1] == lo)
                (x1, y1) = next(q for q in group if q[0] * side[0] + q[1] * side[1] == hi)
                self.assertEqual(world.tile(x0 - side[0], y0 - side[1]), CLIFF, f"seed {seed}: ramp {p} open at one end")
                self.assertEqual(world.tile(x1 + side[0], y1 + side[1]), CLIFF, f"seed {seed}: ramp {p} open at one end")

    def test_every_plateau_can_be_climbed(self):
        """Every plateau top is reached by at least one ramp (it's covered by the reachability
        test too, but this names the culprit)."""
        for seed, world, bases, _ in self.maps:
            tops = {p for p in self.tiles(world) if world.level(*p) == HIGH and world.tile(*p) != CLIFF}
            while tops:
                plateau = flood(world, next(iter(tops)), lambda x, y: (x, y) in tops)
                tops -= plateau
                ramps = [p for p in plateau for dx, dy in N4 if world.in_bounds(p[0] + dx, p[1] + dy)
                         and world.tile(p[0] + dx, p[1] + dy) == RAMP]
                self.assertTrue(ramps, f"seed {seed}: plateau at {next(iter(plateau))} has no ramp")

    def test_point_symmetric(self):
        """Both sides get the same map."""
        for seed, world, _, _ in self.maps:
            w, h = world.w, world.h
            for x, y in self.tiles(world):
                mx, my = w - 1 - x, h - 1 - y
                self.assertEqual(world.tile(x, y) == CLIFF, world.tile(mx, my) == CLIFF,
                                 f"seed {seed}: {(x, y)} and {(mx, my)} differ")
                self.assertEqual(world.level(x, y), world.level(mx, my), f"seed {seed}: heights differ at {(x, y)}")


if __name__ == "__main__":
    unittest.main()
