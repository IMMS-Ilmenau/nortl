from typing import List

from nortl.core.protocols import EngineProto

from .verilog_utils.process import AlwaysComb, AlwaysFF, VerilogAssignment, VerilogCase, VerilogIf, VerilogPrint, VerilogPrintf
from .verilog_utils.structural import VerilogDeclaration, VerilogModule

# FIXME: Make empty blocks being not rendered at all.


class VerilogRenderer:
    """This class transforms the engine data into a verilog code.

    To simplify matters, the verilog_utils folder contains code for rendering individual blocks.
    """

    def __init__(self, engine: EngineProto, include_modules: bool = True, clock_gating: bool = False):
        """Initializes the VerilogRenderer with the engine data and rendering options.

        Args:
            engine: The CoreEngine object representing the finite state machine.
            include_modules: A boolean indicating whether to include module instantiations in the generated Verilog code. Defaults to True.
            clock_gating: A boolean indicating whether to enable clock gating logic in the generated Verilog code. Defaults to False.
        """
        self.engine = engine
        self.verilog_module = VerilogModule(self.engine.module_name)

        self.codelst: List[str] = []

        self.include_modules = include_modules
        self.clock_gating = clock_gating

        self.clk_request_signals: List[str] = []

    def clear(self) -> None:
        """Clears the internal code list and resets the Verilog module for a new rendering cycle."""
        self.codelst = []
        self.verilog_module = VerilogModule(self.engine.module_name)

    def render(self) -> str:
        """Renders the engine into Verilog code.

        This method orchestrates the creation of the Verilog module, signals, instances, and logic blocks.

        Returns:
            A string containing the complete Verilog code.
        """
        self.clear()

        self.create_interface()
        self.create_state_enum()
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
            state_variable = worker.create_scoped_name('state_nxt')
            cases = VerilogCase(state_variable)

            for state in worker.states:
                if state.has_metadata('Clock_gating'):  # FIXME: Add Metadata to docs
                    cases.add_case(state.name)
                    cases.add_item(state.name, VerilogAssignment('GCLK_enable', "1'b0"))

                    for condition, _ in state.transitions:
                        block = VerilogIf(condition)
                        block.true_branch.add(VerilogAssignment('GCLK_enable', "1'b1"))
                        cases.add_item(state.name, block)

                    for signal, val, condition in state.assignments:
                        block = VerilogIf((signal != val) & (condition))
                        block.true_branch.add(VerilogAssignment('GCLK_enable', "1'b1"))
                        cases.add_item(state.name, block)

            clk_en_proc.add(cases)

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
        self.verilog_module.ports.append(VerilogDeclaration('input logic', 'CLK_I'))
        self.verilog_module.ports.append(VerilogDeclaration('input logic', 'RST_ASYNC_I'))

        for name, signal in self.engine.signals.items():
            if signal.type == 'local':
                verilog_signal = VerilogDeclaration(signal.data_type, name, width=signal.width)
                self.verilog_module.signals.append(verilog_signal)
            else:
                if signal.data_type in ['reg', 'wire', 'logic']:
                    verilog_signal = VerilogDeclaration(f'{signal.type} {signal.data_type}', name, signal.width)
                else:
                    verilog_signal = VerilogDeclaration(signal.data_type, name, width=signal.width)
                self.verilog_module.ports.append(verilog_signal)

    def create_state_enum(self) -> None:
        """Creates the Verilog state enumeration.

        This method defines the enumeration type for the engine states, which is used to represent
        the current state of the engine in the Verilog code.
        """
        for worker in self.engine.workers.values():
            state_variable = worker.create_scoped_name('state')
            state_nxt_variable = worker.create_scoped_name('state_nxt')
            state_var = VerilogDeclaration('enum', [state_variable, state_nxt_variable])
            for state in worker.states:
                state_var.add_member(state.name)
            self.verilog_module.signals.append(state_var)

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
            state_variable = worker.create_scoped_name('state')
            state_nxt_variable = worker.create_scoped_name('state_nxt')

            next_state_func.add(VerilogAssignment(state_nxt_variable, state_variable))

            cases = VerilogCase(state_variable)

            for state in worker.states:
                cases.add_case(state.name)

                for condition, next_state in state.transitions:
                    if condition.render() == "1'h1":
                        cases.add_item(state.name, VerilogAssignment(state_nxt_variable, next_state))
                    elif condition.render() == "1'h0":
                        pass
                    else:
                        item = VerilogIf(condition)
                        item.true_branch.add(VerilogAssignment(state_nxt_variable, next_state))
                        cases.add_item(state.name, item)

            next_state_func.add(cases)

        self.verilog_module.functionals.append(next_state_func)

    def create_output_function(self) -> None:
        """Creates the Verilog output function.

        This method generates the logic for updating the output signals of the engine, based on the
        current state and the input signals.
        """
        output_func = AlwaysFF('CLK_I', 'RST_ASYNC_I')

        for signal, reset_val, _ in self.engine.main_worker.reset_state.assignments:
            output_func.add_reset(VerilogAssignment(signal, reset_val))

        for signal in self.engine.signals.values():
            if signal.pulsing:
                output_func.add(VerilogAssignment(signal, '0'))

        for worker in self.engine.workers.values():
            state_nxt_variable = worker.create_scoped_name('state_nxt')
            cases = VerilogCase(state_nxt_variable)

            for state in worker.states:
                if len(state.assignments) > 0:
                    cases.add_case(state.name)

                    for signal, val, condition in state.assignments:
                        if condition.render() == "1'h1":
                            cases.add_item(state.name, VerilogAssignment(signal, val))
                        else:
                            block = VerilogIf(condition)
                            block.true_branch.add(VerilogAssignment(signal, val))
                            cases.add_item(state.name, block)

            output_func.add(cases)

        self.verilog_module.functionals.append(output_func)

    def create_prints(self) -> None:
        """Creates the print statements that have been put into each state."""
        output_func = AlwaysFF('CLK_I', 'RST_ASYNC_I')

        for worker in self.engine.workers.values():
            state_nxt_variable = worker.create_scoped_name('state_nxt')
            cases = VerilogCase(state_nxt_variable)

            for state in worker.states:
                cases.add_case(state.name)

                for fname, item in state._printfs.items():
                    for line, val in item:
                        cases.add_item(state.name, VerilogPrintf(fname, line, *[v.render() for v in val]))

                for line, val in state._prints:
                    cases.add_item(state.name, VerilogPrint(line, *[v.render() for v in val]))

            output_func.add(cases)

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
        state_transition = AlwaysFF('CLK_I', 'RST_ASYNC_I')
        for worker in self.engine.workers.values():
            state_variable = worker.create_scoped_name('state')
            state_nxt_variable = worker.create_scoped_name('state_nxt')

            state_transition.add_reset(VerilogAssignment(state_variable, worker.reset_state.name))

            block = VerilogIf(f'{worker.sync_reset}')
            block.true_branch.add(VerilogAssignment(state_variable, worker.reset_state.name))
            block.false_branch.add(VerilogAssignment(state_variable, state_nxt_variable))

            state_transition.add(block)

        self.verilog_module.functionals.append(state_transition)
