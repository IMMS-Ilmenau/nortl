from nortl.renderer.verilog_utils.structural import VerilogDeclaration


def test_register_declaration_width_0() -> None:
    target = VerilogDeclaration('logic', 'A')
    assert target.render() == 'logic A'

    target = VerilogDeclaration('logic', 'A', 0)
    assert target.render() == 'logic A'


def test_register_declaration() -> None:
    target = VerilogDeclaration('logic', 'A', 4)
    assert target.render() == 'logic [3:0] A'


def test_double_register_declaration() -> None:
    target = VerilogDeclaration('logic', ['A', 'B'], 4)
    assert target.render() == 'logic [3:0] A, B'


def test_enum() -> None:
    target = VerilogDeclaration('enum logic', 'A', 4, members=['STATE1', 'STATE2'])
    assert target.render() == 'enum logic [3:0] {STATE1, STATE2} A'

    target = VerilogDeclaration('enum logic', 'A')
    target.add_member('STATE1', 0)
    target.add_member('STATE2', 1)

    assert target.render() == 'enum logic {STATE1 = 0, STATE2 = 1} A'


def test_param() -> None:
    target = VerilogDeclaration('BU', 'A')
    target.add_parameter('WIDTH', 1)

    assert target.render() == 'BU #(.WIDTH(1)) A ()'


def test_connection() -> None:
    target = VerilogDeclaration('BU', 'A')
    target.add_connection('A', 'B')
    target.add_connection('C', 'D')

    assert target.render() == 'BU A (.A(B), .C(D))'
