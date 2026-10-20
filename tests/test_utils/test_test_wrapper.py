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


class TestTheTestWrapperWithValueCapture(NoRTLTestBase[Engine]):
    """Test that values captured during simulation are parsed and passed to callback_after_simulation."""

    def init_sequence(self) -> Engine:
        f = Engine('my_engine')
        f.define_local('counter', 8, 0)
        return f

    def dut(self, engine: Engine) -> None:
        for _ in range(5):
            engine.set(engine.signals['counter'], engine.signals['counter'] + 1)
            engine.capture('count', engine.signals['counter'])
            engine.capture('pair', engine.signals['counter'], 42)
            engine.sync()

    def callback_after_simulation(self, engine: Engine, captured_values: list[dict[str, object]]) -> None:
        # One dict per engine.capture() call, in emission order
        assert captured_values == [
            {'count': [1]},
            {'pair': [1, 42]},
            {'count': [2]},
            {'pair': [2, 42]},
            {'count': [3]},
            {'pair': [3, 42]},
            {'count': [4]},
            {'pair': [4, 42]},
            {'count': [5]},
            {'pair': [5, 42]},
        ]

    def verify_final_state(self, engine: Engine) -> None:
        self.assertTrue(engine.signals['counter'] == 5)
