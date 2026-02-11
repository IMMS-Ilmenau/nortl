from typing import Dict, List, Set

from nortl.core.protocols import EngineProto, ScratchSignalProto


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
        self.scratch_map: Dict[str, List[str]] = {}  # Map state name to list of
        self.set_of_labels: Set[str] = set()
        self.list_of_labels: List[str] = []
        self.map_label_to_htmlcolor: Dict[str, str] = {}

    def _extract_frame_info(self, source: ScratchSignalProto) -> str:
        frame = source.creator_frames[-1]
        ret = f'{frame.filename}, {frame.lineno}: {frame.function}'
        return ret

    def _generate_map(self) -> None:
        length = self.engine.scratch_manager.scratchpad_width
        for statelist in self.engine.states.values():
            for state in statelist:
                new_lst = [''] * length

                for scratch_signal in state.active_scratch_signals:
                    if isinstance(scratch_signal.index, slice):
                        bits = list(scratch_signal.index.indices(length))

                        if bits[1] < bits[0]:
                            bits[0], bits[1] = bits[1], bits[0]

                        # Include last bit in range
                        bits[1] += 1

                        for idx in range(*bits):
                            new_lst[idx] = self._extract_frame_info(scratch_signal)
                    else:
                        new_lst[scratch_signal.index] = self._extract_frame_info(scratch_signal)

                    self.set_of_labels.add(self._extract_frame_info(scratch_signal))

                self.scratch_map[state.name] = new_lst

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
        self.list_of_labels = sorted(list(self.set_of_labels))
        for label, colorstr in zip(self.list_of_labels, self.generate_colors(len(self.list_of_labels))):
            self.map_label_to_htmlcolor[label] = colorstr

    def render(self, show_frameinfo: bool = False) -> str:
        """Will create the html table in a raw string."""
        self._generate_map()
        self._create_metadata()

        retlst = ['<table>']
        for statename in sorted(list(self.scratch_map.keys())):
            retlst.append('<tr>')

            retlst.append(f'<td>{statename}</td>')

            for item in self.scratch_map[statename]:
                frameinfo = ''
                if show_frameinfo:
                    frameinfo = item

                if item != '':
                    retlst.append(f'<td style="background-color: {self.map_label_to_htmlcolor[item]}">{frameinfo}</td>')
                else:
                    retlst.append('<td></td>')

            retlst.append('</tr>')

        retlst += ['</table>']
        return '\n'.join(retlst)
