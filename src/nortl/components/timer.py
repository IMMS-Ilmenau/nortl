from typing import Union

from nortl.core.protocols import EngineProto, ParameterProto, Renderable


class Timer:
    """This class represents a timer in the engine. It provides functions for operating the timer conveniently.

    It depends on the availability of a verilog module `nortl_count_down_timer`
    """

    def __init__(
        self, engine: EngineProto, width: Union[int, ParameterProto] = 16, instance_name_prefix: str = 'I_TIMER', clock_gating: bool = False
    ) -> None:
        """Initializes a timer object in the engine.

        This function instantiates a (count-down) timer module in the engine and holds the signals for the delay, reload and finish / zero.

        Arguments:
            engine (CoreEngine): Target engine object
            width (int): width of the counter register
            instance_name_prefix (str): Prefix for the instance name used in verilog. This also prefixes the names of the connected signals
            clock_gating (bool): If true, the unit is connected to the gated clock. If clock gating is disable, this setting is ignored.
        """
        self.engine = engine

        timer_idx = 0
        while (instance_name := f'{instance_name_prefix}_{timer_idx}') in engine.module_instances:
            timer_idx = timer_idx + 1

        self.instance_name = instance_name

        self.timer_module = self.engine.create_module_instance('nortl_count_down_timer', self.instance_name, clock_gating)

        self.engine.override_module_parameter(self.instance_name, 'DATA_WIDTH', width)

        self.delay = self.engine.define_local(f'{self.instance_name}_delay', reset_value=0, width=width)  # Todo: Could be an async signal
        self.reload = self.engine.define_local(f'{self.instance_name}_reload', reset_value=0)  # Todo: Could be an async signal
        self.zero = self.engine.define_local(f'{self.instance_name}_zero')  # Todo: Could be an async signal

        self.engine.connect_module_port(self.instance_name, 'DELAY', self.delay)
        self.engine.connect_module_port(self.instance_name, 'RELOAD', self.reload)
        self.engine.connect_module_port(self.instance_name, 'ZERO', self.zero)

    def wait_delay(self, delay: Union[Renderable, int, bool]) -> None:
        """Wait for a given delay without returning control to the engine. This can be seen as blocking delay.

        Arguments:
            delay (Renderable): Delay to wait for (in cycles)
        """
        self.start_delay(delay)
        self.engine.wait_for(self.finished)

    def start_delay(self, delay: Union[Renderable, int, bool]) -> None:
        """Start the timer with a given delay. This acts as a non-blocking delay and therefore returns control after starting the timer.

        Arguments:
            delay (Renderable): Delay to wait for (in cycles)
        """
        self.engine.set(self.delay, delay)
        self.engine.set(self.reload, 1)
        self.engine.sync()
        self.engine.set(self.reload, 0)
        self.engine.sync()

    @property
    def finished(self) -> Renderable:
        """Returns the signal (Renderable) that signals, if the timer has finished, i.e. the counter register is zero.

        Returns:
            Renderable: Zero-Flag of the counter
        """
        return self.zero
