from nortl import Engine
from nortl.core import CoreEngine
from nortl.core.constructs.loop import WhileLoop
from nortl.core.module import Module
from nortl.core.operations import Const
from nortl.utils.test_wrapper import NoRTLTestBase


class TestTheTestWrapper(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> Engine:
        f = Engine('my_engine')
        f.define_local('testreg', 4, 0)
        return f

    def dut(self, engine: CoreEngine) -> None:
        engine.set(engine.signals['testreg'], 5)
        engine.sync()

    def verify_final_state(self, engine: CoreEngine) -> None:
        self.assertTrue(engine.signals['testreg'] == 5)


class TestTheTestWrapperWithTB(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> Engine:
        f = Engine('my_engine')
        f.define_local('testreg', 4, 0)
        c = f.define_local('channel', 4, 0)
        c.access_checker.disable_check('identical_rw')
        return f

    def dut(self, engine: CoreEngine) -> None:
        for _ in range(10):
            engine.set(engine.signals['testreg'], engine.signals['channel'])
            engine.sync()

    def the_testbench(self, engine: CoreEngine) -> None:
        engine.set(engine.signals['channel'], 5)
        engine.sync()

    def verify_final_state(self, engine: CoreEngine) -> None:
        self.assertTrue(engine.signals['testreg'] == 5)


class TestTheTestWrapperWithTimeout(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> Engine:
        self.expect_timeout = 1

        f = Engine('my_engine')
        f.define_local('testreg', 4, 0)
        c = f.define_local('channel', 4, 0)
        c.access_checker.disable_check('identical_rw')
        return f

    def dut(self, engine: CoreEngine) -> None:
        with WhileLoop(engine, Const(True)):  # endless loop
            engine.sync()

    def the_testbench(self, engine: CoreEngine) -> None:
        pass

    def verify_final_state(self, engine: CoreEngine) -> None:
        # Normally, we get a fail due to the timeout signal, so we need to decrement the error_ctr to mask ths
        self.assertTrue(engine.signals['timeout'])
        self.finish_simulation()


class TestTheTestWrapperWithTimeoutReset(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> Engine:
        self.expect_timeout = 1

        f = Engine('my_engine')
        f.define_local('testreg', 4, 0)
        c = f.define_local('channel', 4, 0)
        self.ctr = f.define_local('test_ctr', 24, 0)
        c.access_checker.disable_check('identical_rw')
        return f

    def dut(self, engine: CoreEngine) -> None:
        with WhileLoop(engine, self.ctr < 0x10010):  # endless loop
            engine.set(self.ctr, self.ctr + 1)
            self.reset_timeout()
            engine.sync()

        self.assertEqual(self.ctr, 0x10010)

    def the_testbench(self, engine: CoreEngine) -> None:
        pass

    def verify_final_state(self, engine: CoreEngine) -> None:
        self.finish_simulation()


class TestTheTestWrapperInputsShoulbeBeWriteable(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> Engine:
        f = Engine('my_engine')
        f.define_input('testreg', 4)
        return f

    def dut(self, engine: CoreEngine) -> None:
        engine.set(engine.signals['testreg'], 5)
        engine.sync()

    def verify_final_state(self, engine: CoreEngine) -> None:
        self.assertTrue(engine.signals['testreg'] == 5)


INVERTER_CODE = """
module inverter (
    input A,
    output Q
);

assign Q = ~A;

endmodule
"""


class TestCustomModule(NoRTLTestBase[CoreEngine]):
    """Test adding custom Verilog modules."""

    def init_sequence(self) -> Engine:
        f = Engine('my_engine')
        inverter_in = f.define_local('inverter_in', reset_value=0)
        inverter_out = f.define_local('inverter_out')

        inverter = Module('inverter', INVERTER_CODE)
        inverter.add_port('A')
        inverter.add_port('Q')
        inverter._ignore_clk_rst_connection = True
        f.add_module(inverter)
        instance = f.create_module_instance('inverter', 'I_INVERTER')
        instance.connect_port('A', inverter_in)
        instance.connect_port('Q', inverter_out)

        return f

    def dut(self, engine: CoreEngine) -> None:
        engine.set(engine.signals['inverter_in'], 1)
        engine.sync()

    def verify_final_state(self, engine: CoreEngine) -> None:
        self.assertTrue(engine.signals['inverter_out'] == 0)
