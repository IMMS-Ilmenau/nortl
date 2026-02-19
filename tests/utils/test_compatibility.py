from nortl.core.checker import StaticAccessChecker
from nortl.core.common import NamedEntity, StaticAccess
from nortl.core.engine import CoreEngine
from nortl.core.manager.scratch_manager import ScratchManager
from nortl.core.manager.signal_manager import SignalManager
from nortl.core.module import Module, ModuleInstance
from nortl.core.operations import Const
from nortl.core.parameter import Parameter
from nortl.core.process import Thread, Worker
from nortl.core.protocols import (
    AssignmentProto,
    ConditionalAssignmentProto,
    EngineProto,
    ModuleInstanceProto,
    ModuleProto,
    NamedEntityProto,
    ParameterProto,
    ScratchManagerProto,
    ScratchSignalProto,
    SelectorAssignmentProto,
    SignalManagerProto,
    SignalProto,
    SignalSliceProto,
    StateProto,
    StaticAccessCheckerProto,
    StaticAccessProto,
    ThreadProto,
    WorkerProto,
)
from nortl.core.signal import ScratchSignal, Signal, SignalSlice
from nortl.core.state import Assignment, ConditionalAssignment, SelectorAssignment, State


def test_protocol_compatibility() -> None:
    """This test is used to debug the protocol<=>class mismatches. No real function, but good debugging."""
    t1: NamedEntityProto = NamedEntity('test')
    t2: ModuleInstanceProto = ModuleInstance(Module('test'), 'Test')
    t3: ModuleProto = Module('test')
    t4: EngineProto = CoreEngine('test')
    t5: StateProto = State(t4.main_worker, 'none')
    t6: SignalProto = Signal(t4, type='local', name='test', width=2)
    t7: SignalSliceProto = SignalSlice(t6, 1)
    t8: ScratchSignalProto = ScratchSignal(t6, 1)
    t9: ParameterProto = Parameter(t4, 'test', default_value=1)
    t10: WorkerProto = Worker(t4, 'test')
    t11: ThreadProto = Thread(t10, 'name')
    t12: StaticAccessProto = StaticAccess(t11)
    t13: StaticAccessCheckerProto = StaticAccessChecker(t6)
    t14: ScratchManagerProto = ScratchManager(t4)
    t15: SignalManagerProto = SignalManager(t4)
    t16: AssignmentProto = Assignment(t6, Const(1))
    t17: ConditionalAssignmentProto = ConditionalAssignment(t6, Const(1), Const(1))
    t18: SelectorAssignmentProto = SelectorAssignment(t6, {t8 == 1: Const(1)})

    del t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11, t12, t13, t14, t15, t16, t17, t18
