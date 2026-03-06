from contextlib import contextmanager
from types import TracebackType
from typing import Iterator, List, Optional, Sequence, Type

from more_itertools import run_length

from nortl.core.operations import Var
from nortl.core.protocols import EngineProto, MemoryViewProto, PermanentSignal, ScratchSignalProto, SignalProto, ThreadProto
from nortl.core.signal import ScratchSignal, list_indexes


class ScratchManager:
    def __init__(self, engine: EngineProto) -> None:
        self._engine = engine

        # Scratch manager starts out with a main zone
        self._zones: List['MemoryZone'] = []
        self._active_zones: List['MemoryZone'] = []
        self._main_zone = self.create_zone('main')

    @property
    def engine(self) -> EngineProto:
        """NoRTL engine."""
        return self._engine

    # Scratch signal management
    def create_signal(self, width: int) -> ScratchSignal:
        """Create new scratch signal inside the active memory zone."""

        if width <= 0:
            raise RuntimeError('Tried to create a scratch signal with width<=0. Something is wrong in the code outside of this unit!')

        return self.active_zone.create_signal(width)

    # Context management
    def enter_context(self) -> None:
        """Triggers the enter_context function of all managed scratch signals."""
        for scratch_signal in self.active_zone.scratch_signals:
            scratch_signal.enter_context()

    def exit_context(self) -> None:
        """Triggers the exit_context function of all managed scratch signals."""
        for scratch_signal in self.active_zone.scratch_signals:
            scratch_signal.exit_context()

    def force_release_signals_by_thread(self, thread: ThreadProto) -> None:
        """Releases all signals of the current thread. This is triggered by the Thread class after the thread has safely ended."""
        for scratch_signal in self.active_zone.scratch_signals:
            if scratch_signal.owner == thread:
                scratch_signal.release(force=True)

        self.free_accesses_from_thread(thread)

    def free_accesses_from_thread(self, thread: ThreadProto) -> None:
        """Disables all access checks to scratch signals that have their origin in the given thread."""
        for scratch_signal in self.active_zone.scratch_signals:
            scratch_signal.free_access_from_thread(thread)

    # Memory zone managment
    @property
    def zones(self) -> Sequence['MemoryZone']:
        """Memory zones."""
        return self._zones

    @property
    def main_zone(self) -> 'MemoryZone':
        """Main memory zone."""
        return self._main_zone

    @property
    def active_zone(self) -> 'MemoryZone':
        """Active memory zone.

        Zones are activated by entering them as a context manager. Only one zone will be active at a time.
        """
        return self._active_zones[-1]

    @property
    def suspended_zones(self) -> Sequence['MemoryZone']:
        """Suspended memory zones.

        While only one zone will be active in the foreground, the previously active zone(s) will be suspended in the background.
        Signals of suspended zones can still be accessed, but new scratch signals will always be allocated in the active zone.
        """
        return self._active_zones[:-1]

    def create_zone(self, name: Optional[str] = None) -> 'MemoryZone':
        """Create new memory zone.

        Each memory zone consists of individual scratch pad, where scratch signals can be allocated and released.

        The signals inside a zone are automatically released and can no longer be accessed, once it is left.
        However, the allocated scratch pad stays reserved.

        Zones can be re-entered multiple times and will dynamically grow if needed.
        Each time a zone is entered, a new memory view is created. As the memory views are exclusive to each other, they can have different allocations of the scratch signals.

        Once the noRTL engine is completely assembled, zones could be merged, if their active regions don't overlap.
        """
        zone = MemoryZone(self, main_zone=len(self._zones) == 0, name=name)
        self._zones.append(zone)
        return zone


