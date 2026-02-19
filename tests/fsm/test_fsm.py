import pytest

from nortl.core.engine import CoreEngine
from nortl.core.exceptions import ConflictingAssignmentError, WriteViolationError
from nortl.core.module import Module
from nortl.core.operations import All, Any, Const, Var
from nortl.core.signal import Signal
from nortl.core.state import SelectorAssignment


def test_engine_setup() -> None:
    """Test that the engine class can be initialized correctly."""
    engine = CoreEngine('my_engine')
    assert engine.module_name == 'my_engine'


def test_engine_define_input() -> None:
    """Test that an input signal can be defined correctly."""
    engine = CoreEngine('my_engine')
    input_signal = engine.define_input('input_signal')
    assert isinstance(input_signal, Signal)
    assert input_signal.name == 'input_signal'


def test_engine_define_output() -> None:
    """Test that an output signal can be defined correctly."""
    engine = CoreEngine('my_engine')
    output_signal = engine.define_output('output_signal', reset_value=1)
    assert isinstance(output_signal, Signal)
    assert output_signal.name == 'output_signal'


def test_engine_define_local() -> None:
    """Test that a local signal can be defined correctly."""
    engine = CoreEngine('my_engine')
    local_signal = engine.define_local('local_signal')
    assert isinstance(local_signal, Signal)
    assert local_signal.name == 'local_signal'


def test_engine_set_output_invalid_type() -> None:
    """Test that setting an output signal with an invalid type raises a TypeError."""
    engine = CoreEngine('my_engine')
    output_signal = engine.define_output('output_signal', reset_value=1)
    with pytest.raises(TypeError):
        engine.set(output_signal, 'invalid_type')  # type: ignore


def test_engine_set_output_invalid_signal() -> None:
    """Test that setting an output signal with an invalid signal raises a ValueError.

    The exception occurs because the signal is not a Signal instance.
    """
    engine = CoreEngine('my_engine')
    with pytest.raises(TypeError):
        engine.set('invalid_signal', 0)  # type: ignore


def test_engine_set_input_signal() -> None:
    """Test that setting an input signal with an vale raises an WriteViolationError."""
    engine = CoreEngine('my_engine')
    input_signal = engine.define_input('input_signal')
    with pytest.raises(WriteViolationError):
        engine.set(input_signal, 1)


def test_engine_set_combinational_signal() -> None:
    """Test that setting an combinational signal with an vale raises an WriteViolationError."""
    engine = CoreEngine('my_engine')
    word = engine.define_input('word', width=16)
    lsb = engine.define_local('lsb', value=word[7:0])
    with pytest.raises(WriteViolationError):
        engine.set(lsb, 1)


def test_engine_set_output_invalid_value() -> None:
    """Test that setting an output signal with an invalid value raises a TypeError."""
    engine = CoreEngine('my_engine')
    output_signal = engine.define_output('output_signal', reset_value=1)
    with pytest.raises(TypeError):
        engine.set(output_signal, 'invalid_type')  # type: ignore


def test_engine_set_output_multiple_assignments() -> None:
    """Test that setting an output signal with multiple conflicting assignments in the same cycle raises a ConflictingAssignmentError."""
    engine = CoreEngine('my_engine')
    output_signal = engine.define_output('output_signal', reset_value=0)

    # The reset state already contains an assignment to output_signal, that must not be overwritten
    with pytest.raises(ConflictingAssignmentError):
        engine.set(output_signal, 1)
    engine.sync()  # After sync, the signal can be set again

    # Similarily, set_once() will add an assignment output_signal = 0 in the next_state
    engine.set_once(output_signal, 1)
    engine.sync()
    with pytest.raises(ConflictingAssignmentError):
        engine.set(output_signal, 1)
    engine.sync()

    # Multiple assignments are allowed, if they result in the same value
    engine.set(output_signal, 0)
    engine.set(output_signal, 0)


