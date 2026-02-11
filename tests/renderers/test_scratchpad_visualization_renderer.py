from pathlib import Path

from nortl import Engine
from nortl.renderer import ScratchpadVisualizationRenderer


def test_simple_rendering() -> None:
    # Some whatever engine
    engine = Engine('my_engine')
    engine.tracer.upper_boundary = str(Path(__file__))

    _ = engine.define_input('IN')
    engine.sync()
    local_cnt = engine.define_scratch(4)
    engine.set(local_cnt, 1)
    dummy_before = engine.define_local('test', 2, 0)
    engine.set(dummy_before, local_cnt)

    with engine.fork('proc2') as proc2:
        with engine.fork('Proc1') as proc1:
            dummy = engine.define_scratch(2)
            engine.set(dummy, local_cnt)
            engine.sync()
            engine.set(local_cnt, 2)

        proc1.cancel()
        engine.set(local_cnt, 2)
        engine.set(dummy_before, local_cnt)

    proc2.cancel()
    dummy = engine.define_scratch(2)
    engine.set(dummy, local_cnt)
    engine.sync()

    renderer = ScratchpadVisualizationRenderer(engine)

    with open((Path(__file__).parent / 'artifacts') / 'out.md', 'w') as file:
        file.write(renderer.render())
