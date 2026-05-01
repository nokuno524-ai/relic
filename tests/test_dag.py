"""Tests for the DAG builder."""

import pytest
from relic.dag import DAG, build_dag
from relic.constraints import Constraint
from relic.errors import CyclicDependencyError


def test_topological_sort_simple():
    dag = DAG()
    dag.add_node("A")
    dag.add_node("B")
    dag.add_constraint(Constraint("B", "left", "A", "right", 10.0))
    order = dag.topological_sort()
    assert order.index("A") < order.index("B")


def test_cycle_detection():
    dag = DAG()
    dag.add_node("A")
    dag.add_node("B")
    dag.add_constraint(Constraint("B", "left", "A", "right"))
    dag.add_constraint(Constraint("A", "left", "B", "right"))
    with pytest.raises(CyclicDependencyError):
        dag.topological_sort()


def test_build_dag():
    constraints = [
        Constraint("B", "left", "A", "right", 25.0),
        Constraint("C", "left", "B", "right", 25.0),
    ]
    dag = build_dag(constraints, {"A", "B", "C"})
    order = dag.topological_sort()
    assert order.index("A") < order.index("B") < order.index("C")


def test_no_constraints():
    dag = build_dag([], {"A", "B"})
    order = dag.topological_sort()
    assert set(order) == {"A", "B"}
