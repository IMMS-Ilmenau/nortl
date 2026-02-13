from nortl import Engine


def test_scratch_release_after_condition_context() -> None:
    """Test that a scratch signal created in a Condition context is released after exiting."""
    engine = Engine('my_engine')
    out = engine.define_output('out', 4, 0)

    with engine.condition(out == 0):
        test = engine.define_scratch(4)
        engine.set(test, 1)

    # The scratch signal should be released after exiting the context
    assert test.released, 'Scratch signal should be released after exiting Condition context'


def test_scratch_release_after_scratch_context() -> None:
    """Test that a scratch signal created in a context is released after exiting."""
    engine = Engine('my_engine')
    engine.sync()

    with engine.context():
        test = engine.define_scratch(4)
        engine.set(test, 1)

    # The scratch signal should be released after exiting the context
    assert test.released, 'Scratch signal should be released after exiting context'


def test_scratch_release_after_else_condition_context() -> None:
    """Test that a scratch signal created in an ElseCondition context is released after exiting."""
    engine = Engine('my_engine')
    out = engine.define_output('out', 4, 0)

    with engine.condition(out == 0):
        engine.set(out, 1)
    with engine.else_condition():
        test = engine.define_scratch(4)
        engine.set(test, 1)

    # The scratch signal should be released after exiting the ElseCondition context
    assert test.released, 'Scratch signal should be released after exiting ElseCondition context'


def test_scratch_release_nested_contexts() -> None:
    """Test that scratch signals in nested contexts are properly released."""
    engine = Engine('my_engine')
    out = engine.define_output('out', 4, 0)

    with engine.condition(out == 0):
        with engine.condition(out == 1):
            test = engine.define_scratch(4)
            engine.set(test, 1)

    # The scratch signal should be released after exiting both nested contexts
    assert test.released, 'Scratch signal should be released after exiting nested Condition contexts'


def test_scratch_manual_release_in_context() -> None:
    """Test that manual release works correctly within the same context."""
    engine = Engine('my_engine')
    out = engine.define_output('out', 4, 0)

    with engine.condition(out == 0):
        test = engine.define_scratch(4)
        engine.set(test, 1)
        test.release()

    # The scratch signal should be manually released
    assert test.released, 'Scratch signal should be manually released'


def test_scratch_not_released_outside_context() -> None:
    """Test that a scratch signal created outside a context is not released when exiting the context."""
    engine = Engine('my_engine')
    out = engine.define_output('out', 4, 0)
    engine.sync()

    test = engine.define_scratch(4)
    engine.set(test, 1)

    with engine.condition(out == 0):
        pass

    # The scratch signal should NOT be released because it was created outside the context
    assert not test.released, "Scratch signal should not be released when exiting a context it wasn't created in"


def test_scratch_context_counter_value() -> None:
    """Test that the context counter is correctly incremented and decremented."""
    engine = Engine('my_engine')
    out = engine.define_output('out', 4, 0)
    engine.sync()

    # Create scratch signal outside context - counter should be 0
    test = engine.define_scratch(4)
    assert test._context_ctr == 0, 'Scratch signal created outside context should have counter 0'

    with engine.condition(out == 0):
        # Inside context - counter should be 1
        assert test._context_ctr == 1, 'Scratch signal inside context should have counter 1'

    # After exiting - counter should be 0 (but not released because it was created outside)
    assert test._context_ctr == 0, 'Scratch signal counter should return to 0 after exiting context'


def test_scratch_release_in_forked_thread() -> None:
    """Test that scratch signals work correctly in forked threads."""
    engine = Engine('my_engine')
    engine.sync()

    # In forked thread, the scratch signal should not be released
    with engine.fork('f1') as f1:
        test = engine.define_scratch(4)
        engine.set(test, 1)
        assert not test.released, 'Scratch signal should not be released in forked thread'

    f1.cancel()

    # After thread ends, the scratch signal should be released
    assert test.released, 'Scratch signal should be released after forked thread ends'
