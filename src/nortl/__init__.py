"""noRTL Code Generation Engine.

This module provides the main Engine class and mixins for creating noRTL-based code generation.
It includes components for communication, constructs for flow control, and algorithms for analysis.
"""

from contextlib import contextmanager
from typing import Iterator, Union

from nortl import verilog_library
from nortl.algorithms import EmptyStateRemovalMixin, ReachabilityAnalysisMixin, ScratchReorderingMixin, StateMergerMixin
from nortl.components import Channel, ElasticChannel, Timer
from nortl.core import All, Any, Concat, Const, CoreEngine, IfThenElse, Var, Volatile, enable_tracing, to_renderable
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
    'enable_tracing',
    'to_renderable',
]


class ComponentsMixin(CoreEngine):
    """Mixin class providing noRTL Components.

    This allows easier access to the components, without needing to import them.
    """

    def create_channel(self, width: int, name: str = 'channel') -> Channel:
        """Create a channel.

        Example:
        ```python
        engine = Engine("my_engine")
        channel = engine.create_channel(8, "data_channel")
        ```

        Arguments:
            width: Bit width of the channel.
            name: Name of the channel instance.
        """
        return Channel(self, width, name=name)

    def create_elastic_channel(self, width: int, name: str = 'channel') -> ElasticChannel:
        """Create an elastic channel.

        Example:
        ```python
        engine = Engine("my_engine")
        channel = engine.create_elastic_channel(8, "data_channel")
        ```

        Arguments:
            width: Bit width of the channel.
            name: Name of the channel instance.
        """
        return ElasticChannel(self, width, name=name)

    def create_timer(self, width: Union[int, ParameterProto] = 16, instance_name_prefix: str = 'I_TIMER', clock_gating: bool = False) -> Timer:
        """Create a timer.

        Example:
        ```python
        engine = Engine("my_engine")
        timer = engine.create_timer(32, "I_TIMER", clock_gating=True)
        ```

        Arguments:
            width: Bit width of the timer counter (default: 16).
            instance_name_prefix: Prefix for the instance name (default: 'I_TIMER').
            clock_gating: Enable clock gating for the timer (default: False).
        """
        return Timer(self, width=width, instance_name_prefix=instance_name_prefix, clock_gating=clock_gating)


class ConstructsMixin(CoreEngine):
    """Mixin class providing noRTL Constructs.

    This allows easier access to the flow control constructs, without needing to import them.
    """

    def condition(self, condition: Renderable) -> Condition:
        """Adds a Condition.

        Example:
        ```python
        engine = Engine("my_engine")
        in_signal = engine.define_input("IN")

        with engine.condition(in_signal == 1):
            engine.sync()
            engine.do_something()
        ```

        Arguments:
            condition: A Renderable signal representing the condition to evaluate.
        """
        return Condition(self, condition)

    def else_condition(self) -> ElseCondition:
        """Adds an Else Condition.

        The else condition is automatically derived from the previous conditions in the state.

        Example:
        ```python
        engine = Engine("my_engine")
        in_signal = engine.define_input("IN")

        with engine.condition(in_signal == 1):
            engine.sync()
            engine.do_something()
        with engine.else_condition():
            engine.do_something_else()
        ```

        """
        return ElseCondition(self)

    def fork(self, threadname: str) -> Fork:
        """Adds a Fork.

        Example:
        ```python
        engine = Engine("my_engine")
        with engine.fork("thread1"):
            engine.do_something()
        ```

        Arguments:
            threadname: Name of the fork thread.
        """
        return Fork(self, threadname)

    def for_loop(
        self, start: Union[Renderable, int], stop: Union[Renderable, int], step: Union[Renderable, int] = Const(1), counter_width: int = 16
    ) -> ForLoop:
        """Adds a For loop.

        Example:
        ```python
        engine = Engine("my_engine")
        out = engine.define_output("test_output", width=8)

        with engine.for_loop(0, 100, 2) as i:
            engine.set(out, i)
        ```

        Arguments:
            start: A signal or int representing the start value of the loop counter.
            stop: A signal or int representing the final value of the loop counter (non-inclusive).
            step: A signal or int representing the step value of the counter (default: 1).
            counter_width: Width of the counter variable (default: 16).
        """
        return ForLoop(self, start, stop, step=step, counter_width=counter_width)

    def while_loop(self, condition: Renderable) -> WhileLoop:
        """Adds a While loop.

        Example:
        ```python
        engine = Engine("my_engine")
        out = engine.define_output("test_output", width=8)

        with engine.while_loop(out < 4) as _:
            engine.set(out, out + 1)
        ```

        Arguments:
            condition: A signal or expression representing the condition of the while loop.
        """
        return WhileLoop(self, condition)


class ManagementMixin(CoreEngine):
    """Mixin Class that provides context managers with convenience functions."""

    @contextmanager
    def context(self) -> Iterator[None]:
        """Creates an empty context for scoping scratch variables."""
        self.scratch_manager.enter_context()
        yield
        self.scratch_manager.exit_context()

    @contextmanager
    def collapse_sync(self) -> Iterator[None]:
        """Marks all states as collapsable. This means, that all empty states (engine.sync() without assignments) may be removed by an optimzation."""
        # Use a counter to handle nested contexts
        if 'collapse_sync_depth' not in self.state_metadata_template:
            self.state_metadata_template['collapse_sync_depth'] = 0
        self.state_metadata_template['collapse_sync_depth'] += 1
        if self.state_metadata_template['collapse_sync_depth'] == 1:
            self.state_metadata_template['collapsable'] = True
        yield
        self.state_metadata_template['collapse_sync_depth'] -= 1
        if self.state_metadata_template['collapse_sync_depth'] == 0:
            self.state_metadata_template['collapsable'] = False


class Engine(
    ComponentsMixin,
    ConstructsMixin,
    ManagementMixin,
    ReachabilityAnalysisMixin,
    ScratchReorderingMixin,
    StateMergerMixin,
    EmptyStateRemovalMixin,
    CoreEngine,
):
    """noRTL Engine.

    The Engine class is the main entry point for creating noRTL-based code generation.
    It provides access to components, constructs, and algorithms through mixin classes.

    Example:
    ```python
    from nortl import Engine

    engine = Engine("my_engine")
    in_signal = engine.define_input("IN")
    out_signal = engine.define_output("OUT", width=8)

    with engine.condition(in_signal == 1):
        engine.set(out_signal, 5)
    ```
    """

    def __init__(self, module_name: str, reset_state_name: str = 'IDLE') -> None:
        """Initialize a new noRTL Engine.

        Arguments:
            module_name: Name of the resulting SystemVerilog module.
            reset_state_name: Default name for the reset state (default: 'IDLE').
        """
        super().__init__(module_name, reset_state_name)

        for module in verilog_library.get_modules():
            self.add_module(module)
