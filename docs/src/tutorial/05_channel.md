## Channels

Passing data between parallel threads is a common requirement. noRTL provides two channel implementations that abstract the handshake protocol:

* **Channel:** A simple ready/valid handshake. The sender blocks until the receiver is ready. Ideal for point-to-point communication where strict synchronization is desired.
* **ElasticChannel:** A FIFO-based channel that decouples the sender and receiver speeds. It buffers data internally, allowing the producer to run ahead of the consumer (rate matching). Perfect for streaming data or handling bursty workloads.

## Using a Basic Channel

```python
data_channel = engine.create_channel(width=16, name='sensor_data')
engine.sync()  # Leave reset before fork().

with engine.fork("sensor_reader") as reader:
    # ... read sensor values ...
    data_channel.send(sensor_value)  # Blocks until receiver is ready

# Main thread waits for data and processes it
received_val = data_channel.receive()
engine.set(out, received_val)
```

## Using an Elastic Channel (FIFO)

```python
# Create elastic channel with depth 8. The depth must be 2**N.
fifo_channel = engine.create_elastic_channel(width=16, name='fifo_data', depth=8)
engine.sync()  # Leave reset before fork().

with engine.fork("batch_processor") as batcher:
    # send_multiple stores the list last-element-first (MSB first).
    # This list is received as 100, then 101, then 102.
    fifo_channel.send_multiple([102, 101, 100])

# Main thread consumes items one by one when ready.
# receive() blocks until the FIFO level is non-zero.
item = fifo_channel.receive()
engine.set(out, item)
```

!!! warning

    Both channel types are **blocking** by design, but they do not block on the same condition. `Channel.send` and `Channel.receive` wait until the ready/valid handshake completes. `ElasticChannel.send` waits until `level < depth - 2`, and `ElasticChannel.receive` waits until `level != 0`. Neither call has a non-blocking mode. Poll `Channel.ready`, `Channel.valid`, or `ElasticChannel.level` yourself.
