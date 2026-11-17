import math
import unittest
from dataclasses import replace

from thermalite import physics, seasonal
from thermalite.assumptions import DEFAULT
from thermalite.data import Sink, Source, haversine_km
from thermalite.matcher import assign, match_all, score


def src(temp=55.0, mw=20.0, lat=40.5, lon=-74.45, id="S"):
    return Source(id, id, lat, lon, mw, "liquid", temp, 0.8)


def snk(temp=70.0, mwh=60000.0, type="district_energy", lat=40.51, lon=-74.44, id="K"):
    return Sink(id, id, type, lat, lon, mwh, temp)


class Physics(unittest.TestCase):
    def test_direct_exchange_when_source_hotter(self):
        self.assertFalse(physics.needs_heat_pump(60, 35, DEFAULT))
        self.assertTrue(math.isinf(physics.heat_pump_cop(60, 35, DEFAULT)))
        self.assertEqual(physics.delivered_from_source(100, math.inf), 100)
        self.assertEqual(physics.electricity_for(100, math.inf), 0)

    def test_cop_falls_as_lift_grows(self):
        self.assertGreater(physics.heat_pump_cop(30, 50, DEFAULT), physics.heat_pump_cop(30, 80, DEFAULT))

    def test_energy_balance(self):
        cop = physics.heat_pump_cop(30, 75, DEFAULT)
        delivered = physics.delivered_from_source(1000, cop)
        work = physics.electricity_for(delivered, cop)
        self.assertAlmostEqual(delivered, 1000 + work)

    def test_cop_matches_carnot_formula(self):
        # source 30, sink 75, approach 5 -> 80 C hot side, 25 C cold side, lift 55 K
        expected = 0.5 * (80 + 273.15) / 55
        self.assertAlmostEqual(physics.heat_pump_cop(30, 75, DEFAULT), expected)


class Seasonal(unittest.TestCase):
    def test_profiles_sum_to_one(self):
        for name, p in seasonal.PROFILES.items():
            self.assertEqual(len(p), 12, name)
            self.assertAlmostEqual(sum(p), 1.0, msg=name)

    def test_flat_demand_fully_served_by_flat_supply(self):
        used, _ = seasonal.utilized(1000, 1000, seasonal.PROFILES["flat"])
        self.assertAlmostEqual(used, 1000)

    def test_hdd_shape_replaces_illustrative_curve(self):
        hdd = [500, 400, 300, 150, 50, 0, 0, 0, 20, 100, 250, 450]
        p = seasonal.profile_for("district_energy", hdd_shape=hdd)
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertNotEqual(p, seasonal.PROFILES["space_and_water"])
        # flat-profile sinks ignore climate
        self.assertEqual(seasonal.profile_for("pool", hdd_shape=hdd), seasonal.PROFILES["flat"])

    def test_seasonal_demand_wastes_summer_supply(self):
        used, _ = seasonal.utilized(1000, 1000, seasonal.PROFILES["space_heating"])
        self.assertLess(used, 1000)


class Matching(unittest.TestCase):
    def test_haversine_one_degree_latitude(self):
        self.assertAlmostEqual(haversine_km(40, -74, 41, -74), 111.2, delta=0.2)

    def test_steam_sink_rejected(self):
        m = score(src(), snk(temp=180))
        self.assertFalse(m.feasible)
        self.assertIn("steam", m.reason)

    def test_close_hot_water_sink_viable(self):
        m = score(src(), snk())
        self.assertTrue(m.feasible, m.reason)
        self.assertGreater(m.co2_avoided_t, 0)

    def test_distance_kills_economics(self):
        near = score(src(), snk())
        far = score(src(), snk(lat=41.2, lon=-74.44))
        self.assertGreater(near.net_annual_usd, far.net_annual_usd)
        self.assertGreater(far.route_km, far.breakeven_route_km)
        self.assertFalse(far.feasible)

    def test_search_radius(self):
        a = replace(DEFAULT, max_search_km=1.0)
        self.assertEqual(match_all([src()], [snk(lat=41.0)], a), [])

    def test_assign_uses_each_source_once(self):
        sources = [src()]
        sinks = [snk(id="K1"), snk(id="K2", lat=40.52)]
        chosen = assign(match_all(sources, sinks))
        self.assertEqual(len(chosen), 1)


class Ingest(unittest.TestCase):
    def test_atlas_centroid_polygon_and_point(self):
        from thermalite.atlas import centroid
        sq = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
        self.assertEqual(centroid(sq), (1.0, 1.0))
        self.assertEqual(centroid({"type": "Point", "coordinates": [-74, 40]}), (40, -74))

    def test_osm_area_100m_square(self):
        from thermalite.osm import polygon_area_m2
        d_lat = 100 / 111_320
        d_lon = 100 / (111_320 * math.cos(math.radians(40)))
        sq = [{"lat": 40, "lon": -74}, {"lat": 40, "lon": -74 + d_lon},
              {"lat": 40 + d_lat, "lon": -74 + d_lon}, {"lat": 40 + d_lat, "lon": -74}]
        self.assertAlmostEqual(polygon_area_m2(sq), 10_000, delta=50)

    def test_osm_classify(self):
        from thermalite.osm import classify
        self.assertEqual(classify({"building": "greenhouse"}), "greenhouse")
        self.assertEqual(classify({"amenity": "hospital"}), "hospital")
        self.assertIsNone(classify({"building": "house"}))


class Sensitivity(unittest.TestCase):
    def test_incentive_never_reduces_viable_heat(self):
        from thermalite.sensitivity import incentive_curve
        sources = [src(id="S1"), src(id="S2", temp=30, lat=40.6)]
        sinks = [snk(id="K1"), snk(id="K2", temp=50, type="greenhouse", lat=40.55),
                 snk(id="K3", lat=40.62, type="hospital", temp=80)]
        curve = incentive_curve(sources, sinks)
        pairs = [r["viable_pairs"] for r in curve]
        self.assertEqual(pairs, sorted(pairs))


if __name__ == "__main__":
    unittest.main()