def test_engine_set_output_multiple_assignments_slice() -> None:
    """Test that setting an output signal with any combination of slices and full signals in the same cycle raises a ConflictingAssignmentError."""
    engine = CoreEngine('my_engine')
    output_signal = engine.define_output('output_signal', width=3, reset_value=0)

    # Setting the entire signal with the same value multiple times is allowed
    engine.set(output_signal, 0)

    # Setting a different value is not allowed
    with pytest.raises(ConflictingAssignmentError):
        engine.set(output_signal, 3)

    # Setting a slice of the signal is not allowed, even if it is the same value
    with pytest.raises(ConflictingAssignmentError):
        engine.set(output_signal[0], 0)
    with pytest.raises(ConflictingAssignmentError):
        engine.set(output_signal[2:0], 0)

    engine.sync()

    # Different parts of the slice can be set
    engine.set(output_signal[0], 1)
    engine.set(output_signal[1], 0)
    engine.set(output_signal[2], 1)

    # Partially overlapping assignments are not supported
    with pytest.raises(ConflictingAssignmentError):
        engine.set(output_signal[1:0], 1)
    engine.sync()

    # Mix of slice and single value is supported, as long as they don't overlap
    engine.set(output_signal[0], 1)
    engine.set(output_signal[2:1], 1)

    # Slice indexes are treates as inclusive, so index [0:0] is the same as index [0]
    engine.set(output_signal[0:0], 1)

    # Despite being very bad practice, reversed indexes are supported to
    engine.set(output_signal[1:2], 1)


def test_engine_set_output_multiple_assignments_variable_slice() -> None:
    """Test that setting an output signal with variable width with any combination of slices and full signals in the same cycle raises a ConflictingAssignmentError."""
    engine = CoreEngine('my_engine')
    # Actual value of the width doesn't matter
    scratch_pad = engine.define_output('scratch_pad', width=Var(1), reset_value=0)

    # Setting the entire signal with the same value multiple times is allowed
    engine.set(scratch_pad, 0)

    # Setting a different value is not allowed
    with pytest.raises(ConflictingAssignmentError):
        engine.set(scratch_pad, 3)

    # Setting a slice of the signal is not allowed, even if it is the same value
    with pytest.raises(ConflictingAssignmentError):
        engine.set(scratch_pad[0], 0)
    with pytest.raises(ConflictingAssignmentError):
        engine.set(scratch_pad[2:0], 0)

    engine.sync()

    # Different parts of the slice can be set
    engine.set(scratch_pad[0], 1)
    engine.set(scratch_pad[1], 0)
    engine.set(scratch_pad[2], 1)

    # Partially overlapping assignments are not supported
    with pytest.raises(ConflictingAssignmentError):
        engine.set(scratch_pad[1:0], 1)
    engine.sync()

    # Mix of slice and single value is supported, as long as they don't overlap
    engine.set(scratch_pad[0], 1)
    engine.set(scratch_pad[2:1], 1)

    # Slice indexes are treates as inclusive, so index [0:0] is the same as index [0]
    engine.set(scratch_pad[0:0], 1)

    # Despite being very bad practice, reversed indexes are supported to
    engine.set(scratch_pad[1:2], 1)


def test_engine_set_when() -> None:
    """Test that the set_when method can be used correctly."""
    engine = CoreEngine('my_engine')

    ao22 = engine.define_output('ao22', reset_value=0)
    a = engine.define_input('a')
    b = engine.define_input('b')
    c = engine.define_input('c')
    d = engine.define_input('d')
    engine.sync()

    # emulate 2x2-Input AND into 2-Input OR
    engine.set_when(
        ao22,
        {
            (a & b): 1,
            (c & d): 1,
            'default': 0,
        },
    )

    assert len(engine.current_state.assignments) == 1
    assert isinstance(engine.current_state.assignments[0], SelectorAssignment)
    assert len(engine.current_state.assignments[0].cases) == 2
    assert engine.current_state.assignments[0].priority  #  Default is provided
    assert engine.current_state.assignments[0].default.render() == '0'  # type: ignore[union-attr]


