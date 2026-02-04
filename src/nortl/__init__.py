"""noRTL Code Generation Engine."""

from typing import Union

from nortl import verilog_library
from nortl.components import Channel, ElasticChannel, Timer
from nortl.core import All, Any, Concat, Const, CoreEngine, IfThenElse, Var, Volatile
from nortl.core.constructs import Condition, ElseCondition, Fork, ForLoop, WhileLoop
from nortl.core.protocols import ParameterProto, Renderable

__all__ = [
    'All',
    'Any',
    'Concat',
    'Const',
    'CoreEngine',
    'Engine',
    'IfThenElse',
    'Var',
    'Volatile',
]


class ComponentsMixin(CoreEngine):
    """Mixin class providing noRTL Components.

    This allows easier access to the components, without needing to import them.
    """

    def create_channel(self, width: int, name: str = 'channel') -> Channel:
        """Create a channel."""
        return Channel(self, width, name=name)

    def create_elastic_channel(self, width: int, name: str = 'channel') -> ElasticChannel:
        """Create an elastic channel."""
        return ElasticChannel(self, width, name=name)

    def create_timer(self, width: Union[int, ParameterProto] = 16, instance_name_prefix: str = 'I_TIMER', clock_gating: bool = False) -> Timer:
        """Create a timer."""
        return Timer(self, width=width, instance_name_prefix=instance_name_prefix, clock_gating=clock_gating)


class ConstructsMixin(CoreEngine):
    """Mixin class providing noRTL Constructs.

    This allows easier access to the flow control constructs, without needing to import them.
    """

    def condition(self, condition: Renderable) -> Condition:
        """Adds a Condition."""
        return Condition(self, condition)

    def else_condition(self) -> ElseCondition:
        """Adds a Else Condition."""
        return ElseCondition(self)

    def fork(self, threadname: str) -> Fork:
        """Adds a Fork."""
        return Fork(self, threadname)

    def for_loop(
        self, start: Union[Renderable, int], stop: Union[Renderable, int], step: Union[Renderable, int] = Const(1), counter_width: int = 16
    ) -> ForLoop:
        """Adds a For loop."""
        return ForLoop(self, start, stop, step=step, counter_width=counter_width)

    def while_loop(self, condition: Renderable) -> WhileLoop:
        """Adds a While loop."""
        return WhileLoop(self, condition)


class Engine(ComponentsMixin, ConstructsMixin, CoreEngine):
    """noRTL Engine."""

    def __init__(self, module_name: str, reset_state_name: str = 'IDLE') -> None:
        """Initialize a new noRTL Engine.

        Arguments:
            module_name: Name of the resulting SystemVerilog module.
            reset_state_name: Default name for the reset state.
        """
        super().__init__(module_name, reset_state_name)

        for module in verilog_library.get_modules():
            self.add_module(module)
