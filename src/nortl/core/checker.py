from logging import getLogger
from typing import Callable, ClassVar, Dict, List, Literal, Protocol, Set, Type
from warnings import warn

from .exceptions import ExclusiveReadError, ExclusiveWriteError, NonIdenticalRWError
from .protocols import ACCESS_CHECKS, SIGNAL_ACCESS_CHECKS, StaticAccessProto

__all__ = [
    'StaticAccessChecker',
    'set_severity_level',
]

logger = getLogger(__name__)


T_SEVERITY_LEVEL = Literal['raise', 'warn', 'log', 'suppress']


def set_severity_level(level: T_SEVERITY_LEVEL) -> None:
    """Set severity level for noRTL access checks."""
    BaseChecker.severity = level


class AccessControlledSignal(Protocol):
    """Minimal protocol for access controlled signals.

    This supports both real signals and Volatile modifiers.
    """

    @property
    def name(self) -> str: ...

    @property
    def read_accesses(self) -> Set[StaticAccessProto]: ...

    @property
    def write_accesses(self) -> Set[StaticAccessProto]: ...


class BaseChecker:
    """Baseclass for checkers."""

    severity: ClassVar[T_SEVERITY_LEVEL] = 'raise'

    @staticmethod
    def throw(exception_type: Type[Exception], msg: str) -> None:
        """Throw exception."""
        match BaseChecker.severity:
            case 'raise':
                raise exception_type(msg)
            case 'warn':
                warn(msg, stacklevel=2)
            case 'log':
                logger.error(f'[{exception_type.__name__}] {msg}', stacklevel=2, stack_info=True)


class StaticAccessChecker(BaseChecker):
    """Static access checker for signals."""

    # FIXME: Adapt traceback of the checks to show position in the actual user-code where the exception happened

    def __init__(self, signal: AccessControlledSignal) -> None:
        self.signal = signal
        self.enabled_checks: List[SIGNAL_ACCESS_CHECKS] = ['exclusive_read', 'exclusive_write', 'identical_rw']
        self._cached_reading_thread_names: Set[str] = set()
        self._cached_writing_thread_names: Set[str] = set()

        self.check_mapping: Dict[ACCESS_CHECKS, Callable[[], None]] = {
            'exclusive_read': self.check_exclusive_read,
            'exclusive_write': self.check_exclusive_write,
            'identical_rw': self.check_identical_rw,
        }

    @property
    def reading_thread_names(self) -> Set[str]:
        if len(self._cached_reading_thread_names) != 0:
            return self._cached_reading_thread_names

        threadnames: Set[str] = set()
        for access in self.signal.read_accesses:
            if access.active and access.thread.running:
                threadnames.add(f'{access.thread.worker.name}.{access.thread.name}')

        self._cached_reading_thread_names = threadnames

        return threadnames

    @property
    def writing_thread_names(self) -> Set[str]:
        if len(self._cached_writing_thread_names) != 0:
            return self._cached_writing_thread_names

        threadnames: Set[str] = set()
        for access in self.signal.write_accesses:
            if access.active and access.thread.running:
                threadnames.add(f'{access.thread.worker.name}.{access.thread.name}')

        self._cached_writing_thread_names = threadnames

        return threadnames

    def disable_check(self, check: SIGNAL_ACCESS_CHECKS) -> None:
        self.enabled_checks.remove(check)

    def check(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """This function executes all checks and raises errors, if needed."""

        # Clear out caches
        self._cached_reading_thread_names = set()
        self._cached_writing_thread_names = set()

        # Actual Check
        for check in self.enabled_checks:
            if check not in ignore:
                self.check_mapping[check]()

    def check_exclusive_read(self) -> None:
        if len(self.reading_thread_names) > 1:
            self.throw(
                ExclusiveReadError, f'Signal {self.signal} has been read by more than one thread! Reading Threads: {self.reading_thread_names}'
            )

    def check_exclusive_write(self) -> None:
        if len(self.writing_thread_names) > 1:
            self.throw(
                ExclusiveWriteError, f'Signal {self.signal} has been written by more than one thread! Writing Threads: {self.writing_thread_names}'
            )

    def check_identical_rw(self) -> None:
        if len(self.writing_thread_names) == 0 or len(self.reading_thread_names) == 0:
            pass
        elif self.writing_thread_names != self.reading_thread_names:
            self.throw(
                NonIdenticalRWError, f'Signal {self.signal} has been written by {self.writing_thread_names} and read by {self.reading_thread_names}.'
            )
