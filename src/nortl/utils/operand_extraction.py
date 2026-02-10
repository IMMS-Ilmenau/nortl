from typing import List, Union

from nortl.core.operations import Const
from nortl.core.protocols import OperationProto, Renderable


def extract_operands(obj: Union[Renderable, OperationProto], keep_const: bool = False) -> List[Union[Renderable, OperationProto]]:
    ret = []

    if hasattr(obj, 'operands'):
        for op in obj.operands:
            ret += extract_operands(op, keep_const)
    else:
        if keep_const or not isinstance(obj, Const):
            ret.append(obj)

    return ret
