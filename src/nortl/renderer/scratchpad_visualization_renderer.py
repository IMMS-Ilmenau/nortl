import re
from typing import Dict, List, Set, Tuple, Union

from nortl.core.protocols import EngineProto, ScratchSignalProto


def sort_by_nat_split(x: str) -> Tuple[Union[int, str], ...]:
    """Sort string with mix of numbers and text, while preserving natural order of the numbers.

    This works by splitting string into elements and trying to convert everything to integers.
    """
    result: List[Union[int, str]] = []
    for element in re.split(r'([0-9]+)', x):
        if len(element) == 0:
            continue

        try:
            element = int(element)
        except ValueError:
            pass

        result.append(element)

    return tuple(result)


class ScratchpadVisualizationRenderer:
    """Visualization for the scratchpad over all states.

    The result can be seen as a table of the form
    | STATE    | Scratchpad Bits |
    | -------- | --------------- |
    | STATE_1  | A, B, C         |

    This will be generated as html that can be rendered inline in markdown.
    """

    def __init__(self, engine: EngineProto, include_modules: bool = True, clock_gating: bool = False):
        self.engine = engine
        self.scratch_map: Dict[str, List[Tuple[str, int, int]]] = {}  # Map state name to list of
        self.set_of_labels: Set[str] = set()
        self.list_of_labels: List[str] = []
        self.map_label_to_htmlcolor: Dict[str, str] = {}

    def _extract_frame_info(self, source: ScratchSignalProto) -> str:
        frame = source.creator_frames[-1]
        ret = f'{frame.filename}, {frame.lineno}: {frame.function}\n'
        return ret

    def _generate_map(self) -> None:
        length = self.engine.scratch_manager.scratchpad_width
        for statelist in self.engine.states.values():
            for state in statelist:
                new_lst = []

                for scratch_signal in state.active_scratch_signals:
                    if isinstance(scratch_signal.index, slice):
                        bits = list(scratch_signal.index.indices(length))

                        if bits[1] < bits[0]:
                            bits[0], bits[1] = bits[1], bits[0]

                        # Include last bit in range
                        bits[1] += 1

                        new_lst.append((self._extract_frame_info(scratch_signal), bits[0], bits[1] - bits[0]))
                    else:
                        new_lst.append((self._extract_frame_info(scratch_signal), scratch_signal.index, 1))

                    self.set_of_labels.add(self._extract_frame_info(scratch_signal))

                self.scratch_map[state.name] = sorted(new_lst, key=lambda x: x[1])

    def generate_colors(self, n: int) -> List[str]:
        """Creats n different colors that should actually look different."""
        colors = []
        for i in range(n):
            hue = i / n
            s_, l_ = 0.65, 0.55

            def hue_to_rgb(p: float, q: float, t: float) -> float:
                if t < 0:
                    t += 1
                if t > 1:
                    t -= 1
                if t < 1 / 6:
                    return p + (q - p) * 6 * t
                if t < 1 / 2:
                    return q
                if t < 2 / 3:
                    return p + (q - p) * (2 / 3 - t) * 6
                return p

            q = l_ * (1 + s_) if l_ < 0.5 else l_ + s_ - l_ * s_
            p = 2 * l_ - q
            r = hue_to_rgb(p, q, hue + 1 / 3)
            g = hue_to_rgb(p, q, hue)
            b = hue_to_rgb(p, q, hue - 1 / 3)

            colors.append(f'#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}')
        return colors

    def _create_metadata(self) -> None:
        self.list_of_labels = list(self.set_of_labels)
        for label, colorstr in zip(self.list_of_labels, self.generate_colors(len(self.list_of_labels))):
            self.map_label_to_htmlcolor[label] = colorstr

    def render(self, show_frameinfo: bool = False) -> str:
        """Will create the html table in a raw string."""
        self._generate_map()
        self._create_metadata()

        retlst = ['<table>']

        retlst.append('<tr>')
        retlst.extend(['<td></td>' for _ in range(self.engine.scratch_manager.scratchpad_width + 1)])
        retlst.append('</tr>')

        for statename in sorted(list(self.scratch_map.keys()), key=lambda x: sort_by_nat_split(x)):
            retlst.append('<tr>')

            retlst.append(f'<td>{statename}</td>')

            next_pos = 0
            for item, pos, length in self.scratch_map[statename]:
                if next_pos != pos:
                    retlst.append(f'<td colspan="{pos - next_pos}"></td>')
                next_pos = pos + length

                frameinfo = ''
                if show_frameinfo:
                    frameinfo = item

                if item != '':
                    retlst.append(f'<td style="background-color: {self.map_label_to_htmlcolor[item]}" colspan="{length}">{frameinfo}</td>')
                else:
                    retlst.append('<td></td>')

            retlst.append('</tr>')

        retlst += ['</table>']
        return '\n'.join(retlst)
