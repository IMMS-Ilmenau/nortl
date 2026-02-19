from typing import Dict, Iterator, List, Tuple

from nortl.core.protocols import EngineProto


class MermaidRenderer:
    """This class contains the methods to render a nortl to a mermaid state diagram.

    Note that only states and transitions are shown. For transitions, the conditions are omitted.
    It's purpose is to support illustration only!
    """

    # FIXME: Include Fork/Joins

    def __init__(self, engine: EngineProto):
        self.engine = engine
        self.indent_level = 0

    def render(self) -> str:
        ret = '---\n'
        ret += f'title {self.engine.module_name}\n'
        ret += '---\n'
        ret += 'stateDiagram-v2\n'

        for _, worker_graph in self._render_workers():
            ret += worker_graph
        return ret

    def render_workers(self) -> Iterator[Tuple[str, str]]:
        for worker, worker_graph in self._render_workers():
            ret = '---\n'
            ret += f'title {self.engine.module_name} {worker}\n'
            ret += '---\n'
            ret += 'stateDiagram-v2\n'
            ret += worker_graph
            yield worker, ret

    def _render_workers(self) -> Iterator[Tuple[str, str]]:
        for worker, worker_states in self.engine.states.items():
            transitions: List[Tuple[str, str, str]] = []
            assignment: Dict[str, List[Tuple[str, str, str]]] = {}

            for state in worker_states:
                for condition, next_state in state.transitions:
                    transitions.append((state.name, next_state.name, condition.render()))

                item = []
                for r, v, c in state.assignments:
                    item.append((r.render(), v.render(), c.render()))
                assignment[state.name] = item

            # Generate the mermaid code
            ret = ''
            for s1, s2, cond in transitions:
                ret += f'    {s1} --> {s2}: {cond.replace(":", "_")}\n'

            for s1, assignmentlist in assignment.items():
                if len(assignmentlist) != 0:
                    ret += f'    note right of {s1}\n'
                    for reg, val, cond in assignmentlist:
                        ret += f'        if {cond.replace(":", "_")}, set {reg.replace(":", "_")} to {val.replace(":", "_")}\n'

                    ret += '    end note\n'

            yield worker, ret
