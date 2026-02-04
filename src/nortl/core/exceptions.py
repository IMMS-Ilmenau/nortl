"""This module defines exception types for noRTL."""

from typing import TypeVar

from nortl.core.protocols import AssignmentTarget, Renderable

__all__ = [
    'AccessAfterReleaseError',
    'ConflictingAssignmentError',
    'ExclusiveReadError',
    'ExclusiveWriteError',
    'ForbiddenAssignmentError',
    'NonIdenticalRWError',
    'OwnershipError',
    'TransitionLockError',
    'TransitionRestrictionError',
    'UnfinishedForwardDeclarationError',
    'WriteViolationError',
    'read_access',
    'write_access',
]


T_Read = TypeVar('T_Read', bound=Renderable)
T_Write = TypeVar('T_Write', bound=AssignmentTarget)


# Access Violation Errors
class AccessViolationError(RuntimeError):
    """Base class for errors caused by invalid read or write access to signals or operation results."""


class ExclusiveReadError(AccessViolationError):
    """This error occurs when a signal is read by more than one thread.

    This error can be suppressed by disabling or ignoring the 'exclusive_read' check for a signal.

    To permanently disable the check, use `signal.acess_checker.disable_check('exclusive_read')`.

    To ignore the check during a read or write access, wrap the signal in a [Volatile][nortl.core.modifiers.Volatile] modifier with
    `Volatile(signal, 'exclusive_read')`.
    """


class ExclusiveWriteError(AccessViolationError):
    """This error occurs when a signal is written by more than one thread.

    This error can be suppressed by disabling or ignoring the 'exclusive_write' check for a signal.

    To permanently disable the check, use `signal.acess_checker.disable_check(''exclusive_write)`.

    To ignore the check during a read or write access, wrap the signal in a [Volatile][nortl.core.modifiers.Volatile] modifier with
    `Volatile(signal, 'exclusive_write')`.
    """


class NonIdenticalRWError(AccessViolationError):
    """This error occurs when a signal is read and written by different threads.

    This error can be suppressed by disabling or ignoring the 'identical_rw' check for a signal.

    To permanently disable the check, use `signal.acess_checker.disable_checkidentical_rw('')`.

    To ignore the check during a read or write access, wrap the signal in a [Volatile][nortl.core.modifiers.Volatile] modifier with
    `Volatile(signal, 'identical_rw')`.
    """


class AccessAfterReleaseError(AccessViolationError):
    """This error occurs when a scratch signal is accessed after being released."""


class WriteViolationError(AccessViolationError):
    """This error occurs when an input signal is written."""


def read_access(object: T_Read) -> T_Read:
    """Perform read access to renderable.

    This helper function hides the traceback caused during recursive read access.
    """
    try:
        object.read_access()
    except AccessViolationError as e:
        raise e.with_traceback(None)
    return object


def write_access(object: T_Write) -> T_Write:
    """Perform write access to signal.

    This helper function hides the traceback caused during recursive write access.
    """
    try:
        object.write_access()
    except AccessViolationError as e:
        raise e.with_traceback(None)
    return object


# Transition Errors
class TransitionError(RuntimeError):
    """Base class for errors related to invalid transitions."""


class TransitionLockError(TransitionError):
    """This error occurs when attempting to add new transitions to a state that has been locked or would need to be locked but cannot."""


class TransitionRestrictionError(TransitionError):
    """This error occurs when attempting to add new transitions to a state that has been restricted to transition to a specific other state."""


# Assignment Errors
class AssignmentError(RuntimeError):
    """Base class for errors related to invalid assignments."""


class ForbiddenAssignmentError(AssignmentError):
    """This error occurs when attempting to add assignments to a state that does not allow it."""


class ConflictingAssignmentError(AssignmentError):
    """This error occurs when attempting to add multiple conflicting assignments to the same signal in one state."""


# Misc. Errors
class OwnershipError(RuntimeError):
    """This error occurs when noRTL instances, that don't belong to the same noRTL Engine are mixed up.

    This can occur when noRTL is used in an interactive context, e.g. a Jupyter notebook.
    """


class UnfinishedForwardDeclarationError(RuntimeError):
    """This error occurs when the worker has a forward-declared state, but the user attempts to switch the current state to a different state.

    This error is meant to prevent dead-ends in the state graph.
    """
