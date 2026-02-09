from types import TracebackType
from typing import List

from nortl.core.constructs import Condition
from nortl.core.protocols import EngineProto, ThreadProto, WorkerProto

__all__ = [
    'Fork',
]


class Fork:
    """Context manager to realize a Fork."""

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

        free_workers: List[WorkerProto] = [w for w in self.engine.workers.values() if not w.working]

        if free_workers == []:
            self.assigned_worker = self.engine.create_worker()
        else:
            self.assigned_worker = free_workers[0]

        self.new_thread = self.assigned_worker.create_thread(self.threadname)

        self.engine.current_worker = self.assigned_worker

    def __enter__(self) -> ThreadProto:
        """Create a new thread and integrate it into next free worker (or create a new worker)."""

        self.engine.current_state = self.assigned_worker.reset_state

        select_id = len(self.assigned_worker.threads)

        condition = Condition(self.engine, self.assigned_worker.start & (self.assigned_worker.select == select_id))

        with condition:
            state_within_condition = self.engine.current_state
            state_within_condition.set_metadata('Fork Select ID', select_id)
            self.engine.set(self.assigned_worker.idle, 0)

        for worker in self.engine.workers.values():
            if worker is self.checkpoint_worker:
                spawning_worker = worker

        spawning_thread = spawning_worker.threads[-1]
        spawning_thread._spawned_threads.append(self.new_thread)

        # Adjust signal accesses
        self.engine.signal_manager.free_accesses_from_thread(spawning_thread)
        self.engine.scratch_manager.free_accesses_from_thread(spawning_thread)

        self.engine.current_state = state_within_condition

        self.engine.sync()

        self.new_thread.active = True

        return self.new_thread

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.engine.sync()
        self.new_thread.finish()

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