def test_engine_set_when_nested() -> None:
    """Test that the set_when method can be used correctly for nested selectors."""
    engine = CoreEngine('my_engine')

    mux4 = engine.define_output('mux4', reset_value=0)
    sel0 = engine.define_input('sel0')
    sel1 = engine.define_input('sel1')
    a = engine.define_input('a')
    b = engine.define_input('b')
    c = engine.define_input('c')
    d = engine.define_input('d')
    engine.sync()

    # emulate 4:1 MUX
    engine.set_when(
        mux4,
        {
            ~sel1: {
                ~sel0: a,
                sel0: b,
            },
            # One of the cases could use a default instead
            sel1: {
                ~sel0: c,
                sel0: d,
            },
        },
    )

    assert len(engine.current_state.assignments) == 1
    assert isinstance(engine.current_state.assignments[0], SelectorAssignment)
    assert len(engine.current_state.assignments[0].cases) == 2
    assert not engine.current_state.assignments[0].priority  #  Default is not provided
    assert engine.current_state.assignments[0].default is None


def test_engine_set_when_short_circuit() -> None:
    """Test short correct circuiting behavior in selectors."""
    engine = CoreEngine('my_engine')

    sig = engine.define_output('sig', reset_value=0)
    sel0 = engine.define_input('sel0')
    sel1 = engine.define_input('sel1')
    const0 = Const('0b0')
    const1 = Const('0b1')
    engine.sync()

    # If a condition of the selector evaluates to constant False, it is filtered out
    # Note: The All is not necessary here at all, but demonstrates how a constant-False value may propagate into the condition, e.g. from a constant
    # parameter of the system
    engine.set_when(sig, {sel0: 1, All(const0, sel1): 1})
    assert isinstance(engine.current_state.assignments[0], SelectorAssignment)
    assert len(engine.current_state.assignments[0].cases) == 1
    engine.sync()

    # If a condition of the selector evaluates to constant True, the behavior depends.
    # If the selector does not appear to be priority encoded, due to missing 'default', it throws an exception:
    with pytest.raises(RuntimeError):
        engine.set_when(sig, {sel0: 1, Any(const1, sel1): 1})

    # The short circuiting must be explicitely allowed.
    # Note: the assignment still stays an selector assignment, despite having just one case
    engine.set_when(sig, {sel0: 1, Any(const1, sel1): 1}, allow_short_circuit=True)
    assert isinstance(engine.current_state.assignments[0], SelectorAssignment)
    assert len(engine.current_state.assignments[0].cases) == 1
    assert engine.current_state.assignments[0].cases[0][0].is_constant
    assert engine.current_state.assignments[0].cases[0][0].value == 1  # type: ignore[attr-defined]
    engine.sync()

    # Alternatively, if the selector has a priority, the always True condition will override all following conditions and becomes the default
    engine.set_when(sig, {All(~sel0, ~sel1): 1, Any(const1, sel1): 1, sel0: 0, 'default': 0})
    assert isinstance(engine.current_state.assignments[0], SelectorAssignment)
    assert len(engine.current_state.assignments[0].cases) == 1  # Only one case of the 3 left over
    assert not engine.current_state.assignments[0].cases[0][0].is_constant
    assert engine.current_state.assignments[0].default.is_constant  # type: ignore
    assert engine.current_state.assignments[0].default.value == 1  # Note how the default is no longer 1


def test_engine_wait_for() -> None:
    """Test that the wait_for method can be used correctly."""
    engine = CoreEngine('my_engine')
    event_signal = engine.define_input('input_signal')
    engine.wait_for(event_signal)


def test_engine_wait_for_invalid_condition() -> None:
    """Test that the wait_for method with an invalid condition raises a ValueError.

    The exception occurs because the condition is not a Renderable instance.
    """
    engine = CoreEngine('my_engine')
    with pytest.raises(ValueError):
        engine.wait_for('invalid_condition')  # type: ignore


