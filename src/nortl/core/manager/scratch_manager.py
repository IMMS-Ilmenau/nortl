from collections import deque
from typing import Deque, List, Optional

from more_itertools import run_length

from nortl.core.operations import Var
from nortl.core.protocols import EngineProto, ScratchSignalProto, SignalProto, ThreadProto
from nortl.core.signal import ScratchSignal


class ScratchManager:
    def __init__(self, engine: EngineProto) -> None:
        self.engine = engine

        self._scratchpad_width: Optional[Var] = None
        self._scratchpad: Optional[SignalProto] = None

        self.scratch_signals: Deque[ScratchSignalProto] = deque([])

    @property
    def scratchpad_width(self) -> int:
        """Width of scratch pad signal."""
        if self._scratchpad_width is None:
            self._create_scratch_pad()
        return self._scratchpad_width.value  # type: ignore[union-attr]

    @scratchpad_width.setter
    def scratchpad_width(self, value: int) -> None:
        """Width of scratch pad signal."""
        if self._scratchpad_width is None:
            self._create_scratch_pad()
        if value < self.scratchpad_width:
            raise ValueError('Scratch pad width must not be decreased.')
        self._scratchpad_width.update(value)  # type: ignore[union-attr]

    @property
    def scratchpad(self) -> SignalProto:
        """Scratch pad."""
        if self._scratchpad is None:
            self._create_scratch_pad()
        return self._scratchpad  # type: ignore[return-value]

    def _create_scratch_pad(self) -> None:
        """Create scratchpad signal."""
        self._scratchpad_width = Var(0)
        self._scratchpad = self.engine.define_local('SCRATCH_SIGNAL', width=self._scratchpad_width, reset_value=0)

    def create(self, width: int) -> ScratchSignal:
        position = self.alloc(width)

        if position is None:
            raise ValueError('Scratch map full!')

        new_scratch_signal = self.scratchpad[position + width - 1 : position].as_scratch_signal()
        self.scratch_signals.append(new_scratch_signal)
        return new_scratch_signal  # type: ignore[return-value]

    @property
    def scratch_map(self) -> List[bool]:
        """Returns a list that shows the state of the currently allocated scratchpad.

        The returned List comprises each bit on the scratchpad as a bool. True-values show, that the bit is currently in use.
        This function is the base for the allocation algorithm that needs to find an appropriate slice of the scratchpad that
        can be used for the next scratch register.

        This function could be realized in a more incremental way in a future version.
        """

        smap = self.scratchpad_width * [False]

        for elem in self.scratch_signals:
            if not elem.released:
                if isinstance(elem.index, slice):
                    bits = list(elem.index.indices(self.scratchpad_width))

                    if bits[1] < bits[0]:
                        bits[0], bits[1] = bits[1], bits[0]

                    # Include last bit in range
                    bits[1] += 1

                    for idx in range(*bits):
                        smap[idx] = True
                else:
                    smap[elem.index] = True

        return smap

    def alloc(self, width: int) -> Optional[int]:
        """Looks for a portion of the scratchpad, where N bits can be used.

        The function returns the first bit's position.
        """

        mmap_encoded = run_length.encode(self.scratch_map)

        position = 0
        for used, length in mmap_encoded:
            if not used and length >= width:
                return position
            position = position + length

        # We did not find a position until now, so we extend the scratch pad by enough bits to fit the new signal in.
        self.scratchpad_width += width

        return self.alloc(width)

    def enter_context(self) -> None:
        """Triggers the enter_context function of all managed scratch signals."""
        for scratch_signal in self.scratch_signals:
            scratch_signal.enter_context()

    def exit_context(self) -> None:
        """Triggers the exit_context function of all managed scratch signals."""
        for scratch_signal in self.scratch_signals:
            scratch_signal.exit_context()

    def force_release_signals_by_thread(self, thread: ThreadProto) -> None:
        """Releases all signals of the current thread. This is triggered by the Thread class after the thread has safely ended."""
        for scratch_signal in self.scratch_signals:
            if scratch_signal.owner == thread:
                scratch_signal.release(force=True)

        self.free_accesses_from_thread(thread)

    def free_accesses_from_thread(self, thread: ThreadProto) -> None:
        for scratch_signal in self.scratch_signals:
            scratch_signal.free_access_from_thread(thread)
