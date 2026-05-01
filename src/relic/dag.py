"""DAG builder — dependency graph, topological sort, cycle detection."""

from __future__ import annotations

from .constraints import Constraint
from .errors import CyclicDependencyError


class DAG:
    """Directed acyclic graph for constraint dependencies."""

    def __init__(self):
        self.nodes: set[str] = set()
        self.edges: dict[str, list[str]] = {}  # node -> nodes it depends on
        self.constraints: list[Constraint] = []

    def add_node(self, name: str):
        self.nodes.add(name)
        if name not in self.edges:
            self.edges[name] = []

    def add_constraint(self, constraint: Constraint):
        self.add_node(constraint.target_name)
        self.add_node(constraint.source_name)
        self.constraints.append(constraint)
        # target depends on source
        self.edges[constraint.target_name].append(constraint.source_name)

    def topological_sort(self) -> list[str]:
        """Return nodes in topological order. Raises on cycle."""
        # Kahn's algorithm
        in_degree: dict[str, int] = {n: 0 for n in self.nodes}
        adj: dict[str, list[str]] = {n: [] for n in self.nodes}

        for target, sources in self.edges.items():
            for source in sources:
                adj[source].append(target)
                in_degree[target] += 1

        queue = [n for n in self.nodes if in_degree[n] == 0]
        queue.sort()  # deterministic
        order: list[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort()

        if len(order) != len(self.nodes):
            # Find cycle
            remaining = [n for n in self.nodes if n not in set(order)]
            raise CyclicDependencyError(remaining)

        return order

    def get_constraints_for(self, name: str) -> list[Constraint]:
        """Get all constraints that set properties on `name`."""
        return [c for c in self.constraints if c.sets() == name]


def build_dag(constraints: list[Constraint], object_names: set[str]) -> DAG:
    """Build a DAG from constraints and object names."""
    dag = DAG()
    for name in object_names:
        dag.add_node(name)
    for c in constraints:
        dag.add_constraint(c)
    return dag
