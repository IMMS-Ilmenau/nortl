import itertools as it
from typing import List, Set, Tuple

from nortl.core.engine import CoreEngine
from nortl.core.operations import BaseOperation
from nortl.core.protocols import ScratchSignalProto
from nortl.utils.type_aliases import IntSlice


def extract_scratch_signals(width: int, universe: List[ScratchSignalProto]) -> List[ScratchSignalProto]:
    """Extract scratch signals with a specific width from the universe.

    This function filters the universe of scratch signals to return only those
    that have the specified width.

    Args:
        width: The width to filter by
        universe: List of all scratch signals to filter from

    Returns:
        List of scratch signals with the specified width
    """
    return [s for s in universe if s.width == width]


def get_scratch_signal_group(start_signal: ScratchSignalProto, universe: List[ScratchSignalProto]) -> Tuple[int, List[ScratchSignalProto]]:
    """Creates a group of scratch signals that share the same similarity to the start signal.

    The similarity used for this process is the maximum similarity to all other signals of same width.
    This function groups signals that are most similar to the start signal based on their
    call stack similarity metric.

    Args:
        start_signal: The reference signal to measure similarity against
        universe: List of all scratch signals to consider

    Returns:
        A tuple containing:
        - The maximum similarity score
        - A list of signals with that maximum similarity (including the start signal)
    """
    if not isinstance(start_signal.width, int):
        raise RuntimeError('Start signal for scratch reordering has non-int width!? This should not be possible for ScratchSignals.')

    reduced_universe = extract_scratch_signals(start_signal.width, universe)
    maximum_similarity = max([start_signal.call_stack_similarity(s) for s in reduced_universe])

    return maximum_similarity, [s for s in reduced_universe if start_signal.call_stack_similarity(s) == maximum_similarity] + [start_signal]


def index_overlap(signal1: ScratchSignalProto, signal2: ScratchSignalProto) -> bool:
    """Check if two signals have overlapping indices.

    This function determines if the index of one signal overlaps with the index of another signal.
    It handles both integer indices and slice indices.

    Args:
        signal1: First signal to check
        signal2: Second signal to check

    Returns:
        True if the indices overlap, False otherwise
    """
    if isinstance(signal1.index, int) and isinstance(signal2.index, int):
        return signal1.index == signal2.index
    elif isinstance(signal1.index, int) and not isinstance(signal2.index, int):
        return signal1.index <= signal2.index.start and signal1.index >= signal2.index.stop  # type:ignore
    elif isinstance(signal2.index, int) and not isinstance(signal1.index, int):
        return signal2.index <= signal1.index.start and signal2.index >= signal1.index.stop  # type:ignore
    else:
        ret = signal1.index.start <= signal2.index.start and signal1.index.start >= signal2.index.stop  # type:ignore
        ret = ret or (signal1.index.stop <= signal2.index.start and signal1.index.stop >= signal2.index.stop)  # type:ignore
        return ret


def overlaps(signal1: ScratchSignalProto, signal2: ScratchSignalProto) -> bool:
    """Check if two signals are active in the same states and overlap in scratch map.

    This function determines if two signals are both active in the same states and have overlapping
    positions in the scratch map. This is used to detect conflicts when relocating scratch signals.

    Args:
        signal1: First signal to check
        signal2: Second signal to check

    Returns:
        True if signals overlap in both state and scratch map, False otherwise
    """
    # FIXME: Maybe move this method to scratch_manager to provide a consistency check.

    if index_overlap(signal1, signal2):
        return not signal1.states_disjoint(signal2)

    return False


