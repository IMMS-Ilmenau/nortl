from typing import List, Literal

from nortl.core.protocols import WorkerProto

from .process import AlwaysFF, VerilogAssignment, VerilogCase, VerilogIf
from .structural import VerilogDeclaration
from .utils import VerilogRenderable


class StateRegister:
    """Handles state register declaration and case statement assembly for Verilog generation.

    This class isolates state encoding logic, allowing for easy experimentation with
    different state encodings without modifying the renderer's core logic.
    """

    def __init__(self, worker: WorkerProto) -> None:
        """Initialize the StateRegister.

        Args:
            worker: The worker containing the states.
            state_var: The name of the current state variable.
            next_state_var: The name of the next state variable.
        """
        self.worker = worker
        self.state_var = worker.create_scoped_name('state')
        self.next_state_var = worker.create_scoped_name('state_nxt')
        self._current_case: VerilogCase | None = None
        self.states: List[str] = []

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

        Returns:
            A VerilogCase object containing the state transition logic.
        """
        state_transition = AlwaysFF('CLK_I', 'RST_ASYNC_I')
        state_transition.add_reset(VerilogAssignment(self.state_var, self.worker.reset_state.name))

        block = VerilogIf(f'{self.worker.sync_reset}')
        block.true_branch.add(VerilogAssignment(self.state_var, self.worker.reset_state.name))
        block.false_branch.add(VerilogAssignment(self.state_var, self.next_state_var))

        state_transition.add(block)

        return state_transition
