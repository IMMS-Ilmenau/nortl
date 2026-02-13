from types import TracebackType

from nortl.core import Const
from nortl.core.operations import to_renderable
from nortl.core.protocols import EngineProto, Renderable, StateProto

__all__ = [
    'ForLoop',
    'WhileLoop',
]


class ForLoop:
    """Context manager to realize a for-loop within a noRTL engine."""

    def __init__(
        self, engine: EngineProto, start: Renderable | int, stop: Renderable | int, step: Renderable | int = 1, counter_width: int = 16
    ) -> None:
        """Initializes the ForLoop context manager.

        Its intention is to emulate the behavior of a for loop in a engine.

        Example:
        ```python
        engine = Engine("my_engine")
        out = engine.define_output("test_output", width=8)

        with engine.for_loop(0, 100, 2) as i: # This returns the ForLoop(engine,...) context manager
            # code that should be run multiple times
            engine.set(out, i)
        ```

        The context manager cares about the realization of the counter variable and returns it to be used in the loop.
        This means, multiple (non-colliding) loops may use the same count registers.

        As in other programming languages: Only modify the counter variable within the loop if you really know, what you do.
        Generally, it is a very bad idea to write to the loop variable.

        Arguments:
            engine: The CoreEngine instance.
            start: A signal or int representing the start value of the loop counter
            stop: A signal or int representing the final value of the loop counter. The value is non-inclusive.
            step: A signal or int representing the step value of the counter (default: 1)
            counter_width: Width of the counter variable (default: 16). The counter width must fit the stop value.
        """
        self.engine = engine
        self.start = to_renderable(start)
        self.stop = to_renderable(stop)
        self.step = to_renderable(step)

        self.start_state = engine.current_state
        self.final_state = engine.create_state()

        # TODO Validate start and stop values against counter_width, if possible
        # FIXME width must be 1 bit wider than the actual counter!
        self.counter = self.engine.define_scratch(counter_width)
        self.counter_nxt = self.counter + self.step

    def __enter__(self) -> Renderable:
        """Executes the provided function if the condition is met."""
        self.engine.set(self.counter, self.start)
        self.engine.sync()
        self.start_state = self.engine.current_state

        other_state = self.engine.create_state()

        self.engine.jump_if(self.counter == self.stop, self.final_state, other_state)

        self.engine.current_state = other_state

        # TODO consider moving this into the engine itself
        self.engine.scratch_manager.enter_context()

        return self.counter

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.engine.sync()
        self.engine.set(self.counter, self.counter_nxt)
        self.engine.jump_if(Const(1), self.start_state)

        # Goto final state
        self.engine.current_state = self.final_state

        self.engine.scratch_manager.exit_context()
        self.counter.release()

        self.engine.sync()


class WhileLoop:
    """Context manager to realize a while-loop within a noRTL engine.

    Its intention is to emulate the behavior of a while loop in an engine.

    Example:
    ```python
    engine = Engine("my_engine")
    out = engine.define_output("test_output", width=8)

    with engine.while_loop(out < 4) as _:  # This returns the WhileLoop(engine,...) context manager
        # code that should be run while the condition is true
        engine.set(out, out + 1)
    ```

    The context manager handles the state transitions for the loop.
    Make sure to modify the condition variables within the loop body to eventually make the condition false,
    otherwise the loop will run indefinitely.

    Arguments:
        engine: The CoreEngine instance.
        condition: A signal or expression representing the condition of the while loop.
    """

    def __init__(self, engine: EngineProto, condition: Renderable) -> None:
        """Initializes a While construct."""
        self.engine = engine
        self.condition = to_renderable(condition)

        self.start_state: StateProto
        self.final_state: StateProto

    def __enter__(self) -> None:
        self.start_state = self.engine.current_state
        self.final_state = self.engine.create_state()

        # Add conditional jump to start state
        self.engine.jump_if(self.condition, self.engine.next_state, self.final_state)

        # Switch to loop content and yield back
        self.engine.current_state = self.engine.next_state

        # TODO consider moving this into the engine itself
        self.engine.scratch_manager.enter_context()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if len(self.engine.current_state.transitions) > 0:
            raise RuntimeError('Last state in a While loop must not have any outgoing transitions!')

        self.engine.jump_if(Const(1), self.start_state)

        # Goto final state
        self.engine.current_state = self.final_state

        self.engine.scratch_manager.exit_context()
