from types import TracebackType
from typing import List

from nortl.core.protocols import EngineProto, ThreadProto, WorkerProto

__all__ = [
    'Fork',
]


class Fork:
    """Context manager to realize a fork-join parallelism pattern within a noRTL engine.

    Its intention is to spawn a new thread that runs concurrently with the main thread.
    The fork creates a new worker (if no free worker is available) and a new thread within that worker.

    Example:
    ```python
    engine = Engine("my_engine")
    out = engine.define_output("test_output", width=8)

    with engine.fork("spawned_thread") as spawned_thread:
        # Code that should run in parallel
        engine.set(out, 42)
        engine.sync()

    # After the fork, the main thread continues while the spawned process is running.
    engine.sync()

    # Join the spawned thread to wait for its completion
    spawned_thread.join()
    ```

    The context manager handles the state transitions and worker allocation for the spawned thread.
    It also manages the signal access permissions to ensure proper synchronization between the
    spawning and spawned threads.

    Arguments:
        engine: The CoreEngine instance.
        threadname: Name of the new thread, optional
    """

    def __init__(self, engine: EngineProto, threadname: str):
        """Initializes the Fork context manager.

        Arguments:
            engine: The CoreEngine instance.
            threadname: Name of the new thread, optional
        """
        self.engine = engine
        self.threadname = threadname

        self.checkpoint_worker = self.engine.current_worker
        self.checkpoint_state = self.engine.current_state
        self.assigned_worker: WorkerProto
        self.assigned_thread: ThreadProto

    def _allocate_worker(self) -> None:
        """Allocate a worker and create thread."""
        free_workers: List[WorkerProto] = [w for w in self.engine.workers.values() if not w.working]

        if free_workers == []:
            self.assigned_worker = self.engine.create_worker()
        else:
            self.assigned_worker = free_workers[0]

        self.assigned_thread = self.assigned_worker.create_thread(self.threadname)

    def __enter__(self) -> ThreadProto:
        """Create a new thread and integrate it into next free worker (or create a new worker)."""
        self._allocate_worker()

        # Switch to worker + state
        self.engine.current_worker = self.assigned_worker
        self.engine.current_state = self.assigned_worker.reset_state

        select_id = len(self.assigned_worker.threads)

        # Create start transition from worker idle into fork body
        self.engine.jump_if(self.assigned_worker.start & (self.assigned_worker.select == select_id), self.engine.next_state)
        self.engine.current_state = self.engine.next_state

        self.engine.set(self.assigned_worker.idle, 0)

        for worker in self.engine.workers.values():
            if worker is self.checkpoint_worker:
                spawning_worker = worker

        spawning_thread = spawning_worker.threads[-1]
        spawning_thread._spawned_threads.append(self.assigned_thread)

        # Adjust signal accesses
        self.engine.signal_manager.free_accesses_from_thread(spawning_thread)
        self.engine.scratch_manager.free_accesses_from_thread(spawning_thread)

        # Add metadata
        self.engine.current_state.set_metadata('Fork Select ID', select_id)

        self.engine.sync()

        self.assigned_thread.active = True

        return self.assigned_thread

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # Finalize fork body
        self.engine.sync()
        self.assigned_thread.finish()

        # Return to old worker + state
        self.engine.current_worker = self.checkpoint_worker
        self.engine.current_state = self.checkpoint_state

        thread_id = len(self.assigned_worker.threads)

        # Now the thread has been rendered and so we start the Worker!
        self.engine.set(self.assigned_worker.start, 1)
        self.engine.set(self.assigned_worker.select, thread_id)

        # Inform the state via metadata that it actually started a thread
        metadata = (self.assigned_worker.name, thread_id)
        if self.engine.current_state.has_metadata('Forked Processes'):
            old_data = self.engine.current_state.get_metadata('Forked Processes')
            self.engine.current_state.set_metadata('Forked Processes', old_data.append(metadata))
        else:
            self.engine.current_state.set_metadata('Forked Processes', [metadata])

        self.engine.sync()
