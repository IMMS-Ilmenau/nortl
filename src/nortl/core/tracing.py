"""Tracing for noRTL."""

import inspect
import sys
import tempfile
from contextlib import contextmanager
from inspect import FrameInfo
from pathlib import Path
from time import time
from typing import ClassVar, Iterator, List, Optional, Sequence, Tuple, Union

from .protocols import EngineProto, NamedEntityProto

# Optional import of pyinstrument
try:
    from pyinstrument.low_level.stat_profile_python import get_frame_info
    from pyinstrument.renderers import HTMLRenderer
    from pyinstrument.session import Session as PyinstrumentSession

    PROFILING_AVAILABLE = True

    def build_call_stack(frames: Sequence[FrameInfo]) -> List[str]:
        """Build call stack for pyinstrument."""
        return [get_frame_info(frame.frame) for frame in frames]

except ImportError:
    PROFILING_AVAILABLE = False
    PROFILING_INSTALL_NOTICE = (
        'Please install pyinstrument to enable support for profiling. '
        + 'noRTL defines it as an optional dependency, that can be installed with e.g. \'pip install "nortl[profiling]"\'.'
    )

    # Fallback placeholders
    class PyinstrumentSession:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError(f'Unable to create PyinstrumentSession.\n{PROFILING_INSTALL_NOTICE}')

    def build_call_stack(frames: Sequence[FrameInfo]) -> List[str]:
        return [f'{frame.filename:{frame.lineno}}' for frame in frames]  # Return dummy call stack


__all__ = [
    'Tracer',
    'enable_tracing',
]


# Default boundary: nortl.core.engine.py
DEFAULT_BOUNDARY = str((Path(__file__).parent / 'engine.py'))


@contextmanager
def enable_tracing(lower_boundary: Union[Path, str] = DEFAULT_BOUNDARY) -> Iterator[None]:
    """Enable tracing and configure upper boundary.

    noRTL tracing is disabled by default. It can be enabled by accessing `engine.tracer.enabled`, before creating any states.
    This context manager allows to comfortably enable tracing for a noRTL engine, without having to change anything inside the code creating it.

    Tracing significantly slows down noRTL by a factor of 5 to 10. It should only be enabled if actually needed.

    Example:
        For example, if your noRTL engine is created inside a function `create_engine`, you would need to modify it to enable the tracer.

        Instead, simply use this context manager:

        ```python
        from nortl import enable_tracing

        from my_code import create_engine

        with enable_tracing():
            # Create the engine
            engine = create_engine()

        # Export the trace as a pyinstrument session
        engine.tracer.session.save('my_engine.pyisession')
        ```
    """
    # Turn lower boundary into string
    if isinstance(lower_boundary, Path):
        lower_boundary = str(lower_boundary)  # Format as platform default

    # Determine upper boundary by searching the stack for the invocation of enable_tracing()
    upper_boundary = '<undefined'
    for frame in inspect.stack():
        for line in frame.code_context or ():
            if 'enable_tracing()' in line:
                upper_boundary = frame.filename
                break

    # Update boundaries and temporarily enable tracing
    Tracer.lower_boundary = lower_boundary
    Tracer.upper_boundary = upper_boundary
    Tracer.enabled = True
    yield
    Tracer.enabled = False


