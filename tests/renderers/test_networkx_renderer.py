import networkx as nx
import pytest

from nortl.core.engine import CoreEngine
from nortl.core.operations import Const
from nortl.renderer.networkx_renderer import NetworkXRenderer


def test_networkx_renderer_setup() -> None:
    """Test that the NetworkXRenderer initializes correctly."""
    engine = CoreEngine('test_engine')
    renderer = NetworkXRenderer(engine)
    assert isinstance(renderer, NetworkXRenderer)


def test_networkx_renderer_render_empty_engine() -> None:
    """Test that rendering an empty engine returns an graph with only a reset state."""
    engine = CoreEngine('empty_engine')
    renderer = NetworkXRenderer(engine)
    graph = renderer.render()
    assert isinstance(graph, nx.DiGraph)
    assert len(graph.nodes) == 1
    assert len(graph.edges) == 0


def test_networkx_renderer_render_single_state_engine() -> None:
    """Test that rendering an engine with a single state returns a graph with a single node."""
    engine = CoreEngine('single_state_engine')
    state = engine.create_state('state')  # noqa: F841
    renderer = NetworkXRenderer(engine)
    graph = renderer.render()
    assert isinstance(graph, nx.DiGraph)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 0


def test_networkx_renderer_render_multiple_states_engine() -> None:
    """Test that rendering an engine with multiple states returns a graph with multiple nodes."""
    engine = CoreEngine('multiple_states_engine')
    state1 = engine.create_state('state1')
    state2 = engine.create_state('state2')
    state1._add_transition(Const(True), state2)
    renderer = NetworkXRenderer(engine)
    graph = renderer.render()
    assert isinstance(graph, nx.DiGraph)
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 1


def test_networkx_renderer_render_engine_with_transitions() -> None:
    """Test that rendering an engine with transitions returns a graph with edges."""
    engine = CoreEngine('engine_with_transitions')
    state1 = engine.create_state('state1')
    state2 = engine.create_state('state2')
    state1._add_transition(Const(True), state2)
    renderer = NetworkXRenderer(engine)
    graph = renderer.render()
    assert isinstance(graph, nx.DiGraph)
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 1
    assert ('state1', 'state2') in graph.edges


def test_networkx_renderer_render_engine_with_multiple_transitions() -> None:
    """Test that rendering an engine with multiple transitions returns a graph with multiple edges."""
    engine = CoreEngine('engine_with_multiple_transitions')
    state1 = engine.create_state('state1')
    state2 = engine.create_state('state2')
    state3 = engine.create_state('state3')
    state1._add_transition(Const(True), state2)
    state1._add_transition(Const(True), state3)
    renderer = NetworkXRenderer(engine)
    graph = renderer.render()
    assert isinstance(graph, nx.DiGraph)
    assert len(graph.nodes) == 4
    assert len(graph.edges) == 2
    assert ('state1', 'state2') in graph.edges
    assert ('state1', 'state3') in graph.edges


def test_networkx_renderer_render_invalid_engine() -> None:
    """Test that rendering an invalid engine raises an exception.

    The exception occurs because the engine is not properly initialized.
    """
    with pytest.raises(AttributeError):
        renderer = NetworkXRenderer(None)  # type: ignore
        renderer.render()