class MemoryZone:
    """Memory zone."""

    def __init__(self, manager: ScratchManager, main_zone: bool = False, name: Optional[str] = None) -> None:
        self._manager = manager
        self._id = len(manager.zones)

        self._width: Optional[Var] = None
        self._scratchpad: Optional[SignalProto] = None

        self._views: List['MemoryView'] = []
        self._active_view: Optional['MemoryView'] = None
        self._main_zone = main_zone

        self._name = f'Zone {self.id}'
        if name is not None:
            self._name += f' ({name})'

        # Main zone always has a single active view
        if main_zone:
            self._create_view()
            self._active_view = self._views[-1]

    @property
    def manager(self) -> ScratchManager:
        """Scratch manager."""
        return self._manager

    @property
    def name(self) -> str:
        """Name of the memory zone."""
        return self._name

    @property
    def main_zone(self) -> bool:
        """Indicates if this zone is the main zone.

        The main zone is always active (or suspended in the background).
        """
        return self._main_zone

    @property
    def id(self) -> int:
        """Numerical identifier of the memory zone."""
        return self._id

    # Scratch pad
    @property
    def width(self) -> int:
        """Width of scratch pad signal."""
        if self._width is None:
            self._create_scratch_pad()
        return self._width.value  # type: ignore[union-attr]

    @width.setter
    def width(self, value: int) -> None:
        """Width of scratch pad signal."""
        if self._width is None:  # pragma: no cover
            self._create_scratch_pad()
        if value < self.width:
            raise ValueError('Scratch pad width must not be decreased.')
        self._width.update(value)  # type: ignore[union-attr]

    @property
    def scratchpad(self) -> SignalProto:
        """Scratch pad."""
        if self._scratchpad is None:  # pragma: no cover
            return self._create_scratch_pad()
        return self._scratchpad

    def _create_scratch_pad(self) -> PermanentSignal:
        """Create scratch pad signal."""
        self._width = Var(0)
        name = 'SCRATCH_SIGNAL'

        if not self.main_zone:
            name += f'_ZONE{self.id}'

        self._scratchpad = self.manager.engine.define_local(name, width=self._width, reset_value=0)
        return self._scratchpad

    @property
    def scratch_map(self) -> Sequence[bool]:
        """Returns a list that shows the state of the currently allocated scratch pad.

        The returned list comprises each bit on the scratch pad as a bool. True-values show, that the bit is currently in use.
        This function is the base for the allocation algorithm that needs to find an appropriate slice of the scratch pad that
        can be used for the next scratch register.

        This function could be realized in a more incremental way in a future version.
        """

        smap = self.width * [False]

        for signal in self.active_view.scratch_signals:
            if not signal.released:
                for index in list_indexes(signal.index):
                    smap[index] = True

        return smap

    def alloc(self, width: int) -> Optional[int]:
        """Looks for a portion of the scratch pad, where a signal with the specified width can be allocated.

        If necessary, the scratch pad is grown to fit the new signal.
        The function returns the starting position for the signal.
        """

        if not isinstance(width, int):
            raise TypeError(f'Width for scratch signal must an integer, got {width}')

        mmap_encoded = run_length.encode(self.scratch_map)

        position = 0
        for used, length in mmap_encoded:
            if not used and length >= width:
                return position
            position = position + length

        # We did not find a position until now, so we extend the scratch pad by enough bits to fit the new signal in.
        self.width += width

        return self.alloc(width)

    # Scratch signal management
    @property
    def scratch_signals(self) -> Sequence['ScratchSignal']:
        """Scratch signals inside the current memory view."""
        return self.active_view.scratch_signals

    def create_signal(self, width: int) -> ScratchSignal:
        """Create new scratch signal inside the memory zone."""
        return self.active_view.create_signal(width)

    # Activation and view management
    @property
    def active(self) -> bool:
        """Indicates if the zone is currently active."""
        return self.manager.active_zone is self

    @property
    def suspended(self) -> bool:
        """Indicates if the zone is currently suspended in the background."""
        return self in self.manager.suspended_zones

    @property
    def active_view(self) -> 'MemoryView':
        """Active view of the zone, containing the allocated scratch signals."""
        if self._active_view is None:
            raise RuntimeError('Memory zone does not have an active view. This is most likely an internal issue.')
        if self.active or self.suspended:
            return self._active_view
        else:
            raise RuntimeError('Memory zone is neither active nor suspended. Its signals cannot be accessed.')

    @property
    def views(self) -> Sequence['MemoryView']:
        """Sequence of memory views."""
        return self._views

    def _create_view(self) -> 'MemoryView':
        self.manager._active_zones.append(self)
        view = MemoryView(self)
        self._views.append(view)
        return view

    def __enter__(self) -> 'MemoryView':
        if self.main_zone:
            raise RuntimeError('This zone is the main zone, unable enter create a new view.')
        view = self._create_view()
        self._active_view = view
        return view

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        if exc_type is not None:
            return
        if not self.active:
            raise RuntimeError('This zone is not active, unable to deactivate it.')

        if len(self.manager._active_zones) > 1:
            self._release_zone()
            self.manager._active_zones.pop(-1)
        else:
            raise RuntimeError('This zone is the last active one (main zone), unable to deactivate it.')

    @contextmanager
    def recover(self, view: 'MemoryViewProto') -> Iterator[None]:
        """Recover a previous memory view and set it as active.

        This is intended to be used for internal purposes.
        """
        if self.active:
            raise RuntimeError(
                'It is not possible to recover an alternative view while the memory zone is active. This is most likely an internal issue.'
            )

        self.manager._active_zones.append(self)
        self._active_view = view  # type: ignore[assignment]
        yield
        self._release_zone()
        self.manager._active_zones.pop(-1)

    def _release_zone(self) -> None:
        """Release all signals in the zone."""
        for signal in self.active_view.scratch_signals:
            signal.release(force=True)


class MemoryView:
    """Memory view.

    A memory view holds a specific allocation of a memory zone.
    Memory zones can have multiple memory views, that are exclusive to each other.
    """

    def __init__(self, zone: MemoryZone):
        self._zone = zone
        self._scratch_signals: List[ScratchSignal] = []

    @property
    def zone(self) -> MemoryZone:
        """Memory zone."""
        return self._zone

    @property
    def scratch_signals(self) -> Sequence[ScratchSignal]:
        """Sequence of scratch signals allocated in the view."""
        return self._scratch_signals

    def create_signal(self, width: int) -> ScratchSignal:
        """Create new scratch signal inside the memory view."""
        position = self.zone.alloc(width)

        if position is None:
            raise ValueError('Scratch map is full!')

        new_signal = self.zone.scratchpad[position + width - 1 : position].as_scratch_signal(self.zone)
        return new_signal  # type: ignore[return-value]

    def _register_signal(self, signal: ScratchSignalProto) -> None:
        """Register scratch signal.

        This is used for internal purposes only and should never be called manually.

        Scratch signals actively register themselves after creation.
        This ensures, that all scratch signals are tracked correctly.
        """
        self._scratch_signals.append(signal)  # type: ignore[arg-type]
