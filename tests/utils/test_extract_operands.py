from nortl import Const, Engine
from nortl.utils.operand_extraction import extract_operands


def test_extract_operands() -> None:
    e = Engine('my_engine')

    a = e.define_input('A')
    b = e.define_input('B')

    c = e.define_input('C')

    con = Const(25, 8)

    res = [r.render() for r in extract_operands((a + b) * c)]

    assert a.render() in res
    assert b.render() in res
    assert c.render() in res
    assert con.render() not in res

    res = [r.render() for r in extract_operands((a + b) * c * con, keep_const=False)]

    assert a.render() in res
    assert b.render() in res
    assert c.render() in res
    assert con.render() not in res

    res = [r.render() for r in extract_operands((a + b) * c * con, keep_const=True)]

    assert a.render() in res
    assert b.render() in res
    assert c.render() in res
    assert con.render() in res


def test_extract_operands_slice_handling() -> None:
    e = Engine('my_engine')

    a = e.define_input('A', 8)

    res = [r.render() for r in extract_operands(a[3:0])]

    assert res == ['A[3:0]']


def test_extract_operands_scratch() -> None:
    e = Engine('my_engine')

    a = e.define_scratch(8)

    res = [r.render() for r in extract_operands(a[3:0])]

    assert res == ['SCRATCH_SIGNAL[3:0]']
