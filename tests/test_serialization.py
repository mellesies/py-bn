# -*- coding: utf-8 -*-
import unittest
import logging

from thomas.core.models.bn import BayesianNetwork, DiscreteNetworkNode
from thomas.core import examples

log = logging.getLogger(__name__)


class TestSerialization(unittest.TestCase):

    def setUp(self):
        self.Gs = examples.get_student_network()
        self.maxDiff = None

    def test_basic_setup(self):
        """Test instantiation of the Student network."""
        random_vars = ['D', 'I', 'G', 'S', 'L']

        for rv in random_vars:
            self.assertTrue(rv in self.Gs.nodes)
            self.assertTrue(isinstance(self.Gs.nodes[rv], DiscreteNetworkNode))

    def test_serialization(self):
        """Test serialization to and loading from dictionary."""
        serialized = self.Gs.as_dict()
        unserialized = BayesianNetwork.from_dict(serialized)

        self.assertDictEqual(serialized, unserialized.as_dict())
