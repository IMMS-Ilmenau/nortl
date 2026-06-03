from abc import ABCMeta, abstractmethod
from typing import Any, ClassVar, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Tuple, Union

from nortl.core.coverage.records import AnyRecord, CoverGroupRecord, CoverPointRecord, EngineReference, InfoRecord
from nortl.core.operations import Const
from nortl.core.protocols import EngineProto, PrintMessageProto
from nortl.core.serialization.engine_info import EngineInfo
from nortl.renderer.verilog_utils.process import Initial, VerilogFunctionCall, VerilogIf
from nortl.renderer.verilog_utils.structural import GuardBlock, VerilogModule
from nortl.renderer.verilog_utils.utils import VerilogRenderable

__all__ = [
    'BasePrintHandler',
    'CoverageWriter',
    'Logger',
    'PrintHandlerProto',
]


class VerilogRendererProto(Protocol):
    engine: EngineProto
    verilog_module: VerilogModule
    synthesis_guard: Optional[Tuple[str, str]]


class PrintHandlerProto(Protocol):
    """Protocol for print handler."""

    def render(self, print_message: PrintMessageProto[Any]) -> VerilogRenderable: ...


def as_assoc_array(obj: Mapping[str, object]) -> str:
    """Render keyword arguments to Verilog associative array."""
    entries = ', '.join(f'"{key}": {to_verilog(value)}' for key, value in obj.items())
    return f"'{{{entries}}}"


def as_array(obj: Iterable[object]) -> str:
    """Render items as Verilog array."""
    entries = ', '.join(f'{to_verilog(value)}' for value in obj)
    return f"'{{{entries}}}"


def to_verilog(obj: object) -> str:
    """Convert object to verilog."""
    match obj:
        case str():
            return f'"{obj}"'
        case bool():
            return "1'b1" if obj else "1'b0"
        case _:
            return f'{obj}'  # Trigger rendering


class BasePrintHandler[T](metaclass=ABCMeta):
    """Baseclass for print handlers."""

    def __init__(self, renderer: VerilogRendererProto) -> None:
        self.renderer = renderer

    @abstractmethod
    def render(self, print_message: PrintMessageProto[T]) -> VerilogRenderable:
        """Render message."""


class Logger(BasePrintHandler[str]):
    """Print handler for logging.

    The logger processes all print statments with the default `'logger'` handler.
    It supports multiple log-levels for information, warnings and errors.

    A matching implementation is found in the [noRTL simulation library][nortl.verilog_library.sim] in `SIM_MODULES['logger']`.
    """

    INSTANCE_NAME: ClassVar[str] = 'logger'
    """Instance name for logger in Verilog."""

    def function_name(self, print_message: PrintMessageProto[str]) -> str:
        """Generate function name for logging a message.

        This method may be overriden, e.g. to rebind the logger to a simpler function (e.g. `$display`).

        Arguments:
            print_message: The print message to log. The logging level is parsed from the `kwargs` of the print.
        """
        return f'{self.INSTANCE_NAME}.{print_message.kwargs.get("level", "info")}'

    def render(self, print_message: PrintMessageProto[str]) -> VerilogRenderable:
        """Render message."""
        if not isinstance(print_message.message, str):
            raise TypeError(f'Logger print handler expects a string message, got {type(print_message.message)}!')

        # Invoke string replacement with $sformatf
        message: Union[VerilogRenderable, str]
        if len(print_message.args) > 0:
            message = VerilogFunctionCall('$sformatf', True, to_verilog(print_message.message), *print_message.args).render()
        else:
            message = to_verilog(print_message.message)

        function_call = VerilogFunctionCall(self.function_name(print_message), False, message)

        if print_message.condition is None or (print_message.condition.is_constant and print_message.condition.value):  # type: ignore[attr-defined]
            return function_call
        else:
            return VerilogIf(print_message.condition, function_call)


