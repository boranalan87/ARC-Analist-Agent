import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('ls20_replay', Path(__file__).resolve().parents[1] / 'tools' / 'ls20_replay.py')
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class RouteChecks(unittest.TestCase):
    def test_all_routes_valid(self):
        for route in MOD.ROUTES.values():
            self.assertTrue(route)
            self.assertTrue(set(route) <= set('UDLR'))

    def test_first_route(self):
        self.assertEqual(MOD.ROUTES['level1'], 'UUUULLLDURRRUUU')

    def test_known_level4_prefix_not_marked_complete(self):
        self.assertEqual(MOD.EXPECTED_LEVELS, 3)

if __name__ == '__main__':
    unittest.main()
