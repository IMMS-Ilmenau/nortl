from typing import List, Sequence, Set, Tuple

from nortl.core.engine import CoreEngine
from nortl.core.protocols import ScratchSignalProto
from nortl.utils.type_aliases import IntSlice


def extract_scratch_signals(width: int, universe: List[ScratchSignalProto]) -> List[ScratchSignalProto]:
    return [s for s in universe if s.width == width]


def get_scratch_signal_group(start_signal: ScratchSignalProto, universe: List[ScratchSignalProto]) -> Tuple[int, List[ScratchSignalProto]]:
    """Creates a List of scratch signals that share the same similarity to the start signal.

    The similarity used for this process is the maximum similarity to all other signals of same width.
    """
    if not isinstance(start_signal.width, int):
        raise RuntimeError('Start signal for scratch reordering has non-int width!? This should not be possible for ScratchSignals.')

    reduced_universe = extract_scratch_signals(start_signal.width, universe)
    maximum_similarity = max([start_signal.call_stack_similarity(s) for s in reduced_universe])

    return maximum_similarity, [s for s in reduced_universe if start_signal.call_stack_similarity(s) == maximum_similarity] + [start_signal]


def overlaps(signal1: ScratchSignalProto, signal2: ScratchSignalProto) -> bool:
    """Are the given two signals active in same states and overlap in scratch map?"""
    # FIXME: Maybe move this method to scratch_manager to provide a consistency check.

    if signal1.states_disjoint(signal2):
        return False

    bits_signal_1: Sequence[int] = []
    bits_signal_2: Sequence[int] = []

    if isinstance(signal1.index, int):
        bits_signal_1 = [signal1.index]
    else:
        # FIXME: Replace by dynamic value later, 1e6 should catch most scenarios for now
        bits_signal_1 = range(*list(signal1.index.indices(int(1e6))))

    if isinstance(signal2.index, int):
        bits_signal_2 = [signal2.index]
    else:
        bits_signal_2 = range(*list(signal2.index.indices(int(1e6))))

    for idx1 in bits_signal_1:
        if idx1 in bits_signal_2:
            return True

    return False


class ScratchReorderingMixin(CoreEngine):
    """The location of scratch register in the scratch map determines the size of multiplexers and the optimization potential by state merging.

    This class provides a heuristic optimization to align scratch registers with similar functions based on their origin in the code
    and their use in the states
    """

    def _try_relocate_scratch_signal(self, scratch_signal: ScratchSignalProto, new_start: int) -> bool:
        """Try to place a scratchsignal at a new location of the scratch pad. Returns True if succeeded and resizes the scratchpad if needed."""
        if not isinstance(scratch_signal.width, int):
            raise RuntimeError('Scratch signal width must always be integer and cannot be a Renderable!')

        if scratch_signal.width != 0:
            new_pos: IntSlice | int = slice(new_start, new_start + scratch_signal.width)
        else:
            new_pos = new_start

        old_pos = scratch_signal.index

        # Relocate
        # The type:ignore is used since the _index should never be set by the user or exposed!
        scratch_signal._index = new_pos  # type:ignore
        # Test if we now overlap with someone

        if any([overlaps(scratch_signal, s) for s in self.scratch_manager.scratch_signals if s is not scratch_signal]):
            scratch_signal._index = old_pos  # type:ignore
            return False

        # Resize scratchpad if needed
        if new_start + scratch_signal.width > self.scratch_manager.scratchpad_width:
            self.scratch_manager.scratchpad_width = new_start + scratch_signal.width

        return True

    def _place_group(self, group: List[ScratchSignalProto], start_offset: int) -> None:
        # Assume all signals in the group have same width.
        if any([not isinstance(s.width, int) for s in group]):
            raise RuntimeError('Scratch signal width must always be integer and cannot be a Renderable!')

        width: int = group[0].width  # type:ignore

        if any([s.width != width for s in group]):
            raise RuntimeError('Signals in group must all have the same width!')

        for signal in group:
            k = 0
            while not self._try_relocate_scratch_signal(signal, start_offset + k * width):
                k = k + 1

    def scratch_reordering(self) -> None:
        universe = [s for s in self.scratch_manager.scratch_signals]

        start_offset = self.scratch_manager.scratchpad_width

        while universe != []:
            scratch_widths: Set[int] = set([s.width for s in universe])  # type:ignore

            signals_of_current_max_width = [s for s in universe if s.width == max(scratch_widths)]
            similarity_groups = [get_scratch_signal_group(s, signals_of_current_max_width) for s in signals_of_current_max_width]
            similarity_groups = sorted(similarity_groups, key=lambda x: x[0], reverse=True)

            _, group_to_place = similarity_groups[0]

            self._place_group(group_to_place, start_offset)

            new_universe = []
            for s in universe:
                found = False
                for k in group_to_place:
                    if s is k:
                        found = True

                if not found:
                    new_universe.append(s)

            universe = new_universe

        # Now shift all signals to the beginning of the scratch pad
        for s in self.scratch_manager.scratch_signals:
            if isinstance(s.index, int):
                pos = s.index
            else:
                pos = min(range(*s.index.indices(int(1e6))))

            self._try_relocate_scratch_signal(s, pos - start_offset)
