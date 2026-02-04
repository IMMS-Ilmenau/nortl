from types import TracebackType

from nortl.core import Const
from nortl.core.protocols import EngineProto, Renderable
from nortl.core.state import State

__all__ = [
    'Condition',
    'ElseCondition',
]


class Condition:
    """Context manager to realize an if-then-else behavior within a noRTL engine."""

    final_state_key: str = 'Condition.start_state'

    def __init__(self, engine: EngineProto, condition: Renderable):
        """Initializes the Condition context manager.

        The state management is as follows:

        *  If we are realizing the first conditional in a state, we need to create a final-state where the engine should be after executing the conditional code.
            * This final-state is stored in the metadata of the current state (and will be reused if another conditional is added)
            * The final-state also has the start state in its meta-data -- if another condition is to be added,
              it should start from the same initial state as the first conditional.
            * After the conditional has been executed, the engine is placed in the final state
        * If we get to realize the second conditional, we recognize that from the metadata of the current state
            * The start and final state are adapted to resemble the behavior of the first conditional

        The Context manager can be used as follows:
        ```python
        from nortl.core import CoreEngine
        from nortl.utils.context_manager import Condition

        f = CoreEngine('my_engine')
        in_signal = f.define_input('IN')

        # Example usage:
        # <= We start at a start_state
        with Condition(f, in_signal == 1):
            f.sync()
            f.do_something()
            # At the end, the engine goes to an inferred final_state

        with Condition(f, in_signal == 0):
            #The context manager again starts from the same start_state as before
            f.sync()
            f.do_something_else()
            # At the end, the engine goes to an inferred final_state

        # We proceed execution from the final_state

        # When no further conditions are expected, an f.sync() creates a new state and breaks the chain-of-conditionals.

        ```

        Arguments:
            engine: The CoreEngine instance.
            condition: A Renderable signal representing the condition to evaluate.
        """
        self.engine = engine
        self.condition = condition

        if self.engine.current_state.has_metadata(self.final_state_key):
            self.start_state = self.engine.current_state.get_metadata(self.final_state_key)
            self.final_state = self.engine.current_state
            self.engine.current_state = self.start_state
        else:
            self.start_state = self.engine.current_state
            self.final_state = engine.create_state()
            self.final_state.set_metadata(self.final_state_key, self.start_state)

    def __enter__(self) -> None:
        """Executes the provided function if the condition is met."""
        conditional_state = self.engine.create_state()
        self.engine.jump_if(self.condition, conditional_state)
        self.engine.current_state = conditional_state

        # TODO consider moving this into the engine itself
        self.engine.scratch_manager.enter_context()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        jumpconds = [t[0] for t in self.engine.current_state.transitions]
        if Const(1) not in jumpconds:
            self.engine.jump_if(Const(1), self.final_state)
        self.engine.current_state = self.final_state

        self.engine.scratch_manager.exit_context()


def get_else_condition(state: State) -> Renderable:
    conditions = [c for c, _ in state.transitions]
    ret: Renderable = Const(1)

    for c in conditions:
        ret = ret & ~c

    return ret


class ElseCondition(Condition):
    """Context manager to realize an else behavior within a noRTL engine.

    Usage example:

        from nortl.core import CoreEngine
        from nortl.utils.context_manager import Condition, ElseCondition

        f = CoreEngine('my_engine')
        in_signal = f.define_input('IN')

        with Condition(f, in_signal == 1):
            f.sync()
            f.do_something()
        with Condition(f, possible_second_condition):
            f.sync()
            f.do_something()

        with ElseCondition(f):
            f.do_something_else()


    """

    def __init__(self, engine: EngineProto):
        state = engine.current_state.get_metadata(self.final_state_key)
        condition = get_else_condition(state)
        super().__init__(engine, condition)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc_val, exc_tb)
        self.engine.sync()