class Tracer:
    """NoRTL tracer.

    The tracer can save the current call stack (in a filtered form) into the metadata of objects.
    This helps with debugging where states are created in the noRTL engine.

    The tracer can also collect custom pyinstrument sessions, that can be exported or directly rendered as a flamegraph.
    """

    enabled: ClassVar = False
    """Enables tracing.

    Tracing significantly slows down noRTL by a factor of 5 to 10. It should only be enabled if actually needed.
    """

    lower_boundary: str = DEFAULT_BOUNDARY
    """Lower boundary for the filtered call stack.

    This frame and all frames below are excluded included in the filtered stack trace.

    By default, the call stack stops when it reaches any method in the module `nortl.core.engine`.
    """

    upper_boundary: str = '<undefined>'
    """Upper boundary for the filtered call stack.

    This frame is the first frame that is included in the filtered stack trace.

    Typically the call stack should start, where the noRTL engine is created, but exclude e.g. the "overhead" from a Jupyter server.
    """

    def __init__(self, engine: EngineProto):
        """Initialize a new tracer.

        Arguments:
            engine: noRTL engine for this tracer.
        """
        self._engine = engine
        self._session: Optional['Session'] = self.create_session()

    @property
    def engine(self) -> EngineProto:
        """NoRTL Engine of this tracer."""
        return self._engine

    @property
    def session(self) -> 'Session':
        """Active profiling session."""
        if self._session is None:
            raise RuntimeError('Tracer has no active session.')
        return self._session

    def create_session(self) -> 'Session':
        """Create a profiling session and set it as active session.

        Returns:
            The new profiling session. It is also stored in tracer.session.
        """
        self._session = Session(self, self._create_trace())
        return self._session

    def add_metadata(self, target: NamedEntityProto, key: str, profile: bool = False) -> None:
        """Retrieve current stack trace and add it to the metadata of the target.

        The stack trace will be filtered, to exclude irrelevant information, based on the boundaries of the tracer.
        At the same time, this will append the stack trace to the current session, if `profile` is True.

        Arguments:
            target: Target where the stack trace will be stored.
            key: Metadata key for the stack trace.
            profile: If True, the full stack trace will be appended to the current session.
                This effectively controls, which stack traces are included in the session profile.
                E.g., for states, it is recommended to either profile where states are created, or where the are set as current state, but not both.
        """
        if self.enabled:
            full_frames = self._create_trace()
            frames = self._filter_trace(full_frames)
            target.set_metadata(key, frames)

            if self._session is not None and profile:
                self._session.append(full_frames)

    @property
    def current_trace(self) -> Sequence[FrameInfo]:
        full_frames = self._create_trace()
        frames = self._filter_trace(full_frames)
        return frames

    def format_metadata(self, target: NamedEntityProto, key: str) -> str:
        """Format the stack trace saved in the metadata of a target into a string.

        Arguments:
            target: Target where the stack trace is stored.
            key: Metadata key for the stack trace.

        Returns:
            Descriptive string of the stack trace.
        """

        # TODO nicer representation of the stack trace
        lines: List[str] = []
        lines.append(f'{target.__class__} {target.name} was created at:')

        for i, frame in enumerate(target.get_metadata(key)) or ():
            lines.append(f'[{i}] in {frame.filename}:{frame.lineno}')
            lines.extend(f'{line.lstrip().rstrip()}' for line in frame.code_context or ())
        return '\n'.join(lines)

    # Internals
    def _create_trace(self) -> Sequence[FrameInfo]:
        """Create full stack trace."""
        return tuple(reversed(inspect.stack()))

    def _filter_trace(self, full_frames: Sequence[FrameInfo]) -> Sequence[FrameInfo]:
        """Filter the frames in a full stack trace to exclude both the noRTL internals (lower boundary) and frames above an upper boundary.

        Also marks the frames outside boundaries as hidden for pyinstrument.

        Arguments:
            full_frames: Full frames of stack trace.

        Returns:
            Filtered stack trace, containing only the frames within boundaries.
        """
        frames = []
        hidden = True
        for frame in full_frames:
            if frame.filename.startswith(self.lower_boundary):
                hidden = True
            if frame.filename.startswith(self.upper_boundary):
                hidden = False

            if not hidden:
                frames.append(frame)
            if hidden:
                frame.frame.f_locals['__tracebackhide__'] = True

        return frames


class Session:
    """Tracing session.

    This session stores stack traces and can be exported into a pyinstrument Session.
    """

    def __init__(self, tracer: Tracer, start_call_stack: Sequence[FrameInfo]) -> None:
        """Initialize a new tracing session.

        Arguments:
            tracer: The associated tracer.
            start_call_stack: Starting call stack of the session, created from `reversed(inspect.stack())`.
        """
        self.tracer = tracer
        self.start_call_stack = build_call_stack(start_call_stack)
        self.frame_records: List[Tuple[List[str], float]] = []

    def append(self, frames: Sequence[FrameInfo]) -> None:
        """Append new stack trace to the session.

        Arguments:
            frames: Full frames of stack trace.
        """
        self.frame_records.append((build_call_stack(frames), 1.0))

    def export(self, description: Optional[str] = None) -> PyinstrumentSession:
        """Export frame records as pyinstrument Session object.

        Arguments:
            description: Additional description for the session.
        """
        if not PROFILING_AVAILABLE:
            raise RuntimeError(f'Unable to export Session.\n{PROFILING_INSTALL_NOTICE}')

        target_description = f'Trace for noRTL engine {self.tracer.engine.module_name}'
        if description is not None:
            target_description += f': {description}'

        return PyinstrumentSession(
            frame_records=self.frame_records,
            start_time=time(),
            duration=len(self.frame_records),
            min_interval=0.0,
            max_interval=1.0,
            sample_count=len(self.frame_records),
            start_call_stack=self.start_call_stack,
            target_description=target_description,
            cpu_time=0.0,
            sys_path=sys.path,
            sys_prefixes=PyinstrumentSession.current_sys_prefixes(),
        )

    def save(self, filepath: Union[Path, str], description: Optional[str] = None) -> None:
        """Save frame records as pyinstrument Session object.

        Arguments:
            filepath: The path to save to. Using the .pyisession extension is recommended.
            description: Additional description for the session.

        The session can be loaded and rendered to HTML with:

        ```
        pyinstrument --load <test.pyisession> -r html
        ```
        """
        session = self.export(description=description)
        session.save(filepath)

    def render(self, filepath: Optional[Union[Path, str]] = None, open_in_browser: bool = True, description: Optional[str] = None) -> Optional[Path]:
        """Render frame records as as pyinstrument HTML flamegraph.

        Arguments:
            filepath: The path to save to. Using the .html extension is recommended. If no path is provided, a temporary file created.
            open_in_browser: Directly open the file in browser.
            description: Additional description for the session.

        Returns:
            Filepath to the HTML file, if it wasn't directly openend in the browser.
        """
        session = self.export(description=description)
        renderer = HTMLRenderer()

        if open_in_browser:
            if filepath is not None:
                filepath = str(filepath)
            renderer.open_in_browser(session, output_filename=filepath)
            return None
        elif filepath is None:
            filepath = Path(tempfile.NamedTemporaryFile(suffix='.html', delete=False))
        else:
            filepath = Path(filepath)

        with open(filepath, 'w', encoding='utf8') as file:
            file.write(renderer.render(session))

        return filepath
