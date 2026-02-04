from typing import List, Tuple

import networkx as nx

from nortl.core import CoreEngine


class NetworkXRenderer:
    """This class contains the methods to render a nortl to verilog code.

    It only represents states and their transitions without representing the conditions.
    """

    def __init__(self, engine: CoreEngine):
        self.engine = engine

        self.transitions: List[Tuple[str, str]] = []
        self.indent_level = 0

    def render(self) -> nx.Graph:  # type: ignore
        """Render the engine to a networkx graph."""
        g = nx.DiGraph()  # type: ignore
        for states in self.engine.states.values():
            for state in states:
                g.add_node(state.name)
                for _, next_state in state.transitions:
                    g.add_edge(state.name, next_state.name)

        return g
