## Channels

Passing data between parallel threads is a common requirement. noRTL provides two channel implementations that abstract the handshake protocol:

* **Channel:** A simple ready/valid handshake. The sender blocks until the receiver is ready. Ideal for point-to-point communication where strict synchronization is desired.
* **ElasticChannel:** A FIFO-based channel that decouples the sender and receiver speeds. It buffers data internally, allowing the producer to run ahead of the consumer (rate matching). Perfect for streaming data or handling bursty workloads.

## Using a Basic Channel

```python
data_channel = engine.create_channel(width=16, name='sensor_data')

with engine.fork("sensor_reader") as reader:
    # ... read sensor values ...
    data_channel.send(sensor_value)  # Blocks until receiver is ready

# Main thread waits for data and processes it
received_val = data_channel.receive()
engine.set(out, received_val)
```

## Using an Elastic Channel (FIFO)

```python
fifo_channel = engine.create_elastic_channel(width=16, name='fifo_data', depth=8)

with engine.fork("batch_processor") as batcher:
    # Can push multiple items without waiting for the main thread
    # The FIFO buffers them automatically
    fifo_channel.send_multiple([100, 101, 102])

# Main thread consumes items one by one when ready
item = fifo_channel.receive()
engine.set(out, item)
```

!!! warning

    Both channel types are **blocking** by design. `send()` and `receive()` will advance the state machine and wait until the handshake completes. If you need non-blocking behavior, you'll need to implement conditional checks (`engine.wait_for()`) around the channel calls or build a custom state machine that polls the channel status.
