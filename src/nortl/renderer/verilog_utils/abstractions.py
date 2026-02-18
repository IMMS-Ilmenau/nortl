from abc import ABC, abstractmethod
from typing import List, Literal, Optional

from nortl.core.protocols import WorkerProto

from .process import AlwaysFF, VerilogAssignment, VerilogCase, VerilogIf
from .structural import VerilogDeclaration
from .utils import VerilogRenderable


class StateRegisterBase(ABC):
    """Abstract base class for state register implementations.

    This class defines the common interface for state register implementations,
    allowing for different state encoding strategies while maintaining a consistent
    API. Subclasses can override specific methods to implement different behaviors.
    """

    def __init__(self, worker: WorkerProto) -> None:
        """Initialize the state register.

        Args:
            worker: The worker containing the states.
        """
        self.worker = worker
        self.state_var = worker.create_scoped_name('state')
        self.next_state_var = worker.create_scoped_name('state_nxt')
        self._current_case: VerilogCase | None = None
        self.states: List[str] = []

    @abstractmethod
    def declare(self) -> VerilogDeclaration:
        """Declares the state register in the Verilog module.

        This method creates the state and next_state variables and adds all state
        members to the enumeration. Subclasses may override this to customize
        the declaration format.

        Returns:
            A VerilogDeclaration object for the state register.
        """
        pass

    @abstractmethod
    def new_case(self, reg: Literal['next state', 'current state']) -> None:
        """Creates a new case statement for the specified state.

        Args:
            reg: Either 'next state' or 'current state' to determine which variable
                 the case statement will use.
        """
        pass

    @abstractmethod
    def add_case(self, case_value: str, item: VerilogRenderable) -> None:
        """Adds an item to the current case.

        Args:
            case_value: The state name for the case statement.
            item: The Verilog item to add (assignment, if statement, print, etc.).

        Raises:
            ValueError: If no active case exists. Call new_case() first or if case_value has not been introduced via add_state
        """
        pass

    @abstractmethod
    def add_state(self, state_name: str) -> None:
        """Adds a state name to the list of states.

        Args:
            state_name: The name of the state to add.
        """
        pass

    @abstractmethod
    def build_case(self) -> VerilogCase:
        """Builds and returns the VerilogCase object from accumulated items.

        Returns:
            A VerilogCase object containing all items added via add_case().

        Raises:
            ValueError: If no active case exists. Call new_case() first.
        """
        pass

    @abstractmethod
    def build_state_transition(self) -> AlwaysFF:
        """Builds the state transition logic.

        This method generates the logic for transitioning the engine from one state
        to another, including reset handling and sync reset conditions. Subclasses
        may override this to customize the transition logic.

        Returns:
            An AlwaysFF object containing the state transition logic.
        """
        pass

    @abstractmethod
    def state_transition(self, next_state: Optional[str]) -> VerilogAssignment:
        """Realzies a transition to a next state."""


class StateRegister(StateRegisterBase):
    """Handles state register declaration and case statement assembly for Verilog generation.

    This class isolates state encoding logic, allowing for easy experimentation with
    different state encodings without modifying the renderer's core logic.
    """

    def __init__(self, worker: WorkerProto) -> None:
        """Initialize the StateRegister.

        Args:
            worker: The worker containing the states.
        """
        super().__init__(worker)

    def declare(self) -> VerilogDeclaration:
        """Declares the state register (enum) in the Verilog module.

        This method creates the state and next_state variables as an enum type
        and adds all state members to the enumeration.
        """
        state_var = self.state_var
        state_nxt_var = self.next_state_var
        state_var_decl = VerilogDeclaration('enum', [state_var, state_nxt_var])
        for state in self.worker.states:
            state_var_decl.add_member(state.name)

        return state_var_decl

    def new_case(self, reg: Literal['next state', 'current state']) -> None:
        """Creates a new case statement for the specified state."""
        if reg == 'next state':
            self._current_case = VerilogCase(self.next_state_var)
        else:
            self._current_case = VerilogCase(self.state_var)

    def add_case(self, case_value: str, item: VerilogRenderable) -> None:
        """Adds an item to the current case.

        Args:
            case_value: The state name for the case statement
            item: The Verilog item to add (assignment, if statement, print, etc.).
        """
        if self._current_case is None:
            raise ValueError('No active case. Call new_case() first.')
        if case_value not in self.states:
            raise ValueError(f'Value {case_value} not found. Please use add_state first to introduce it!')

        # Get the first (and only) case value
        self._current_case.add_item(case_value, item)

    def add_state(self, state_name: str) -> None:
        self.states.append(state_name)

    def build_case(self) -> VerilogCase:
        """Builds and returns the VerilogCase object from accumulated items.

        Returns:
            A VerilogCase object containing all items added via add_case().
        """
        if self._current_case is None:
            raise ValueError('No active case. Call new_case() first.')

        return self._current_case

    def build_state_transition(self) -> AlwaysFF:
        """Builds the state transition logic.

        This method generates the logic for transitioning the engine from one state to another,
        including reset handling and sync reset conditions.
        """
        state_transition = AlwaysFF('CLK_I', 'RST_ASYNC_I')
        state_transition.add_reset(VerilogAssignment(self.state_var, self.worker.reset_state.name))

        block = VerilogIf(f'{self.worker.sync_reset}')
        block.true_branch.add(VerilogAssignment(self.state_var, self.worker.reset_state.name))
        block.false_branch.add(VerilogAssignment(self.state_var, self.next_state_var))

        state_transition.add(block)

        return state_transition

    def encode(self, state_name: str) -> str:
        """Encodes the state in the currently realized way."""
        return state_name

    def state_transition(self, next_state: Optional[str]) -> VerilogAssignment:
        if next_state is None:
            return VerilogAssignment(self.next_state_var, self.state_var)
        return VerilogAssignment(self.next_state_var, next_state)


