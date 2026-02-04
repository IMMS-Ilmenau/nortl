from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from nortl.core.protocols import SIGNAL_TYPES, EngineProto, ParameterProto, Renderable, ThreadProto
from nortl.core.signal import Signal


class SignalManager:
    def __init__(self, engine: EngineProto) -> None:
        self.engine = engine
        self._signals: Dict[str, Signal] = {}
        self._combinationals: List[Tuple[Signal, Renderable]] = []

    @property
    def signals(self) -> Mapping[str, Signal]:
        """Signals."""
        return self._signals

    @property
    def combinationals(self) -> Sequence[Tuple[Signal, Renderable]]:
        """Sequence of combinational signal assignments."""
        return self._combinationals

    def get_signal(self, name: str) -> Signal:
        return self.signals[name]

    def create_signal(
        self,
        type: SIGNAL_TYPES,
        name: str,
        width: Union[int, ParameterProto, Renderable] = 1,
        data_type: str = 'logic',
        is_synchronized: bool = False,
        pulsing: bool = False,
        assignment: Optional[Renderable] = None,
    ) -> Signal:
        """Create a signal.

        Arguments:
            type: Type of the signal.
            name: Name of the signal.
            width: Width of the signal in bits.
            data_type: Data type of the signal.
            is_synchronized: Indicates, if the signal is synchronous to the used clock domain
            pulsing: If true, the signal automatically resets to zero if not set in the current state
            assignment: Source expression for combinational assignment.

        Returns:
            The created signal.

        Raises:
            KeyError: If the signal name already exists.
        """

        if name in self.signals:
            raise KeyError(f'Signal name {name} already exists.')
        if name in self.engine.parameters:
            raise KeyError(f'Signal name {name} collides with existing parameter name.')
        signal = Signal(
            self.engine, type, name, width=width, data_type=data_type, is_synchronized=is_synchronized, pulsing=pulsing, assignment=assignment
        )
        self._signals[name] = signal

        # TODO width of assignment source is not respected, would be better to automatically pick it up?
        # Maybe replace default of width with None?
        if assignment is not None:
            self._combinationals.append((signal, assignment))
        return signal

    def free_accesses_from_thread(self, thread: ThreadProto) -> None:
        for signal in self.signals.values():
            signal.free_access_from_thread(thread)
