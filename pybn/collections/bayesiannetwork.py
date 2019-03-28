# -*- coding: utf-8 -*-
"""Factor: the basis for all reasoning."""
import sys, os
from datetime import datetime as dt

import itertools
from collections import OrderedDict

import numpy as np
import pandas as pd
from pandas.core.dtypes.dtypes import CategoricalDtype
from functools import reduce

import json

import pybn as bn
from ..factors.factor import Factor
from ..factors.cpt import CPT
from ..factors.node import Node

from .bag import Bag

from .. import error


# ------------------------------------------------------------------------------
# BayesianNetwork
# ------------------------------------------------------------------------------
class BayesianNetwork(Bag):
    """A Bayesian Network (BN) consistst of Nodes and Edges.

    Conceptually a BN restricts/extends a Bag of factors by:
    - associating a node with each CPT; to make this possible it also ensures 
      that ...
    - every CPT only has a *single* conditioned variable
    - establishing relationships between the nodes by interpreting conditioning 
      variables to be the parents of the conditioned variable.
    """

    def __init__(self, name, nodes):
        """Instantiate a new BayesianNetwork.

        Args:
            name (str): Name of the Bayesian Network.
            nodes (list): List of Nodes.
        """
        super().__init__(name, nodes)

        self.nodes = {n.RV: n for n in self._factors}
        self.edges = []

        for node in self._factors:
            for parent in node.conditioning:
                self.edges.append((parent, node.RV))

    def __getitem__(self, name):
        """x[name] <==> x.nodes[name]"""
        return self.nodes[name]

    def __repr__(self):
        s = f"<BayesianNetwork name='{self.name}'>\n"
        for n in self._factors:
            s += f"  <Node name='{n.name}' />\n"

        s += '</BayesianNetwork>'

        return s

    def _parse_query_string(self, query_string):
        """Parse a query string into a tuple of query_dist, query_values,
        evidence_dist, evidence_values.

        The query P(I,G=g1|D,L=l0) would imply:
            query_dist = ('I',)
            query_values = {'G': 'g1'}
            evidence_dist = ('D',)
            evidence_values = {'L': 'l0'}
        """
        def split(s):
            dist, values = [], {}
            params = []

            if s:
                params = s.split(',')

            for p in params:
                if '=' in p:
                    key, value = p.split('=')
                    values[key] = value
                else:
                    dist.append(p)

            return dist, values

        query_str, given_str = query_string, ''

        if '|' in query_str:
            query_str, given_str = query_string.split('|')

        return split(query_str) + split(given_str)

    def _complete_case(self, case):
        """..."""
        missing = list(case[case.isna()].index)
        evidence = [e for e in case.index if e not in missing]

        try:
            jpt = self.compute_posterior(
                missing,
                {},
                [],
                evidence_values=case.to_dict()
            )
        except error.InvalidStateError as e:
            print('WARNING - Could not complete case:', e)
            return np.NaN

        # Creata a dataframe by repeating the evicence multiple times
        imputated = pd.DataFrame([case[evidence]] * len(jpt), index=jpt.index)

        # The combinations of missing variables are in the index. Reset the
        # index to make them part of the dataframe.
        imputated = imputated.reset_index()

        # Add the computed probabilities as weights
        imputated.loc[:, 'weight'] = jpt.values

        return imputated

    def _complete_cases(self, incomplete_cases):
        # Create a dataframe that holds *all* unique cases. This way we can
        # complete these cases once and then just count their frequency.

        # drop_duplicates() will work fine with NaNs
        unique_cases = incomplete_cases.drop_duplicates().reset_index(drop=True)

        # apply() yields a Series where each entry holds a DataFrame.
        dfs = unique_cases.apply(self._complete_case, axis=1)
        dfs = dfs.dropna()

        # Add an index to the newly created Series.
        # While set_index() also works with NaNs, but selecting from the index
        # becomes horribly difficult. 
        cols = unique_cases.columns.tolist()
        unique_cases = unique_cases.fillna('NaN')
        dfs.index = unique_cases.set_index(cols).index

        # We can compute the unique cases' counts
        # Also, groupby() doesn't work with NaNs ... 
        incomplete_cases = incomplete_cases.fillna('NaN')
        counts = incomplete_cases.groupby(cols).size()

        return dfs, counts

    def prune(self, Q, e):
        """Prune the graph."""

        # For our purposes, it doesn't matter if a variable is query or evidene.
        vars_to_keep = set(Q + list(e.keys()))

        # Copy the list of edges
        edges = list(self.edges)

        while True:
            # Using zip transforms a list of tuples:
            # [('I', 'S'), ('I', 'G')] --> [('I', 'I'), ('S', 'G')]
            parents, children = list(zip(*edges))
            parents, children = set(parents), set(children)

            # Nodes in 'children' that are not in 'parents' are leaves!
            leaves = children - parents

            # Leaves that can be pruned, should not be in 'vars_to_keep'
            prunable = leaves - vars_to_keep

            # Filter out edges that can be pruned
            edges = [(p, c) for (p, c) in edges if c not in prunable]

            # Stop if there was nothing to remove during this iteration
            if (len(prunable) == 0) or (len(edges) == 0):
                break

        # Its possible that we've removed *all* edges, for instance if Q
        # only contains a parent node.
        if edges:
            parents, children = list(zip(*edges))
        else:
            parents, children = [], []

        nodes = vars_to_keep.union(set(parents + children))        
        factors = [f for f in self._factors if f.RV in nodes]

        return factors

    def compute_posterior(self, query_dist, query_values, evidence_dist, 
        evidence_values, **kwargs):
        """Compute the probability of the query variables given the evidence.

        The query P(I,G=g1|D,L=l0) would imply:
            query_dist = ['I']
            query_values = {'G': 'g1'}
            evidence_dist = ('D',)
            evidence_values = {'L': 'l0'}

        :param tuple query_dist: Random variable to query
        :param dict query_values: Random variable values to query
        :param tuple evidence_dist: Conditioned on evidence
        :param dict evidence_values: Conditioned on values
        :return: pandas.Series (possibly with MultiIndex)
        """
        query_values = bn.add_prefix_to_dict(query_values)

        # evidence_values = {k:v for k,v in evidence_values.items() if isinstance(v, str)}
        evidence_values = bn.remove_none_values_from_dict(evidence_values)
        evidence_values = bn.add_prefix_to_dict(evidence_values)

        # Get a list of *all* variables to query
        query_vars = list(query_values.keys()) + query_dist
        evidence_vars = list(evidence_values.keys()) + evidence_dist

        # First, compute the joint over the query variables and the evidence.
        try:
            # result = self.eliminate(query_vars, evidence_values, **kwargs)
            result = self.eliminate(query_vars + evidence_dist, evidence_values)
            result = result.normalize()
        except error.InvalidStateError as e:
            # print('-' * 80)
            # print(e)
            # print()
            # print('query_vars:', query_vars)
            # print('evidence_values:', evidence_values)
            # Actually, don't deal with this here ... 
            raise

        # At this point, result's scope is over all query and evidence variables
        # If we're computing an entire conditional distribution ...
        if evidence_vars:
            try:
                result = result / result.sum_out(query_vars)
            except:
                print('-' * 80)
                print(f'trying to sum out {query_vars}')
                print(result)
                print('-' * 80)
                raise

        # If query values were specified we can extract them from the factor.
        if query_values:
            levels = list(query_values.keys())
            values = list(query_values.values())

            if result.width == 1:
                result = result[values[0]]

            elif result.width > 1:
                # print(f'values: {values}', f'levels: {levels}')
                # print(result)
                indices = []

                for level, value in query_values.items():
                    # print('-' * 80)
                    # print(level, value)
                    # print('-' * 80)
                    idx = result._data.index.get_level_values(level) == value
                    indices.append(list(idx))

                # result = Factor(result._data.xs(values, level=levels))

                zipped = list(zip(*indices))
                idx = [all(x) for x in zipped]
                result = Factor(result._data[idx])
                # print('indices: ', indices)
                # print('zipped:', zipped)
                # print('idx: ', idx)
                # print('result: ', result)
                # print('-' * 80)


        # The code below only works if eliminate() is called *without* evidence
        # ----------------------------------------------------------------------
        # if evidence_values :
        #     indices = []
        # 
        #     for level, value in evidence_values.items():
        #         idx = result._data.index.get_level_values(level) == value
        #         indices.append(list(idx))
        #         # print('-' * 80)
        #         # print(level, value)
        #         # print('-' * 80)
        # 
        #     zipped = list(zip(*indices))
        #     idx = [all(x) for x in zipped]
        #     # print('indices: ', indices)
        #     # print('zipped:', zipped)
        #     # print('idx: ', idx)
        #     # print('-' * 80)
        #     result = Factor(result._data[idx])

        if isinstance(result, Factor):
            # order = list(evidence_vars) + list(query_vars)
            # order = list(query_vars)
            # result = result.reorder_scope(order)
            result.sort_index()
            return CPT(result, conditioned_variables=query_vars)

        return result

    def MAP(self, query_dist, evidence_values, include_probability=True):
        """Perform a Maximum a Posteriori query."""
        d = self.compute_posterior(query_dist, {}, [], evidence_values)
        evidence_vars = [e for  e in evidence_values.keys() if e in d.scope]

        d = d.droplevel(evidence_vars)

        if include_probability:
            return d.idxmax(), d.max()

        return d.idxmax()

    def P(self, query_string):
        """Return the probability as queried by query_string.

        P('I,G=g1|D,L=l0') is equivalent to calling compute_posterior with:
            query_dist = ('I',)
            query_values = {'G': 'g1'}
            evidence_dist = ('D',)
            evidence_values = {'L': 'l0'}
        """
        qd, qv, gd, gv = self._parse_query_string(query_string)
        return self.compute_posterior(qd, qv, gd, gv)

    def EM_learning(self, data, reset_CPTs=True):
        """Perform parameter learning.

        Sources:
            * https://www.cse.ust.hk/bnbook/pdf/l07.h.pdf
            * https://www.youtube.com/watch?v=NDoHheP2ww4
        """
        pass

    # --- methods for serialization ---
    def as_dict(self):
        """Return a dict representation of this Bayesian Network."""
        return {
            'type': 'BayesianNetwork',
            'name': self.name,
            'edges': self.edges,
            'nodes': [n.as_dict() for n in self._factors]
        }

    def as_json(self, pretty=False):
        """Return a JSON representation (str) of this Bayesian Network."""
        if pretty:
            indent = 4
        else:
            indent = None

        return json.dumps(self.as_dict(), indent=indent)

    def save(self, filename):
        with open(filename, 'w') as fp:
            fp.write(self.as_json(True))

    @classmethod
    def from_dict(self, d):
        """Return a Bayesian Network initialized by its dict representation."""
        name = d.get('name')
        nodes = [Node.from_dict(n) for n in d['nodes']]
        return BayesianNetwork(name, nodes)

    @classmethod
    def from_json(cls, json_str):
        """Return a Bayesian Network initialized by its JSON representation."""
        d = json.loads(json_str)
        return cls.from_dict(d)

    @classmethod
    def open(cls, filename):
        with open(filename) as fp:
            data = fp.read()
            return cls.from_json(data)
