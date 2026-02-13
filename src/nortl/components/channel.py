import math
from typing import List, Sequence

from nortl.core import Concat, Const, IfThenElse, Volatile
from nortl.core.operations import to_renderable
from nortl.core.protocols import EngineProto, Renderable, ScratchSignalProto, SignalProto

# FIXME: Create Abstract base class for Channel


class Channel:
    """A simple Channel with a ready/valid handshake to send data from one thread to another.

    The send and rec functions realize a blocking transfer. This channel cannot be used for a elastic pipeline!

    Example:
    ```python
    from nortl import Engine

    engine = Engine("my_engine")
    out = engine.define_output("test_output", width=8)
    channel = Channel(engine, width=8, name='my_channel')

    # Send data from one thread to another
    channel.send(42)
    ```
    """

    def __init__(self, engine: EngineProto, width: int, name: str = 'channel') -> None:
        """Initializes the Channel.

        The Channel uses a ready/valid handshake protocol to transfer data between threads.
        The signals are defined with identical read/write access to ensure they can be accessed
        from any thread context.

        Arguments:
            engine: The CoreEngine instance.
            width: The bit-width of the data signals.
            name: The name prefix for the internal signals (default: 'channel').
        """
        self.engine = engine
        self.width = width

        # FIXME validate if this channel already exists!
        # Maybe turn into named entity

        # All our signals cross the thread boundaries, so we have non-id rw access
        self.ready = Volatile(self.engine.define_local(f'channel_{name}_ready', 1, 0), 'identical_rw')
        self.valid = Volatile(self.engine.define_local(f'channel_{name}_valid', 1, 0), 'identical_rw')
        self.data = Volatile(self.engine.define_local(f'channel_{name}_data', width, 0), 'identical_rw')

    def send(self, data: Renderable | int) -> None:
        """Sends the data over the channel to the target. The execution is blocked until the data has been received.

        Example:
        ```python
        from nortl import Engine

        engine = Engine("my_engine")
        out = engine.define_output("test_output", width=8)
        channel = Channel(engine, width=8, name='my_channel')

        # Send data from one thread to another
        channel.send(42)
        ```

        The send operation follows a classic ready/valid protocol:
        1. The data is written to the channel's data signal
        2. The valid signal is asserted to indicate data is available
        3. The thread waits for the ready signal from the receiver
        4. The valid signal is de-asserted and data is cleared after transfer
        """
        tx_data = to_renderable(data)
        self.engine.set(self.data, tx_data)
        self.engine.set(self.valid, 1)
        self.engine.wait_for(self.ready == 1)
        self.engine.set(self.valid, 0)
        self.engine.set(self.data, 0)
        self.engine.sync()

    def receive(self) -> ScratchSignalProto:
        """Fetches a data item from the channel. The execution is blocked until the data has been received.

        Example:
        ```python
        from nortl import Engine

        engine = Engine("my_engine")
        in_signal = engine.define_input("test_input", width=8)
        channel = Channel(engine, width=8, name='my_channel')

        # Receive data from another thread
        received_data = channel.receive()
        engine.set(in_signal, received_data)
        ```

        The receive operation internally follows a classic ready/valid protocol:
        1. The ready signal is asserted to indicate the receiver is ready
        2. The thread waits for the valid signal from the sender
        3. The data is read from the channel's data signal
        4. The ready signal is de-asserted after transfer
        """
        target = self.engine.define_scratch(self.width)
        self.engine.set(self.ready, 1)
        self.engine.wait_for(self.valid == 1)
        self.engine.set(target, self.data)
        self.engine.set(self.ready, 0)
        self.engine.sync()
        return target


