from typing import Dict, List, Tuple

from nortl.core.protocols import EngineProto, Renderable, StateProto


class MermaidRenderer:
    """This class contains the methods to render a nortl to a mermaid state diagram.

    Note that only states and transitions are shown. For transitions, the conditions are omitted.
    It's purpose is to support illustration only!
    """

    # FIXME: Include Fork/Joins

    def __init__(self, engine: EngineProto):
        self.engine = engine

        self.transitions: List[Tuple[str, str, str]] = []
        self.assignment: Dict[str, List[Tuple[str, str, str]]] = {}
        self.indent_level = 0

    def _add_transition(self, s1: StateProto, s2: StateProto, condition: Renderable) -> None:
        self.transitions.append((s1.name, s2.name, condition.render()))

    def render(self) -> str:
        for states in self.engine.states.values():
            for state in states:
                for condition, next_state in state.transitions:
                    self._add_transition(state, next_state, condition)

                item = []
                for r, v, c in state.assignments:
                    item.append((r.render(), v.render(), c.render()))
                self.assignment[state.name] = item

        # Generate the mermaid code
        ret = '---\n'
        ret += f'title {self.engine.module_name}\n'
        ret += '---\n'
        ret += 'stateDiagram-v2\n'
        for s1, s2, cond in self.transitions:
            ret += f'    {s1} --> {s2}: {cond.replace(":", "_")}\n'

        for s1, assignmentlist in self.assignment.items():
            if len(assignmentlist) != 0:
                ret += f'    note right of {s1}\n'
                for reg, val, cond in assignmentlist:
                    ret += f'        if {cond.replace(":", "_")}, set {reg.replace(":", "_")} to {val.replace(":", "_")}\n'

                ret += '    end note\n'

        return ret
