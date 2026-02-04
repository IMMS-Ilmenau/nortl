from nortl import Engine


def test_clear_ram(engine: Engine) -> None:
    # Define outputs, reset values are zero
    col_all_on = engine.define_output('col_all_on', width=1)  # Bit width should be optional
    ram_write_zero = engine.define_output('ram_write_zero')
    ram_adr_incr = engine.define_output('ram_adr_incr')

    # Define inputs
    start = engine.define_input('start')
    ram_write_ack = engine.define_input('ram_write_ack')
    ram_end_of_addresses = engine.define_input('ram_end_of_addresses')

    # Define events; could also be done in place
    ram_write_ack_re = ram_write_ack.rising()

    _ = engine.define_local('test_local')

    # Reset State (State 0)
    engine.wait_for(start)

    # Enable all columns (State 1)
    row_loop = engine.current_state  # Remember current state
    engine.set(col_all_on, 1)
    engine.sync()

    # Write Zero to RAM (State 2)
    engine.set_once(ram_write_zero, 1)
    engine.wait_for(ram_write_ack_re == 1)

    # Increment RAM address (State 3)
    engine.set_once(ram_adr_incr, 1)
    engine.sync()

    # Loop (State 4)
    engine.jump_if(ram_end_of_addresses != 1, row_loop, engine.reset_state)

    # set_once merkt für den nächsten Zustand ein Assignment vor
    # es darf nur engine.sync() oder engine.wait_for() benutzt werden, alle anderen Transitions sind verboten (d.h. keine verzweigten States)

    assert len(engine.states[engine.MAIN_WORKER_NAME]) == 5
    assert len(engine.signals) == 9  # 3 inputs, 3 outputs, 2 event outputs (falling is always added too), 1 local signal