def group_by_disjoint(input_list: List[ScratchSignalProto]) -> List[List[ScratchSignalProto]]:
    """Group signals by disjoint state sets.

    This function recursively groups signals into disjoint groups where no two signals in a group
    share any active states. Signals that overlap in states are placed in different groups.

    Args:
        input_list: List of signals to group

    Returns:
        List of groups, where each group contains signals that are mutually disjoint in state
    """
    if len(input_list) == 0:
        return []

    first_element = input_list.pop()
    ret = [first_element]

    leftovers = []
    for element in input_list:
        if all([e1.states_disjoint(e2) for e1, e2 in it.product([element, *ret], repeat=2) if e1 is not e2]):
            ret.append(element)
        else:
            leftovers.append(element)

    if leftovers == []:
        return [ret]
    else:
        return [ret, *group_by_disjoint(leftovers)]


class ScratchReorderingMixin(CoreEngine):
    """Scratch register reordering for optimization.

    This class provides a heuristic optimization to align scratch registers with similar functions
    based on their origin in the code and their use in the states. By grouping signals with similar
    call stack similarities and placing them contiguously in the scratch map, the optimization
    reduces the size of multiplexers and improves state merging potential.

    The algorithm works by:
    1. Identifying signals with the same width
    2. Grouping signals by similarity to each other
    3. Placing similar signals contiguously in the scratch map
    4. Shifting all signals to the beginning of the scratch pad

    This optimization is particularly beneficial for reducing hardware complexity and improving
    performance in state machines with many scratch registers.
    """

    def _relocate_scratch_signal(self, scratch_signal: ScratchSignalProto, new_start: int, dry_run: bool = False) -> bool:
        """Try to place a scratch signal at a new location of the scratch pad.

        This function attempts to relocate a scratch signal to a new position in the scratch map.
        It checks for overlaps with other signals and resizes the scratchpad if necessary.

        Args:
            scratch_signal: The signal to relocate
            new_start: The starting position for the new location
            dry_run: If True, only test the relocation without making changes

        Returns:
            True if relocation succeeded, False otherwise
        """
        if not isinstance(scratch_signal.width, int):
            raise RuntimeError('Scratch signal width must always be integer and cannot be a Renderable!')

        if scratch_signal.width > 1:
            new_pos: IntSlice | int = slice(new_start + scratch_signal.width - 1, new_start)
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
        """Relocate a group of signals to a new location.

        This function attempts to relocate all signals in a group to a new position, ensuring
        they don't overlap with each other or other signals.

        Args:
            signallist: List of signals to relocate
            new_start: The starting position for the new location
            dry_run: If True, only test the relocation without making changes

        Returns:
            True if all signals were successfully relocated, False otherwise
        """
        return all([self._relocate_scratch_signal(s, new_start, dry_run) for s in signallist])

    def _place_list_of_signals(self, signallist: List[ScratchSignalProto], start_offset: int) -> None:
        """Place a list of signals in the scratch map.

        This function places a list of signals in the scratch map, handling potential overlaps
        by grouping signals that don't overlap and placing them sequentially.

        Args:
            signallist: List of signals to place
            start_offset: The starting offset for placement
        """
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
        """Execute the scratch register reordering optimization.

        This function performs the complete scratch reordering algorithm:
        1. Enable caching of active state data in scratch signals
        2. Group signals by similarity and place them contiguously
        3. Shift all signals to the beginning of the scratch pad
        4. Update the scratchpad width accordingly

        The optimization aims to minimize multiplexer sizes and improve state merging
        by placing similar signals close together in the scratch map.
        """
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

        # Now shift all signals to the beginning of the scratch pad
        new_scratchpad_width = 0

        for s in self.scratch_manager.scratch_signals:
            if isinstance(s.index, int):
                pos = s.index
                new_scratchpad_width = max(s.index, new_scratchpad_width)
            else:
                pos = min(s.index.start, s.index.stop)  # type:ignore
                new_scratchpad_width = max(s.index.stop, new_scratchpad_width)  # type:ignore

            self._relocate_scratch_signal(s, pos - start_offset)

        self.scratch_manager._scratchpad_width.update(new_scratchpad_width)  # type:ignore

        # Disable render cache since it may hold invalid values
        BaseOperation.cache_enabled = False
