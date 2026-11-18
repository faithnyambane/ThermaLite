import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from thermalite import climate
from thermalite.assumptions import DEFAULT, REF_HDD
from thermalite.data import Sink, Source
from thermalite.osm import CAPS, classify
from thermalite.rank_states import summarize
from thermalite.siting import _Buckets, _fill_nearest, allocate
from thermalite.siting_ui import pack


def src(mw=50.0, lat=47.0, lon=-122.0, temp=30.0):
    return Source("S", "S", lat, lon, mw, "chilled_water", temp, 0.7)


def snk(id, mwh, lat=47.002, lon=-122.0, type="greenhouse", temp=50.0):
    return Sink(id, id, type, lat, lon, mwh, temp)


class Allocation(unittest.TestCase):
    def test_never_allocates_more_heat_than_the_source_has(self):
        s = src(mw=5)  # ~30,660 MWh/yr of source heat
        sinks = [snk(f"K{i}", 20000, lat=47.0 + 0.001 * i) for i in range(1, 6)]
        alloc = allocate(s, sinks, DEFAULT)
        delivered = sum(a["mwh"] for a in alloc)
        # delivered heat = source heat + heat pump electricity, so allow the COP uplift
        self.assertLess(delivered, s.annual_heat_mwh * 1.5)
        self.assertLess(len(alloc), 5)

    def test_each_building_appears_once_and_far_ones_are_skipped(self):
        sinks = [snk("near", 10000), snk("far", 10000, lat=47.5)]
        alloc = allocate(src(), sinks, DEFAULT)
        ids = [a["sink"] for a in alloc]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("far", ids)

    def test_steam_users_get_nothing(self):
        self.assertEqual(allocate(src(), [snk("steam", 50000, type="hospital", temp=180)], DEFAULT), [])


class GridHelpers(unittest.TestCase):
    def test_fill_nearest_fills_inside_gaps_only(self):
        grid = [[1.0, None, 3.0], [None, -1, None]]
        inside = [[1, 1, 1], [0, 1, 1]]
        _fill_nearest(grid, inside)
        self.assertEqual(grid[0][1], 2.0)
        self.assertIsNone(grid[1][0])  # outside the state: untouched
        self.assertGreater(grid[1][1], 0)

    def test_buckets_nearest(self):
        b = _Buckets([(47.0, -122.0), (48.0, -122.0)], key=lambda p: p)
        self.assertAlmostEqual(b.nearest_km(47.01, -122.0), 1.11, delta=0.05)


class DataQuality(unittest.TestCase):
    def test_outdoor_swim_clubs_are_not_heat_users(self):
        self.assertIsNone(classify({"leisure": "sports_centre", "sport": "swimming"}))
        self.assertEqual(classify({"leisure": "sports_centre", "sport": "swimming", "building": "yes"}), "pool")
        self.assertEqual(classify({"leisure": "swimming_pool", "indoor": "yes"}), "pool")

    def test_caps_exist_for_pools_and_hospitals(self):
        self.assertLessEqual(CAPS["pool"], 2000)
        self.assertLessEqual(CAPS["hospital"], 100000)


class ClimateScaling(unittest.TestCase):
    def _run(self, hdd_total, type):
        shape = [hdd_total / 12] * 12
        with mock.patch.object(climate, "fetch_hdd", lambda pts, **k: {p: shape for p in pts}):
            return climate.apply_climate([snk("k", 10000, type=type)])[0]

    def test_reference_climate_leaves_demand_unchanged(self):
        self.assertAlmostEqual(self._run(REF_HDD, "greenhouse").annual_heat_mwh, 10000)

    def test_warmer_climate_needs_less_heat(self):
        self.assertLess(self._run(REF_HDD / 2, "hospital").annual_heat_mwh, 10000)

    def test_pools_ignore_climate(self):
        self.assertAlmostEqual(self._run(REF_HDD / 2, "pool").annual_heat_mwh, 10000)


def _siting_json(cells, sinks):
    return {"state": "XX", "cell_km": 2, "ref_it_mw": 50, "dlat": 0.018, "dlon": 0.026, "grid_co2": 300.0,
            "prices": {"gas": 40, "elec": 100}, "cooling": "chilled_water", "cells": cells, "sinks": sinks}


def _cell(heat, buyers, lat=47.0):
    return {"lat": lat, "lon": -122.0, "heat": heat, "co2t": heat // 10, "bws": 1.0, "cdd": 100, "sub": 2.0,
            "flood": 0, "prot": 0, "water": 0,
            "alloc": [{"sink": b, "mwh": heat // max(1, len(buyers)), "km": 0.5, "net": 1, "co2": 1} for b in buyers]}


class Ranking(unittest.TestCase):
    def test_sites_sharing_a_buyer_are_counted_once(self):
        d = _siting_json([_cell(100, ["A"]), _cell(90, ["A"]), _cell(50, ["B"]), _cell(0, [])],
                         {"A": {}, "B": {}})
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.json"
            p.write_text(json.dumps(d))
            s = summarize(p)
        self.assertEqual(s["independent_sites"], 2)
        self.assertEqual(s["heat_mwh"], 150)
        self.assertEqual(s["viable_cells"], 3)


class UIPacking(unittest.TestCase):
    def test_pack_is_columnar_and_indexes_buyers(self):
        sinks = {"A": {"name": "Greenhouse A", "type": "greenhouse", "lat": 47.0, "lon": -122.0, "demand": 100}}
        d = _siting_json([_cell(0, []), _cell(100, ["A"])], sinks)
        with tempfile.TemporaryDirectory() as t:
            sj, sc, out = Path(t) / "s.json", Path(t) / "src.csv", Path(t) / "ui.json"
            sj.write_text(json.dumps(d))
            sc.write_text("id,name,lat,lon,it_load_mw,cooling\nD1,DC one,47.1,-122.1,20,liquid\n")
            pack("WA", sj, sc, out)
            u = json.loads(out.read_text())
        self.assertEqual(len(u["cols"]["lat"]), 2)
        self.assertEqual(list(u["alloc"]), ["1"])
        self.assertEqual(u["sinks"][u["alloc"]["1"][0][0]][0], "Greenhouse A")
        self.assertEqual(u["dcs"][0][0], "DC one")


if __name__ == "__main__":
    unittest.main()
