# -*- coding: utf-8 -*-
import unittest
import logging

from thomas.core import error
from thomas.core import examples

log = logging.getLogger(__name__)


class TestJunctionTree(unittest.TestCase):

    def setUp(self):
        self.Gs = examples.get_student_network()

    def test_ensure_cluster(self):
        """Test tree.ensure_cluster()."""
        jt = self.Gs.jt
        Q1 = {'D', 'G', 'I'}
        Q2 = {'L', 'G', 'S'}
        self.assertTrue(jt.get_node_for_set(Q1) is not None)
        self.assertTrue(jt.get_node_for_set(Q2) is None)

        jt.ensure_cluster(Q2)
        self.assertTrue(jt.get_node_for_set(Q2) is not None)

    def test_set_evidence_hard(self):
        """Test tree.set_evidence_hard()."""
        with self.assertRaises(error.InvalidStateError):
            self.Gs.jt.set_evidence_hard(I='i2')

    def test_draw(self):
        """Test tree.draw()."""
        try:
            self.Gs.jt.draw()
        except Exception:
            self.fail("Drawing the tree raised an exception!?")

    def test_edge_repr(self):
        """Test TreeEdge.__repr__()."""
        edge = self.Gs.jt.edges[0]
        self.assertTrue(repr(edge).startswith('Edge:'))