def test_engine_jump_if() -> None:
    """Test that the jump_if method can be used correctly."""
    engine = CoreEngine('my_engine')
    event_signal = engine.define_input('input_signal')
    engine.jump_if(event_signal, engine.next_state)


def test_engine_jump_if_invalid_condition() -> None:
    """Test that the jump_if method with an invalid condition raises a ValueError.

    The exception occurs because the condition is not a Renderable instance.
    """
    engine = CoreEngine('my_engine')
    with pytest.raises(ValueError):
        engine.jump_if('invalid_condition', engine.next_state)  # type: ignore


def test_engine_sync() -> None:
    """Test that the sync method can be used correctly."""
    engine = CoreEngine('my_engine')
    engine.sync()


def test_engine_define_module() -> None:
    """Test that a module can be defined correctly."""
    engine = CoreEngine('my_engine')
    module = engine.define_module('my_module')
    assert module.name == 'my_module'


def test_engine_add_module() -> None:
    """Test that a module can be added correctly."""
    engine = CoreEngine('my_engine')
    module = Module('my_module')
    engine.add_module(module)
    assert module.name in engine.modules


def test_engine_create_module_instance() -> None:
    """Test that a module instance can be created correctly."""
    engine = CoreEngine('my_engine')
    module = engine.define_module('my_module')  # noqa: F841
    instance = engine.create_module_instance('my_module', 'my_instance')
    assert instance.name == 'my_instance'


def test_engine_connect_module_port() -> None:
    """Test that a module port can be connected correctly."""
    engine = CoreEngine('my_engine')
    module = engine.define_module('my_module')
    instance = engine.create_module_instance('my_module', 'my_instance')  # noqa: F841
    module.add_port('port_signal')
    signal = engine.define_input('input_signal')
    engine.connect_module_port('my_instance', 'port_signal', signal)


def test_engine_override_module_parameter() -> None:
    """Test that a module parameter can be overridden correctly."""
    engine = CoreEngine('my_engine')
    module = engine.define_module('my_module')
    module.add_parameter('parameter_name', 1)
    instance = engine.create_module_instance('my_module', 'my_instance')
    engine.override_module_parameter('my_instance', 'parameter_name', 2)
    assert instance.parameter_overrides['parameter_name'] == 2


def test_engine_jump_if_invalid_target() -> None:
    """Test that the jump_if method with an invalid target raises a TypeError."""
    engine = CoreEngine('my_engine')
    event_signal = engine.define_input('input_signal')
    with pytest.raises(ValueError):
        engine.jump_if(event_signal, 'invalid_target')  # type: ignore

    with pytest.raises(ValueError):
        engine.jump_if(event_signal, engine.reset_state, 'invalid_target')  # type: ignore


def test_engine_connect_module_port_invalid_instance() -> None:
    """Test that connecting a module port with an invalid instance raises a ValueError."""
    engine = CoreEngine('my_engine')
    signal = engine.define_input('input_signal')
    with pytest.raises(KeyError):
        engine.connect_module_port('invalid_instance', 'port_signal', signal)


def test_engine_connect_module_port_invalid_port() -> None:
    """Test that connecting a module port with an invalid port raises a ValueError."""
    engine = CoreEngine('my_engine')
    _ = engine.define_module('my_module')
    _ = engine.create_module_instance('my_module', 'my_instance')
    signal = engine.define_input('input_signal')
    with pytest.raises(ValueError):
        engine.connect_module_port('my_instance', 'invalid_port', signal)


def test_engine_set_slice() -> None:
    """Tests that signal slicing can be set."""
    engine = CoreEngine('my_engine')
    output = engine.define_output('OUT', width=8)
    engine.sync()

    # Set entire signal
    engine.set(output, 0xFF)
    engine.sync()

    # Set individual bits
    engine.set(output[0], 0)
    engine.set(output[7], 0)
    engine.sync()

    # Set slice
    engine.set(output[3:0], 0b1010)
