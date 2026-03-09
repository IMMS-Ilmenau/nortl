from typing import Dict, Iterable, List, Union

from nortl.core.protocols import ConditionalAssignmentProto, EngineProto, SelectorAssignmentProto
from nortl.renderer.verilog_utils.utils import VerilogRenderable

from .verilog_utils import ENCODINGS, create_state_var
from .verilog_utils.abstractions import MultiHotEncodedStateRegister, OneHotEncodedStateRegister, StateRegister
from .verilog_utils.process import AlwaysComb, AlwaysFF, VerilogAssignment, VerilogCase, VerilogIf, VerilogPrint, VerilogPrintf
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
        self.state_transition_blocks: Dict[str, AlwaysFF] = {}
        self.output_function_blocks: Dict[str, AlwaysFF] = {}
        self.print_function_blocks: Dict[str, AlwaysFF] = {}

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
        """Creates a three-level clock gating hierarchy.

        Level 1 - Module gate (GCLK): propagates to all lower-level gates and gates sub-module
        instances. Enabled when any register in the module will change.

        Level 2a - Output gate (GCLK_output): cascaded from GCLK. Gates the shared output and
        print AlwaysFF blocks. Enabled by XOR gating: asserted when any output register's next
        value (determined from state_nxt and the state assignments) differs from its current value.

        Level 2b - Per-worker state gates (GCLK_<name>): cascaded from GCLK. One per worker.
        Gates the state transition AlwaysFF for that worker. Enabled when state_nxt != state.
        """
        # Module-level gate signals
        self.verilog_module.signals.append(VerilogDeclaration('logic', 'GCLK'))
        self.verilog_module.signals.append(VerilogDeclaration('logic', 'GCLK_enable'))

        # Output register gate signals
        self.verilog_module.signals.append(VerilogDeclaration('logic', 'GCLK_output'))
        self.verilog_module.signals.append(VerilogDeclaration('logic', 'GCLK_output_enable'))

        # Per-worker state register gate signals
        for worker_name in self.engine.workers:
            self.verilog_module.signals.append(VerilogDeclaration('logic', f'GCLK_{worker_name}'))
            self.verilog_module.signals.append(VerilogDeclaration('logic', f'GCLK_{worker_name}_enable'))

        # Sub-module clock request signals
        clk_requests: List[str] = []
        for name, instance in self.engine.module_instances.items():
            if instance.module.clk_request_port is not None:
                signalname = f'clk_request_{name}'
                self.verilog_module.signals.append(VerilogDeclaration('logic', signalname))
                clk_requests.append(signalname)
            if not instance.module._ignore_clk_rst_connection and instance._clock_gating:
                verilog_inst = self.verilog_module.get_instance(name)
                verilog_inst.add_connection('CLK_I', 'GCLK')

        # Output and print blocks use the XOR-gated output clock
        self.output_function_blocks['_shared'].clk = 'GCLK_output'
        self.print_function_blocks['_shared'].clk = 'GCLK_output'

        # Per-worker state transition blocks use their own gated clock
        for worker_name, blk in self.state_transition_blocks.items():
            blk.clk = f'GCLK_{worker_name}'

        # Create clock enable logic
        self.create_clock_enable(clk_requests)

        # Instantiate module-level clock gate
        clock_gate = VerilogDeclaration('nortl_clock_gate', 'I_CLOCK_GATE')
        clock_gate.add_connection('CLK_I', 'CLK_I')
        clock_gate.add_connection('EN', 'GCLK_enable')
        clock_gate.add_connection('GCLK_O', 'GCLK')
        self.verilog_module.instances.append(clock_gate)

        # Instantiate output register clock gate, cascaded from GCLK
        output_gate = VerilogDeclaration('nortl_clock_gate', 'I_CLOCK_GATE_output')
        output_gate.add_connection('CLK_I', 'GCLK')
        output_gate.add_connection('EN', 'GCLK_output_enable')
        output_gate.add_connection('GCLK_O', 'GCLK_output')
        self.verilog_module.instances.append(output_gate)

    def create_clock_enable(self, clk_requests: List[str]) -> None:
        """Creates all clock enable signals.

        Per-worker enable (GCLK_<name>_enable): asserted when state_nxt != state.

        Output enable (GCLK_output_enable): XOR-based, asserted when any output register's
        next value (derived from state_nxt and the state assignments) differs from its current value.

        Module-level enable (GCLK_enable): OR of output enable, all per-worker enables, and
        any sub-module clock requests. Ensures GCLK propagates to all cascaded gates whenever
        anything needs to clock.
        """
        worker_enables: List[str] = []

        # Per-worker enable: active when state register will change OR when sync reset is asserted
        for worker_name, state_reg in self.state_regs.items():
            enable_signal = f'GCLK_{worker_name}_enable'
            worker_enables.append(enable_signal)

            worker = self.engine.workers[worker_name]
            enable_expr = f'({state_reg.next_state_var} != {state_reg.state_var})'
            sync_reset_expr = f'{worker.sync_reset}'
            if sync_reset_expr != '0':
                enable_expr = f'{enable_expr} | {sync_reset_expr}'

            cg_proc = AlwaysComb()
            cg_proc.add(VerilogAssignment(enable_signal, enable_expr))
            self.verilog_module.functionals.append(cg_proc)

        # Output enable: XOR-based comparison of current output values vs. next values
        self._create_output_clock_enable()

        # Module-level enable: OR of everything — ensures GCLK reaches all cascaded gates
        all_enables = ['GCLK_output_enable', *worker_enables, *clk_requests]
        module_cg_proc = AlwaysComb()
        module_cg_proc.add(VerilogAssignment('GCLK_enable', ' | '.join(all_enables)))
        self.verilog_module.functionals.append(module_cg_proc)

    def _create_output_clock_enable(self) -> None:
        """Builds GCLK_output_enable using XOR-based clock gating.

        For each worker, a case statement on state_nxt checks whether each output register's
        next value (as determined by the state's assignments) differs from its current value.
        The enable is asserted if any output will change.

        Pulsing signals are also handled: in states where they are not explicitly assigned they
        will be reset to 0, so the enable is asserted when the signal is currently non-zero.
        """
        pulsing_signals = [s for s in self.engine.signals.values() if s.pulsing]

        output_en_proc = AlwaysComb()
        output_en_proc.add(VerilogAssignment('GCLK_output_enable', "1'b0"))

        for worker in self.engine.workers.values():
            state_reg = self.state_regs[worker.name]
            case = VerilogCase(state_reg.next_state_var)

            for state in worker.states:
                unconditionally_assigned = {a.signal for a in state.assignments if a.unconditional}

                for assignment in state.assignments:
                    if assignment.unconditional:
                        # XOR check: enable if current value differs from the value to be assigned
                        check = VerilogIf(assignment.signal != assignment.value)
                        check.true_branch.add(VerilogAssignment('GCLK_output_enable', "1'b1"))
                        case.add_item(state_reg.encode(state.name), check)
                    else:
                        # Conservative for conditional assignments: always enable
                        case.add_item(state_reg.encode(state.name), VerilogAssignment('GCLK_output_enable', "1'b1"))

                # Pulsing signals not assigned in this state will be reset to 0
                for ps in pulsing_signals:
                    if ps not in unconditionally_assigned:
                        check = VerilogIf(ps != 0)
                        check.true_branch.add(VerilogAssignment('GCLK_output_enable', "1'b1"))
                        case.add_item(state_reg.encode(state.name), check)

            output_en_proc.add(case)

        self.verilog_module.functionals.append(output_en_proc)

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

            if self.clock_gating and instance.module.clk_request_port is not None:
                signalname = f'clk_request_{instance.name}'
                decl.add_connection(instance.module.clk_request_port, signalname)

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

            next_state_func.add(self.state_regs[worker.name].default_state_assignment())

            for state in worker.states:
                for condition, next_state in state.transitions:
                    self.state_regs[worker.name].state_transition(state.name, next_state.name, condition)

            next_state_func.add(self.state_regs[worker.name].build_case())

        self.verilog_module.functionals.append(next_state_func)

    def create_output_function(self) -> None:  # noqa: C901
        """Creates the Verilog output function.

        This method generates the logic for updating the output signals of the engine, based on the
        current state and the input signals.

        All workers share a single AlwaysFF because multiple workers can assign to the same output
        signal. Splitting into per-worker blocks would create multiple drivers for the same register,
        which is a Verilog error. When clock gating is enabled, this block is driven by the
        module-level GCLK, which is itself enabled whenever any worker's state is transitioning.
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

        self.output_function_blocks['_shared'] = output_func
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

        self.print_function_blocks['_shared'] = output_func
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
