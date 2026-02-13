from typing import List, Set, Tuple

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


def index_overlap(signal1: ScratchSignalProto, signal2: ScratchSignalProto) -> bool:
    if isinstance(signal1.index, int) and isinstance(signal2.index, int):
        return signal1.index == signal2.index
    elif isinstance(signal1.index, int) and not isinstance(signal2.index, int):
        return signal1.index >= signal2.index.start and signal1.index <= signal2.index.stop  # type:ignore
    elif isinstance(signal2.index, int) and not isinstance(signal1.index, int):
        return signal2.index >= signal1.index.start and signal2.index <= signal1.index.stop  # type:ignore
    else:
        ret = signal1.index.start >= signal2.index.start and signal1.index.start <= signal2.index.stop  # type:ignore
        ret = ret or (signal1.index.stop >= signal2.index.start and signal1.index.stop <= signal2.index.stop)  # type:ignore
        return ret


def overlaps(signal1: ScratchSignalProto, signal2: ScratchSignalProto) -> bool:
    """Are the given two signals active in same states and overlap in scratch map?"""
    # FIXME: Maybe move this method to scratch_manager to provide a consistency check.

    if index_overlap(signal1, signal2):
        return not signal1.states_disjoint(signal2)

    return False


def group_by_disjoint(input_list: List[ScratchSignalProto]) -> List[List[ScratchSignalProto]]:
    if len(input_list) == 0:
        return []

    first_element = input_list.pop()
    ret = [first_element]

    leftovers = []
    for element in input_list:
        if first_element.states_disjoint(element):
            ret.append(element)
        else:
            leftovers.append(element)

    if leftovers == []:
        return [ret]
    else:
        return [ret, *group_by_disjoint(leftovers)]


class ScratchReorderingMixin(CoreEngine):
    """The location of scratch register in the scratch map determines the size of multiplexers and the optimization potential by state merging.

    This class provides a heuristic optimization to align scratch registers with similar functions based on their origin in the code
    and their use in the states
    """

    def _relocate_scratch_signal(self, scratch_signal: ScratchSignalProto, new_start: int, dry_run: bool = False) -> bool:
        """Try to place a scratchsignal at a new location of the scratch pad. Returns True if succeeded and resizes the scratchpad if needed."""
        if not isinstance(scratch_signal.width, int):
            raise RuntimeError('Scratch signal width must always be integer and cannot be a Renderable!')

        if scratch_signal.width > 1:
            new_pos: IntSlice | int = slice(new_start, new_start + scratch_signal.width)
        else:
            new_pos = new_start

        old_pos = scratch_signal.index

        # Relocate
        # The type:ignore is used since the _index should never be set by the user or exposed!

        scratch_signal._index = new_pos  # type:ignore

        # Test if we now overlap with someone
        if any(overlaps(scratch_signal, s) for s in self.scratch_manager.scratch_signals if s is not scratch_signal):
            scratch_signal._index = old_pos  # type:ignore
            return False

        if dry_run:
            scratch_signal._index = old_pos  # type:ignore
            return True

        # Resize scratchpad if needed
        if new_start + scratch_signal.width > self.scratch_manager.scratchpad_width:
            self.scratch_manager.scratchpad_width = new_start + scratch_signal.width

        return True

    def _relocate_group(self, signallist: List[ScratchSignalProto], new_start: int, dry_run: bool) -> bool:
        return all([self._relocate_scratch_signal(s, new_start, dry_run) for s in signallist])

    def _place_list_of_signals(self, signallist: List[ScratchSignalProto], start_offset: int) -> None:
        # Assume all signals in the group have same width.
        if any([not isinstance(s.width, int) for s in signallist]):
            raise RuntimeError('Scratch signal width must always be integer and cannot be a Renderable!')

        width: int = signallist[0].width  # type:ignore

        if any([s.width != width for s in signallist]):
            raise RuntimeError('Signals in group must all have the same width!')

        # group singals by overlaps

        grouping = group_by_disjoint(signallist)
        for group in grouping:
            k = 0
            while not self._relocate_group(group, start_offset + k, dry_run=True):
                k = k + 1

            self._relocate_group(group, start_offset + k, dry_run=False)

    def scratch_reordering(self) -> None:
        universe = [s for s in self.scratch_manager.scratch_signals]

        # enable caching of active state data  in the scratch signals
        for s in universe:
            s.set_metadata('cache_active_state_enabled', True)  # type:ignore

        start_offset = self.scratch_manager.scratchpad_width + 1

        while universe != []:
            scratch_widths: Set[int] = set([s.width for s in universe])  # type:ignore

            signals_of_current_max_width = [s for s in universe if s.width == max(scratch_widths)]
            similarity_groups = [get_scratch_signal_group(s, signals_of_current_max_width) for s in signals_of_current_max_width]
            similarity_groups = sorted(similarity_groups, key=lambda x: x[0], reverse=True)

            _, group_to_place = similarity_groups[0]

            self._place_list_of_signals(group_to_place, start_offset)

            new_universe = []
            for s in universe:
                found = False
                for k in group_to_place:
                    if s is k:
                        found = True

                if not found:
                    new_universe.append(s)

            universe = new_universe

            print(f'universe size {len(universe)}, current width = {max(scratch_widths)}')

        # Now shift all signals to the beginning of the scratch pad
        for s in self.scratch_manager.scratch_signals:
            if isinstance(s.index, int):
                pos = s.index
            else:
                pos = min(s.index.start, s.index.stop)  # type:ignore

            self._relocate_scratch_signal(s, pos - start_offset)
