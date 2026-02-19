from typing import Dict, Iterable, List, Union

from nortl.core.protocols import ConditionalAssignmentProto, EngineProto, SelectorAssignmentProto
from nortl.renderer.verilog_utils.utils import VerilogRenderable

from .verilog_utils import ENCODINGS, create_state_var
from .verilog_utils.abstractions import MultiHotEncodedStateRegister, OneHotEncodedStateRegister, StateRegister
from .verilog_utils.process import AlwaysComb, AlwaysFF, VerilogAssignment, VerilogIf, VerilogPrint, VerilogPrintf
from .verilog_utils.structural import VerilogDeclaration, VerilogModule, VerilogPortDeclaration

# FIXME: Make empty blocks being not rendered at all.


class VerilogRenderer:
    """This class transforms the engine data into a verilog code.

    To simplify matters, the verilog_utils folder contains code for rendering individual blocks.
    """

    def __init__(
        self,
        engine: EngineProto,
        include_modules: bool = True,
        clock_gating: bool = False,
        encoding: ENCODINGS = 'binary',
        support_unique_if: bool = False,
    ):
        """Initializes the VerilogRenderer with the engine data and rendering options.

        Args:
            engine: The CoreEngine object representing the finite state machine.
            include_modules: A boolean indicating whether to include module instantiations in the generated Verilog code. Defaults to True.
            clock_gating: A boolean indicating whether to enable clock gating logic in the generated Verilog code. Defaults to False.
            encoding: Encoding to use for the state registers
            support_unique_if: If enabled, will render `unique if` and `priority if` statements. This is not supported by all simulators.
        """
        self.engine = engine
        self.verilog_module = VerilogModule(self.engine.module_name)

        self.codelst: List[str] = []

        self.include_modules = include_modules
        self.clock_gating = clock_gating
        self.encoding = encoding
        self.support_unique_if = support_unique_if

        self.clk_request_signals: List[str] = []

        self.state_regs: Dict[str, Union[StateRegister, OneHotEncodedStateRegister, MultiHotEncodedStateRegister]] = {}

    def clear(self) -> None:
        """Clears the internal code list and resets the Verilog module for a new rendering cycle."""
        self.codelst = []
        self.verilog_module = VerilogModule(self.engine.module_name)
        self.state_regs = {}

    def render(self) -> str:
        """Renders the engine into Verilog code.

        This method orchestrates the creation of the Verilog module, signals, instances, and logic blocks.

        Returns:
            A string containing the complete Verilog code.
        """
        self.clear()

        self.create_interface()
        self.create_state_regs()
        self.create_instances()
        self.create_next_state_logic()
        self.create_output_function()
        self.create_prints()
        self.create_combinationals()
        self.create_state_transition()

        if self.clock_gating:
            self.create_clock_gates()

        ret: List[str] = []
        if self.include_modules:
            ret.extend(m.hdl_code for m in self.engine.modules.values())

        ret.append(self.verilog_module.render())

        return '\n'.join(ret)

    def create_clock_gates(self) -> None:
        """Creates the clock gating logic, including gated clock signals and enables.

        This method adds the necessary signals and connections for implementing clock gating,
        which can reduce power consumption by disabling the clock signal to inactive parts of the engine.
        """
        # Create gated clock signals and clock enables
        self.verilog_module.signals.append(VerilogDeclaration('logic', 'GCLK'))
        self.verilog_module.signals.append(VerilogDeclaration('logic', 'GCLK_enable'))
        self.verilog_module.signals.append(VerilogDeclaration('logic', 'GCLK_enable_latched'))

        clk_requests: List[str] = []

        # Get clock requests from instances
        for name, instance in self.engine.module_instances.items():
            if instance.module.clk_request_port is not None:
                signalname = f'clk_request_{name}'
                self.verilog_module.signals.append(VerilogDeclaration('logic', signalname))
                clk_requests.append(signalname)
            if not instance.module._ignore_clk_rst_connection and instance._clock_gating:
                verilog_inst = self.verilog_module.get_instance(name)
                verilog_inst.add_connection('CLK_I', 'GCLK')

        self.create_clock_enable(clk_requests)

        # Change Clock signal of Always_ff blocks
        for blk in self.verilog_module.functionals:
            if isinstance(blk, AlwaysFF):
                blk.clk = 'GCLK'

        # Instantiate Clock Gate
        clock_gate = VerilogDeclaration('nortl_clock_gate', 'I_CLOCK_GATE')
        clock_gate.add_connection('CLK_I', 'CLK_I')
        clock_gate.add_connection('EN', 'GCLK_enable')
        clock_gate.add_connection('GCLK_O', 'GCLK')

        self.verilog_module.instances.append(clock_gate)

    def create_clock_enable(self, clk_requests: List[str]) -> None:
        """Creates the clock enable signal based on state and clock requests.

        This method generates the logic for controlling the clock enable signal, which is used to
        disable the clock signal to inactive parts of the engine, reducing power consumption.
        """
        # Create clock enable by states
        clk_en_proc = AlwaysComb()
        clk_en_proc.add(VerilogAssignment('GCLK_enable', "1'b1"))

        for worker in self.engine.workers.values():
            self.state_regs[worker.name].new_case('next state')

            for state in worker.states:
                if state.has_metadata('Clock_gating'):  # FIXME: Add Metadata to docs
                    self.state_regs[worker.name].add_case(state.name, VerilogAssignment('GCLK_enable', "1'b0"))

                    for condition, _ in state.transitions:
                        block = VerilogIf(condition)
                        block.true_branch.add(VerilogAssignment('GCLK_enable', "1'b1"))
                        self.state_regs[worker.name].add_case(state.name, block)

                    for assignment in state.assignments:
                        if assignment.unconditional:
                            block = VerilogIf((assignment.signal != assignment.value))
                            block.true_branch.add(VerilogAssignment('GCLK_enable', "1'b1"))
                            self.state_regs[worker.name].add_case(state.name, block)
                        else:
                            # FIXME Selectively enable clock for conditional assignments
                            self.state_regs[worker.name].add_case(state.name, VerilogAssignment('GCLK_enable', "1'b1"))

            clk_en_proc.add(self.state_regs[worker.name].build_case())

        for req in clk_requests:
            block = VerilogIf(req)
            block.true_branch.add(VerilogAssignment('GCLK_enable', "1'b1"))
            clk_en_proc.add(block)

        self.verilog_module.functionals.append(clk_en_proc)

    def create_interface(self) -> None:
        """Creates the Verilog module interface, including parameters, signals, and ports.

        This method defines the input and output signals of the Verilog module, as well as any
        parameters that can be used to customize its behavior.
        """
        # Parameters
        for param in self.engine.parameters.values():
            if param.width is not None:
                self.verilog_module.parameters[f'[{param.width - 1}:0] {param.name}'] = param.default_value
            else:
                self.verilog_module.parameters[param.name] = param.default_value

        # Signals and Ports
        self.verilog_module.ports.append(VerilogPortDeclaration('input logic', 'CLK_I'))
        self.verilog_module.ports.append(VerilogPortDeclaration('input logic', 'RST_ASYNC_I'))

        for name, signal in self.engine.signals.items():
            if signal.type == 'local':
                verilog_signal = VerilogDeclaration(signal.data_type, name, width=signal.width)
                self.verilog_module.signals.append(verilog_signal)
            else:
                if signal.data_type in ['reg', 'wire', 'logic']:
                    port_declaration = VerilogPortDeclaration(f'{signal.type} {signal.data_type}', name, signal.width)
                else:
                    port_declaration = VerilogPortDeclaration(signal.data_type, name, width=signal.width)
                self.verilog_module.ports.append(port_declaration)

    def create_state_regs(self) -> None:
        """Creates the Verilog state enumeration.

        This method defines the enumeration type for the engine states, which is used to represent
        the current state of the engine in the Verilog code.
        """

        for name, worker in self.engine.workers.items():
            self.state_regs[name] = create_state_var(worker, self.encoding)
            for state in worker.states:
                self.state_regs[name].add_state(state.name)

        for state_reg in self.state_regs.values():
            self.verilog_module.signals.append(state_reg.declare())

    def create_instances(self) -> None:
        """Creates the Verilog module instances.

        This method instantiates the submodules of the engine, connecting their ports to the
        appropriate signals in the top-level module.
        """
        for instance in self.engine.module_instances.values():
            decl = VerilogDeclaration(instance.module.name, instance.name)

            # Parameters
            for name, value in instance.module.parameters.items():
                if name in instance.parameter_overrides:
                    decl.add_parameter(name, instance.parameter_overrides[name].render())
                else:
                    decl.add_parameter(name, value)

            # Connections
            if not instance.module._ignore_clk_rst_connection:
                decl.add_connection('CLK_I', 'CLK_I')
                decl.add_connection('RST_ASYNC_I', 'RST_ASYNC_I')

            for port_name, signal in instance.port_connections.items():
                decl.add_connection(port_name, signal.render())

            self.verilog_module.instances.append(decl)

    def create_next_state_logic(self) -> None:
        """Creates the Verilog next state logic.

        This method generates the logic for determining the next state of the engine, based on the
        current state and the input signals.
        """
        next_state_func = AlwaysComb()

        for worker in self.engine.workers.values():
            self.state_regs[worker.name].new_case('current state')

            next_state_func.add(self.state_regs[worker.name].state_transition(None))

            for state in worker.states:
                for condition, next_state in state.transitions:
                    if condition.render() == "1'h1":
                        self.state_regs[worker.name].add_case(state.name, self.state_regs[worker.name].state_transition(next_state.name))
                    elif condition.render() == "1'h0":
                        pass
                    else:
                        item = VerilogIf(condition)
                        item.true_branch.add(self.state_regs[worker.name].state_transition(next_state.name))
                        self.state_regs[worker.name].add_case(state.name, item)

            next_state_func.add(self.state_regs[worker.name].build_case())

        self.verilog_module.functionals.append(next_state_func)

    def create_output_function(self) -> None:  # noqa: C901
        """Creates the Verilog output function.

        This method generates the logic for updating the output signals of the engine, based on the
        current state and the input signals.
        """
        output_func = AlwaysFF('CLK_I', 'RST_ASYNC_I')

        for assignment in self.engine.main_worker.reset_state.assignments:
            if not assignment.unconditional:
                raise RuntimeError('Conditional assignments are not allowed in the reset state.')
            output_func.add_reset(VerilogAssignment(assignment.signal, assignment.value))

        for signal in self.engine.signals.values():
            if signal.pulsing:
                output_func.add(VerilogAssignment(signal, '0'))

        for worker in self.engine.workers.values():
            self.state_regs[worker.name].new_case('next state')

            for state in worker.states:
                if len(state.assignments) > 0:
                    for assignment in state.assignments:
                        if assignment.unconditional:
                            self.state_regs[worker.name].add_case(state.name, VerilogAssignment(assignment.signal, assignment.value))
                        else:
                            for block in self._extract_conditional_assignment(assignment, support_unique_if=self.support_unique_if):
                                self.state_regs[worker.name].add_case(state.name, block)

            output_func.add(self.state_regs[worker.name].build_case())

        self.verilog_module.functionals.append(output_func)

    @classmethod
    def _extract_conditional_assignment(
        cls, assignment: Union[ConditionalAssignmentProto, SelectorAssignmentProto], support_unique_if: bool = False
    ) -> Iterable[VerilogRenderable]:
        for i, (condition, value) in enumerate(assignment.cases):
            if i == 0:
                if support_unique_if:
                    block = VerilogIf(condition, keyword='priority if' if assignment.priority else 'unique if')
                else:
                    block = VerilogIf(condition, keyword='if')
            else:
                block = VerilogIf(condition, keyword='else if')

            if hasattr(value, 'cases'):
                # Value is an selector assignment itself, turn it into nested If, Else If, etc.
                for nested_block in cls._extract_conditional_assignment(value, support_unique_if=support_unique_if):  # type: ignore[arg-type]
                    block.true_branch.add(nested_block)
            else:
                block.true_branch.add(VerilogAssignment(assignment.signal, value))

            # Close off the list of cases with a default
            if i == (len(assignment.cases) - 1) and assignment.default is not None:
                if hasattr(assignment.default, 'cases'):
                    for nested_block in cls._extract_conditional_assignment(assignment.default, support_unique_if=support_unique_if):  # type: ignore[arg-type]
                        block.false_branch.add(nested_block)
                else:
                    block.false_branch.add(VerilogAssignment(assignment.signal, assignment.default))
            yield block

    def create_prints(self) -> None:
        """Creates the print statements that have been put into each state."""
        output_func = AlwaysFF('CLK_I', 'RST_ASYNC_I')

        for worker in self.engine.workers.values():
            self.state_regs[worker.name].new_case('next state')

            for state in worker.states:
                for fname, item in state._printfs.items():
                    for line, val in item:
                        self.state_regs[worker.name].add_case(state.name, VerilogPrintf(fname, line, *[v.render() for v in val]))

                for line, val in state._prints:
                    self.state_regs[worker.name].add_case(state.name, VerilogPrint(line, *[v.render() for v in val]))

            output_func.add(self.state_regs[worker.name].build_case())

        self.verilog_module.functionals.append(output_func)

    def create_combinationals(self) -> None:
        """Creates the Verilog combinational logic.

        This method generates the combinational logic for the engine, based on the input signals.
        """
        combinationals = AlwaysComb()

        for signal, value in self.engine.combinationals:
            combinationals.add(VerilogAssignment(signal, value))

        self.verilog_module.functionals.append(combinationals)

    def create_state_transition(self) -> None:
        """Creates the Verilog state transition logic.

        This method generates the logic for transitioning the engine from one state to another.
        """
        for state_reg in self.state_regs.values():
            self.verilog_module.functionals.append(state_reg.build_state_transition())
