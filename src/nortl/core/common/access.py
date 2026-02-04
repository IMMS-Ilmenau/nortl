from nortl.core.protocols import ThreadProto

from .debug import DebugEntity


class StaticAccess(DebugEntity):
    """Model for an access to a signal.

    This class is used as a container to hold references to the thread that caused the access and information about what caused the access where in the code.
    The signal object can then hold a list (or deque) of accesses for executing checks for e.g. two parallel-running threads accessing the register.

    Note that this does not include checks like access counters that verify,
    that the number of reads is equal to the number of writes so that no data gets lost.
    This structure is only used for detecting concurrent accesses at assemble-time of the noRTL engine (where the code assembles the internal noRTL engine model).
    Realizing access counters is a task to be performed at other levels of abstraction, e.g. in the rendered Verilog code where also formal properties
    can be included for verification in simulation.
    """

    def __init__(self, thread: ThreadProto) -> None:
        super().__init__()
        self.thread = thread
        self.active = True

    def disable(self) -> None:
        self.active = False