class CoverageWriter(BasePrintHandler[AnyRecord]):
    """Print handler for coverage_writer.

    The coverage writer can process coverage records.
    It will automatically insert the emission of an information record into the rendered Verilog.

    A matching implementation is found in the [noRTL simulation library][nortl.verilog_library.sim] in `SIM_MODULES['coverage_writer']`.
    """

    INSTANCE_NAME: ClassVar[str] = 'coverage_writer'
    """Instance name for coverage writer in Verilog."""

    RAW_MODE: ClassVar[bool] = False
    """Enable raw mode. In raw mode, only the write_record() function is used."""

    FUNCTION_NAMES: ClassVar[Mapping[str, str]] = {
        'info': 'emit_info',
        'state': 'emit_state_coverage',
        'transition': 'emit_transition_coverage',
        'coverpoint': 'emit_cover_point',
        'covergroup': 'emit_cover_group',
    }

    def __init__(self, renderer: VerilogRendererProto) -> None:
        super().__init__(renderer)

        self._initialized = False
        self._engine_info: Optional[EngineInfo] = None

    @property
    def engine_info(self) -> EngineInfo:
        """Engine information."""
        if self._engine_info is None:
            self._engine_info = EngineInfo.from_engine(self.renderer.engine)
        return self._engine_info

    def initialize(self) -> None:
        """Initialize coverage emission for the Verilog rendered. Adds an engine information record."""
        if not self._initialized:
            self._initialized = True

            # Emit information record and define cover points and cover groups in an initial block
            initial_block = Initial()

            # Add info record
            # Test information is injected by the coverage_writer itself
            info_record = InfoRecord(type='info', engine=EngineReference.from_engine_info(self.engine_info), test=None)
            initial_block.add(self.create_function_call(info_record, self.renderer.engine.module_name))

            # Add cover groups
            for covergroup in self.renderer.engine.coverage.covergroups.values():
                covergroup_record = CoverGroupRecord.from_covergroup(covergroup)
                initial_block.add(self.create_function_call(covergroup_record, self.renderer.engine.module_name))

            # Define cover points
            for coverpoint in self.renderer.engine.coverage.coverpoints.values():
                coverpoint_record = CoverPointRecord.from_coverpoint(coverpoint, False)
                initial_block.add(self.create_function_call(coverpoint_record, self.renderer.engine.module_name))

            # Wrap initial block in synthesis guard
            if self.renderer.synthesis_guard is not None:
                self.renderer.verilog_module.functionals.append(GuardBlock(*self.renderer.synthesis_guard, initial_block))
            else:
                self.renderer.verilog_module.functionals.append(initial_block)

    def render(self, print_message: PrintMessageProto[AnyRecord]) -> VerilogRenderable:
        """Render message."""
        if 'target' not in print_message.kwargs:
            raise KeyError('Coverage writer requires the coverage target in kwargs!')
        elif not isinstance(coverage_target := print_message.kwargs.get('target'), str):
            raise TypeError(f'Coverage target must be a string, got {type(coverage_target)}!')

        self.initialize()
        function_call = self.create_function_call(print_message.message, coverage_target)

        if print_message.condition is None or (print_message.condition.is_constant and print_message.condition.value):  # type: ignore
            return function_call
        else:
            return VerilogIf(print_message.condition, function_call)

    # Function call
    def create_function_call(self, record: AnyRecord, target: str) -> VerilogFunctionCall:
        """Create Verilog function call for emission of coverage record."""
        if self.RAW_MODE:
            function = f'{self.INSTANCE_NAME}.write_record'
            args: Sequence[Union[str, VerilogRenderable]] = (
                to_verilog(record.model_dump_json().replace('"', r'\"')),
                to_verilog(record.type == 'info'),
            )
            kwargs: Mapping[str, Union[str, VerilogRenderable]] = {}
        else:
            function = self.function_name(record.type)
            args, kwargs = self.build_args(record)

        return VerilogFunctionCall(function, False, to_verilog(target), *args, **kwargs)

    def function_name(self, record_type: str) -> str:
        return f'{self.INSTANCE_NAME}.{self.FUNCTION_NAMES[record_type]}'

    def build_args(self, record: AnyRecord) -> Tuple[Sequence[Union[str, VerilogRenderable]], Mapping[str, Union[str, VerilogRenderable]]]:
        """Build arguments for function call."""

        # Message is used to indicate the record type
        args: List[Union[str, VerilogRenderable]]
        kwargs: Dict[str, Union[str, VerilogRenderable]] = {}
        match record.type:
            case 'info':
                args = [as_assoc_array(record.engine.model_dump())]
                if record.test:
                    args += [as_assoc_array(record.test.model_dump())]
            case 'state':
                args = [to_verilog(record.state), Const(record.covered)]
            case 'transition':
                args = [to_verilog(record.source), to_verilog(record.target), Const(record.covered)]
            case 'coverpoint':
                args = [to_verilog(record.state), to_verilog(record.condition), to_verilog(record.point_name)]
                if record.group_name:
                    kwargs['group_name'] = to_verilog(record.group_name)
                if record.group_coords:
                    kwargs['group_coords'] = as_array(record.group_coords)
                kwargs['covered'] = Const(record.covered)
            case 'covergroup':
                args = [to_verilog(record.name), as_array(record.axis), as_array((as_array(axis_limits) for axis_limits in record.limits))]
        return args, kwargs
