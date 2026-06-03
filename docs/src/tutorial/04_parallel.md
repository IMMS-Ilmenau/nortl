# Parallel Behavior

In hardware, parallelism is the norm. While our sequential Python code *looks* like software, noRTL compiles it into a state machine. But what if you actually want true parallel execution? noRTL provides a `Worker` and `Thread` abstraction that maps closely to hardware threads or processing cores. Each `Worker` runs its own independent state machine, and `Thread`s manage signal ownership to prevent race conditions. Once you start a new thread, noRTL checks for a free worker and creates a new worker if no worker is currently available

## Fork & Join

To start a parallel process, you use the `Fork` context manager. It automatically allocates a new worker (or reuses an idle one) and creates a thread for your logic. The main thread continues running while the spawned thread executes in parallel.

```python
from nortl import Engine
from nortl.components.channel import Channel

engine = Engine("ParallelDemo")
out = engine.define_output("RESULT", 16)

# Spawn a parallel thread
with engine.fork("data_processor") as proc_thread:
    # This code runs in parallel with the main thread
    engine.sync()

# Main thread continues here while 'proc_thread' is still running
engine.sync()

# Wait for the parallel thread to finish and clean up resources
proc_thread.join()
engine.set(out, 1)
```

The `join()` method blocks the main thread until the spawned thread completes. Threads can also be explicitly finished or cancelled:

* `thread.join()`: Waits until the thread's worker returns to its idle state. Automatically releases scratch signals and frees signal access rights.
* `thread.cancel()`: Sends a synchronous reset to the thread's worker, forcibly stopping it and recursively cancelling any child threads.
* `thread.finish()`: Explicitly terminates the thread's current execution path.

noRTL supports nested fork/join structures. In this case, it will allocate the necessary workers automatically. Also the `cancel()` and `join()` functions will handle the interaction with child threads of the currently running thread.

## Access Checks & Signal Ownership

In hardware, signals are shared resources. When multiple threads or workers run in parallel, they might try to read or write the same signal at the same time. Unlike software, hardware doesn't have built-in thread locks, so race conditions can easily corrupt your design. noRTL solves this by implementing **static access checks** that track which thread last accessed a signal.

Every time you read or write a signal, noRTL records the current thread. If another thread tries to access that signal without the first thread having finished, noRTL will raise a clear error:

* `ExclusiveWriteError`: Two threads are trying to drive the same signal simultaneously.
* `NonIdenticalRWError`: One thread is writing while another is reading, creating a potential race condition.
* `ExclusiveReadError`: Multiple threads are reading the same signal concurrently (often a sign of unintended sharing).

These checks act as a safety net during development, ensuring your parallel logic is deterministic before you synthesize it.

## Automatic Ownership Transfer
Manually managing signal ownership would be tedious. Instead, noRTL automatically handles access rights when you use the `Fork` context manager and thread lifecycle methods.

When you **start a new thread** with `engine.fork()`, noRTL automatically releases the signal access rights of the spawning thread. This tells the engine: *"The main thread is done with these signals for now; the new thread has ownership."* This prevents false-positive race condition errors during the parallel execution phase.

Conversely, when a thread **ends** (via `thread.join()` or `thread.finish()`), noRTL automatically frees its access rights. This allows the main thread (or other waiting threads) to safely read or write those signals again.

Here's how it looks in practice:

```python
shared_data = engine.define_local("SHARED_DATA", 16)

with engine.fork("processor") as worker:
    # Ownership automatically transfers to 'worker'
    engine.set(shared_data, 42)
    engine.sync()

# Main thread continues here. The forked thread is still running.
engine.sync()

# Wait for the worker to finish and release its access rights
worker.join()

# Now it's safe for the main thread to read the result
engine.set(out, shared_data)
```

This automatic ownership model means you can focus on designing your parallel logic without worrying about manual locking or signal arbitration. If you do need explicit control over access rights (for advanced use cases), you can manually call `engine.signal_manager.free_accesses_from_thread(thread)`, but in most cases, the context managers handle everything for you.

## Deactivation of Access Checks

!!! warning
    Only deactivate checks if you really know what you are doing.

While static access checks are crucial for preventing race conditions and ensuring deterministic hardware behavior, there are legitimate cases where you need to relax these rules. For example, when implementing communication channels, shared lookup tables, or control signals that are safely read by multiple threads in a coordinated manner. noRTL provides two primary ways to handle these scenarios:

## Using the Access Checker

Every signal carries an internal `StaticAccessChecker` that tracks read and write ownership. You can manually override or clear these checks when you are certain that concurrent access is safe. The engine provides a convenient method to free access rights for a specific thread, which is automatically used during `fork` and `join` operations:

```python
# Manually free access rights from a specific thread
engine.signal_manager.free_accesses_from_thread(my_thread)
```

Alternatively, you can disable checks on a per-signal basis if you are managing complex ownership transfers. This approach gives you explicit control over the lifecycle of access rights but requires careful tracking of thread states to avoid silent race conditions.

## Using `Volatile`

For signals that are intentionally shared across multiple threads or workers, noRTL provides the `Volatile` wrapper. Wrapping a signal with `Volatile` tells the access checker to relax its strict ownership rules for that specific instance. You can specify the desired access policy during initialization:

```python
from nortl import Volatile

# Create a signal that allows shared read/write access across threads
shared_reg = Volatile(
    engine.define_local("SHARED_REG", 8, reset_value=0)
)
```

!!! note
    Using `Volatile` does not magically make your hardware race-condition-free. It only disables the *static* checks performed by noRTL during code generation. You are still responsible for ensuring that the underlying hardware logic (e.g., using handshakes, FIFOs, or arbitration) prevents actual data corruption. For most communication needs, prefer the provided `Channel` and `ElasticChannel` classes, which handle synchronization safely under the hood.
