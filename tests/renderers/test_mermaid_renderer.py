import pytest

from nortl.core.engine import CoreEngine
from nortl.core.operations import Const
from nortl.renderer.mermaid_renderer import MermaidRenderer


def test_empty_engine() -> None:
    """Test that an empty engine renders correctly."""
    engine = CoreEngine('empty_engine')
    renderer = MermaidRenderer(engine)
    rendered_engine = renderer.render()
    assert rendered_engine.startswith('---\ntitle empty_engine\n---\nstateDiagram-v2\n')


def test_engine_with_states() -> None:
    """Test that an engine with states renders correctly."""
    engine = CoreEngine('engine_with_states')
    state1 = engine.create_state('state1')
    state2 = engine.create_state('state2')
    state1._add_transition(Const(True), state2)
    renderer = MermaidRenderer(engine)
    rendered_engine = renderer.render()
    assert 'state1 --> state2' in rendered_engine


def test_engine_with_multiple_transitions() -> None:
    """Test that an engine with multiple transitions renders correctly."""
    engine = CoreEngine('engine_with_multiple_transitions')
    state1 = engine.create_state('state1')
    state2 = engine.create_state('state2')
    state3 = engine.create_state('state3')
    state1._add_transition(Const(True), state2)
    state1._add_transition(Const(True), state3)
    renderer = MermaidRenderer(engine)
    rendered_engine = renderer.render()
    assert 'state1 --> state2' in rendered_engine
    assert 'state1 --> state3' in rendered_engine


def test_engine_with_no_transitions() -> None:
    """Test that an engine with no transitions renders correctly."""
    engine = CoreEngine('engine_with_no_transitions')
    state1 = engine.create_state('state1')  # noqa: F841
    state2 = engine.create_state('state2')  # noqa: F841
    renderer = MermaidRenderer(engine)
    rendered_engine = renderer.render()
    assert 'state1 --> state2' not in rendered_engine


def test_invalid_engine() -> None:
    """Test that an invalid engine raises an exception when rendered.

    The exception occurs because the engine is not properly initialized.
    """
    with pytest.raises(AttributeError):
        renderer = MermaidRenderer(None)  # type: ignore
        renderer.render()


def test_renderer_init() -> None:
    """Test that the MermaidRenderer initializes correctly."""
    engine = CoreEngine('test_engine')
    renderer = MermaidRenderer(engine)
    assert renderer.engine == engine


def test_renderer_render() -> None:
    """Test that the MermaidRenderer renders correctly."""
    engine = CoreEngine('test_engine')
    renderer = MermaidRenderer(engine)
    rendered_engine = renderer.render()
    assert isinstance(rendered_engine, str)


def test_renderer_transitions() -> None:
    """Test that the MermaidRenderer handles transitions correctly."""
    engine = CoreEngine('test_engine')
    state1 = engine.create_state('state1')
    state2 = engine.create_state('state2')
    state1._add_transition(Const(True), state2)
    renderer = MermaidRenderer(engine)
    rendered_engine = renderer.render()
    assert 'state1 --> state2' in rendered_engine
