from typing import List, Tuple

from nortl.core.protocols import EngineProto, StateProto


class MermaidRenderer:
    """This class contains the methods to render a nortl to a mermaid state diagram.

    Note that only states and transitions are shown. For transitions, the conditions are omitted.
    It's purpose is to support illustration only!
    """

    # FIXME: Include Fork/Joins

    def __init__(self, engine: EngineProto):
        self.engine = engine

        self.transitions: List[Tuple[str, str]] = []
        self.indent_level = 0

    def _add_transition(self, s1: StateProto, s2: StateProto) -> None:
        self.transitions.append((s1.name, s2.name))

    def render(self) -> str:
        for states in self.engine.states.values():
            for state in states:
                for _, next_state in state.transitions:
                    self._add_transition(state, next_state)

        # Generate the mermaid code
        ret = '---\n'
        ret += f'title {self.engine.module_name}\n'
        ret += '---\n'
        ret += 'stateDiagram-v2\n'
        for s1, s2 in self.transitions:
            ret += f'    {s1} --> {s2}\n'

        return ret