class ElasticChannel:
    """A Channel with a FIFO for rate matching.

    Example:
    ```python
    from nortl import Engine

    engine = Engine("my_engine")
    out = engine.define_output("test_output", width=8)
    channel = ElasticChannel(engine, width=8, name='my_channel', depth=16)

    # Send multiple data items
    channel.send_multiple([1, 2, 3, 4])
    ```
    """

    def __init__(self, engine: EngineProto, width: int, name: str = 'channel', depth: int = 16) -> None:
        """Initializes the ElasticChannel.

        The ElasticChannel implements a FIFO buffer to allow rate matching between producer and consumer threads.
        The FIFO depth must be a power of 2 (2**N) for proper pointer arithmetic.

        Arguments:
            engine: The CoreEngine instance.
            width: The bit-width of the data signals.
            name: The name prefix for the internal signals (default: 'channel').
            depth: The depth of the FIFO buffer (must be 2**N, default: 16).
        """
        ptr_width = math.ceil(math.log2(depth))

        if not ptr_width.is_integer():
            # FIXME this does not work
            raise ValueError('The depth of a FIFO in an ElasticChannel must be 2**N!')

        self.name = name

        self.engine = engine
        self.width = width
        self.depth = depth

        self.read_ptr = Volatile(self.engine.define_local(f'channel_{name}_readctr', ptr_width, 0))
        self.write_ptr = Volatile(self.engine.define_local(f'channel_{name}_writectr', ptr_width, 0))

        self.level = ((Concat('0b0', self.write_ptr) + self.depth) - self.read_ptr) % self.depth

        # Create data store
        self.data: List[Volatile[SignalProto]] = []
        for i in range(depth):
            data_item = Volatile(self.engine.define_local(f'channel_{name}_data_{i}', width, 0))
            self.data.append(data_item)

    def send(self, data: Renderable | int) -> None:
        """Sends the data over the channel to the target. The execution is blocked until the data has been sent.

        Example:
        ```python
        from nortl import Engine

        engine = Engine("my_engine")
        out = engine.define_output("test_output", width=8)
        channel = ElasticChannel(engine, width=8, name='my_channel', depth=16)

        # Send data
        channel.send(42)
        ```

        The send operation checks the FIFO level before writing and waits if the buffer is nearly full.
        The data is written to the appropriate FIFO position based on the write pointer.
        """
        if isinstance(data, int):
            tx_data: Renderable = Const(data, self.width)
        else:
            tx_data = to_renderable(data)

        self.engine.wait_for(self.level < (self.depth - 2))

        for i in range(self.depth):
            self.engine.set(self.data[i], IfThenElse(self.write_ptr == i, tx_data, self.data[i]))

        self.engine.set(self.write_ptr, self.write_ptr + 1)
        self.engine.sync()

    def send_multiple(self, data_lst: List[Renderable | int]) -> None:
        """Sends several data items over the channel to the target. The execution is blocked until the data has been sent.

        Note that the list order is MSB first!

        Example:
        ```python
        from nortl import Engine

        engine = Engine("my_engine")
        out = engine.define_output("test_output", width=8)
        channel = ElasticChannel(engine, width=8, name='my_channel', depth=16)

        # Send multiple data items
        channel.send_multiple([1, 2, 3, 4])
        ```

        The send_multiple operation writes a sequence of items to the FIFO in reverse order
        to maintain the correct MSB-first ordering when read back.
        """
        if (length := len(data_lst)) > self.depth - 2:
            raise RuntimeError('send_multiple expects the item list to be smaller than (Channel.depth - 2)!')

        tx_data: Sequence[Renderable] = tuple(Const(item, self.width) if isinstance(item, int) else to_renderable(item) for item in data_lst)

        self.engine.wait_for(self.level < (self.depth - 1 - length))

        tmp_data: List[Renderable] = [i for i in self.data]

        for j, item in enumerate(tx_data[::-1]):
            for i in range(self.depth):
                tmp_data[i] = IfThenElse(((self.write_ptr + j) % self.depth) == (i), item, tmp_data[i])

        for i in range(self.depth):
            self.engine.set(self.data[i], tmp_data[i])

        self.engine.sync()
        self.engine.set(self.write_ptr, self.write_ptr + length)

        self.engine.sync()

    def receive(self) -> ScratchSignalProto:
        """Fetches a data item from the channel. The execution is blocked until the data has been received.

        Example:
        ```python
        from nortl import Engine

        engine = Engine("my_engine")
        in_signal = engine.define_input("test_input", width=8)
        channel = ElasticChannel(engine, width=8, name='my_channel', depth=16)

        # Receive data
        received_data = channel.receive()
        engine.set(in_signal, received_data)
        ```

        The receive operation reads the oldest data item from the FIFO based on the read pointer.
        """
        target = self.engine.define_scratch(self.width)
        self.engine.wait_for(self.level != 0)

        res: Renderable = Const(0, self.width)

        for i in range(self.depth):
            res = IfThenElse(self.read_ptr == i, self.data[i], res)

        self.engine.set(target, res)
        self.engine.set(self.read_ptr, self.read_ptr + 1)
        self.engine.sync()
        return target
