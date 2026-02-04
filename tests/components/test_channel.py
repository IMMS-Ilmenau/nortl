# ruff: noqa: N801

from nortl.components.channel import Channel, ElasticChannel
from nortl.core import CoreEngine
from nortl.utils.test_wrapper import NoRTLTestBase


class TestChannel(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.channel = Channel(engine, 8, 'testchannel')
        return engine

    def dut(self, engine: CoreEngine) -> None:
        for i in range(10):
            self.channel.send(i)

    def the_testbench(self, engine: CoreEngine) -> None:
        for i in range(10):
            with self.channel.receive() as rec_val:
                self.assertTrue(rec_val == i)


class TestChannelBlocksSender(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        self.expect_timeout = 1
        engine = CoreEngine('my_engine')
        self.channel = Channel(engine, 8, 'testchannel')
        return engine

    def dut(self, engine: CoreEngine) -> None:
        for i in range(10):
            self.channel.send(i)
        self.assertTrue(0)

    def verify_final_state(self, engine: CoreEngine) -> None:
        self.assertTrue(engine.signals['timeout'])
        self.finish_simulation()


class TestEmptyChannelBlocksReciever(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        self.expect_timeout = 1
        engine = CoreEngine('my_engine')
        self.channel = Channel(engine, 8, 'testchannel')
        return engine

    def dut(self, engine: CoreEngine) -> None:
        for i in range(10):
            self.channel.receive()
        self.assertTrue(0)

    def verify_final_state(self, engine: CoreEngine) -> None:
        self.assertTrue(engine.signals['timeout'])
        self.finish_simulation()


class TestElasticChannel_Trivial(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.channel = ElasticChannel(engine, 8, 'testchannel', 8)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        for i in range(10):
            self.channel.send(i)

    def the_testbench(self, engine: CoreEngine) -> None:
        for i in range(10):
            with self.channel.receive() as rec_val:
                self.assertTrue(rec_val == i)


class TestElasticChannel_SendMultiple(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.channel = ElasticChannel(engine, 8, 'testchannel', 8)
        return engine

    def dut(self, fsm: CoreEngine) -> None:
        for i in range(5):
            print(2 * i, 2 * i + 1)
            self.channel.send_multiple([2 * i + 1, 2 * i])

    def the_testbench(self, fsm: CoreEngine) -> None:
        for i in range(10):
            with self.channel.receive() as rec_val:
                self.assertEqual(rec_val, i)


class TestElasticChannel_sender_faster_than_rec(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.channel = ElasticChannel(engine, 8, 'testchannel', 8)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        for i in range(10):
            self.channel.send(i)

    def the_testbench(self, engine: CoreEngine) -> None:
        for i in range(10):
            engine.sync()
            with self.channel.receive() as rec_val:
                self.assertTrue(rec_val == i)


class TestElasticChannel_delayed_rec(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.channel = ElasticChannel(engine, 8, 'testchannel', 8)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        for i in range(100):
            self.channel.send(i)

    def the_testbench(self, engine: CoreEngine) -> None:
        for _ in range(256):
            engine.sync()
        for i in range(100):
            with self.channel.receive() as rec_val:
                self.assertTrue(rec_val == i)


class TestElasticChannel_delayed_send(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.channel = ElasticChannel(engine, 8, 'testchannel', 8)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        for _ in range(256):
            engine.sync()
        for i in range(100):
            self.channel.send(i)

    def the_testbench(self, engine: CoreEngine) -> None:
        for i in range(100):
            with self.channel.receive() as rec_val:
                self.assertTrue(rec_val == i)


class TestElasticChannel_rec_faster_than_sender(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.channel = ElasticChannel(engine, 8, 'testchannel', 8)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        engine.sync()
        for i in range(10):
            self.channel.send(i)
        engine.sync()

    def the_testbench(self, engine: CoreEngine) -> None:
        for i in range(10):
            with self.channel.receive() as rec_val:
                self.assertTrue(rec_val == i)


class TestElasticChannelBlocksSender(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        self.expect_timeout = 1
        engine = CoreEngine('my_engine')
        self.channel = ElasticChannel(engine, 8, 'testchannel', 8)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        for i in range(10):
            self.channel.send(i)
        self.assertTrue(0)

    def verify_final_state(self, engine: CoreEngine) -> None:
        self.assertTrue(engine.signals['timeout'])
        self.finish_simulation()


class TestEmptyElasticChannelBlocksReciever(NoRTLTestBase):
    def init_sequence(self) -> CoreEngine:
        self.expect_timeout = 1

        engine = CoreEngine('my_engine')
        self.channel = ElasticChannel(engine, 8, 'testchannel', 8)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        for i in range(10):
            self.channel.receive()
        self.assertTrue(0)

    def verify_final_state(self, engine: CoreEngine) -> None:
        self.assertTrue(engine.signals['timeout'])
        self.finish_simulation()