class OneHotEncodedStateRegister(StateRegisterBase):
    """Handles state register declaration and case statement assembly for Verilog generation     using one-hot encoding.

    This class isolates state encoding logic, allowing for easy experimentation with
    different state encodings without modifying the renderer's core logic. Unlike the
    standard StateRegister which uses Systemverilog enums, this implementation uses
    one-hot encoding where each state is represented by a single bit being set to 1.

    Example:
        >>> from nortl.core.protocols import WorkerProto
        >>> from nortl.renderer.verilog_utils import OneHotEncodedStateRegister
        >>> # Create a one-hot encoded state register
        >>> state_reg = OneHotEncodedStateRegister(worker)
        >>> # The state variable will be declared as logic [N-1:0] state
        >>> # where N is the number of states
    """

    def __init__(self, worker: WorkerProto) -> None:
        """Initialize the OneHotEncodedStateRegister.

        Args:
            worker: The worker containing the states.
        """
        super().__init__(worker)
        self.state_width = len(self.worker.states)

    def declare(self) -> VerilogDeclaration:
        """Declares the state register (one-hot encoded logic) in the Verilog module.

        This method creates the state and next_state variables as logic types with
        a width equal to the number of states. Each state corresponds to a single bit
        in the register (one-hot encoding).

        Returns:
            A VerilogDeclaration object for the state register.
        """
        state_var = self.state_var
        state_nxt_var = self.next_state_var
        state_var_decl = VerilogDeclaration('logic', [state_var, state_nxt_var], self.state_width)

        return state_var_decl

    def new_case(self, reg: Literal['next state', 'current state']) -> None:
        """Creates a new case statement for the specified state.

        Args:
            reg: Either 'next state' or 'current state' to determine which variable
                 the case statement will use.
        """
        if reg == 'next state':
            self._current_case = VerilogCase(self.next_state_var)
        else:
            self._current_case = VerilogCase(self.state_var)

    def add_case(self, case_value: str, item: VerilogRenderable) -> None:
        """Adds an item to the current case.

        Args:
            case_value: The state name for the case statement.
            item: The Verilog item to add (assignment, if statement, print, etc.).

        Raises:
            ValueError: If no active case exists. Call new_case() first or if case_value has not been introduced via add_state
        """
        if self._current_case is None:
            raise ValueError('No active case. Call new_case() first.')
        if case_value not in self.states:
            raise ValueError(f'Value {case_value} not found. Please use add_state first to introduce it!')

        # Get the index of the state and create the one-hot pattern
        state_index = self.states.index(case_value)
        one_hot_pattern = f"(1'b1 << {state_index})"

        # Get the first (and only) case value
        self._current_case.add_item(one_hot_pattern, item)

    def add_state(self, state_name: str) -> None:
        """Adds a state name to the list of states.

        Args:
            state_name: The name of the state to add.
        """
        self.states.append(state_name)

    def build_case(self) -> VerilogCase:
        """Builds and returns the VerilogCase object from accumulated items.

        Returns:
            A VerilogCase object containing all items added via add_case().

        Raises:
            ValueError: If no active case exists. Call new_case() first.
        """
        if self._current_case is None:
            raise ValueError('No active case. Call new_case() first.')

        return self._current_case

    def build_state_transition(self) -> AlwaysFF:
        """Builds the state transition logic.

        This method generates the logic for transitioning the engine from one state
        to another, including reset handling and sync reset conditions. The next state
        is computed using a one-hot encoded logic where each state's next state is
        determined by checking which current state bit is set.

        Returns:
            An AlwaysFF object containing the state transition logic.
        """
        state_transition = AlwaysFF('CLK_I', 'RST_ASYNC_I')
        state_transition.add_reset(VerilogAssignment(self.state_var, self.encode(self.worker.reset_state.name)))

        # Build the next state logic using a case statement on the one-hot encoded state

        block = VerilogIf(f'{self.worker.sync_reset}')
        block.true_branch.add(VerilogAssignment(self.state_var, self.encode(self.worker.reset_state.name)))
        block.false_branch.add(VerilogAssignment(self.state_var, self.next_state_var))

        state_transition.add(block)

        return state_transition

    def encode(self, state_name: str) -> str:
        """Encodes the state in the currently realized way."""
        state_position = self.states.index(state_name)
        return f"(1'b1 << {state_position})"

    def state_transition(self, next_state: Optional[str]) -> VerilogAssignment:
        if next_state is None:
            return VerilogAssignment(self.next_state_var, self.state_var)
        return VerilogAssignment(self.next_state_var, self.encode(next_state))
