# -*- coding: utf-8 -*-
import unittest
import doctest
import logging

import json

import thomas.core
from thomas.core.cpt import CPT
from thomas.core.jpt import JPT
from thomas.core import examples

log = logging.getLogger(__name__)

class TestJPT(unittest.TestCase):

    def test_repr(self):
        """Test repr(jpt)."""
        jpt = examples.get_sprinkler_jpt()
        self.assertTrue(repr(jpt).startswith('JPT(A,B,C,D,E)'))

    def test_compute_dist(self):
        """test jpt.compute_dist()"""
        jpt = examples.get_sprinkler_jpt()

        A = jpt.compute_dist(['A'])
        self.assertTrue(isinstance(A, CPT))
        self.assertAlmostEqual(A['a0'], 0.4)
        self.assertAlmostEqual(A['a1'], 0.6)

        A_B = jpt.compute_dist(['A'], ['B'])
        self.assertTrue(isinstance(A_B, CPT))
        self.assertEqual(A_B.scope, ['B', 'A'])
        self.assertAlmostEqual(A_B['b1', 'a1'], 0.286, places=3)

    def test_sprinkler_jpt(self):
        """Test the JPT for the Sprinkler network."""
        jpt = examples.get_sprinkler_jpt()

        self.assertAlmostEqual(jpt.sum(), 1, places=5)

        AB = jpt.compute_posterior(['A', 'B'], {}, [], {})
        self.assertAlmostEqual(AB.sum(), 1, places=5)

        A = jpt.compute_posterior(['A'], {}, [], {})
        self.assertAlmostEqual(A['a1'], 0.6, places=5)
        self.assertAlmostEqual(A['a0'], 0.4, places=5)

        B_A = jpt.compute_posterior(['B'], {}, ['A'], {})
        self.assertAlmostEqual(B_A['a1', 'b1'], 0.20, places=5)
        self.assertAlmostEqual(B_A['a1', 'b0'], 0.80, places=5)
        self.assertAlmostEqual(B_A['a0', 'b1'], 0.75, places=5)
        self.assertAlmostEqual(B_A['a0', 'b0'], 0.25, places=5)

        # Get a known CPT from disk
        filename = thomas.core.get_pkg_data('sprinkler-D_BC.json')
        with open(filename) as fp:
            data = json.load(fp)

        # We need to round the numbers, cause Pandas is picky ;-)
        D_BC_known = CPT.from_dict(data)
        D_BC_known = D_BC_known.as_series().round(3)

        D_BC_computed = jpt.compute_posterior(['D'], {}, ['B', 'C'], {})
        D_BC_computed = D_BC_computed.as_series().round(3)

        self.assertTrue(D_BC_computed.equals(D_BC_known))

        a0_B = jpt.compute_posterior([], {'A': 'a0'}, ['B'], {})
        self.assertEqual(len(a0_B), 2)

        a0 = jpt.compute_posterior([], {'A': 'a0'}, [], {})
        self.assertAlmostEqual(a0, 0.4, places=5)


