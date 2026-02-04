from typing import Dict, List, Optional, Union

from .formatter import VerilogFormatter
from .utils import VerilogRenderable


class VerilogDeclaration:
    def __init__(
        self,
        verilog_type: str,
        name: Union[str, List[str]],
        width: Union[int, str, VerilogRenderable] = 0,
        connections: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        members: Optional[Union[List[str], Dict[str, int]]] = None,
    ):
        self.verilog_type = verilog_type
        self.name = name
        self.connections = connections
        self.params = params
        self.members = members
        self.width = width

    def add_member(self, name: str, value: Optional[Union[int]] = None) -> None:
        if self.members is None:
            if value is not None:
                self.members = {}
            else:
                self.members = []

        if isinstance(self.members, list):
            if value is not None:
                raise RuntimeError('Cannot add an encoded member to an enum without all items to be encoded!')
            self.members.append(name)
        else:
            if value is None:
                raise RuntimeError('Cannot add an un-encoded member to an enum where all items are encoded!')
            self.members[name] = value

    def add_parameter(self, name: str, value: Union[str, int]) -> None:
        if self.params is None:
            self.params = {}

        if isinstance(value, int):
            self.params[name] = str(value)
        else:
            self.params[name] = value

    def add_connection(self, src: str, tgt: str) -> None:
        if self.connections is None:
            self.connections = {}

        self.connections[src] = tgt

    def render(self) -> str:  # noqa: C901
        content: List[str] = []
        connection_lst = []
        param_lst = []

        if self.connections is not None:
            connection_lst = [f'.{x}({y})' for x, y in self.connections.items()]
        if self.params is not None:
            param_lst = [f'.{x}({y})' for x, y in self.params.items()]

        name_str = ''

        content.append(self.verilog_type)

        if isinstance(self.name, list):
            name_str = ', '.join(self.name)
        else:
            name_str = self.name

        if isinstance(self.width, int):
            if self.width > 1:
                content.append(f'[{self.width - 1}:0]')
        else:
            content.append(f'[{self.width}-1:0]')

        if self.verilog_type.startswith('enum'):
            if self.members is None:
                raise RuntimeError(f'Tried to create enum {name_str} without any values. Something is wrong here.')

            if isinstance(self.members, List):
                item_str = ', '.join(self.members)
            else:
                item_str = ', '.join([f'{item} = {value}' for item, value in self.members.items()])

            content.append(f'{{{item_str}}}')

        if self.params is not None:
            content.append(f'#({", ".join(param_lst)})')

        content.append(name_str)

        if not any(t in self.verilog_type for t in ['wire', 'logic', 'reg']) and not self.verilog_type.startswith(
            'enum'
        ):  # other net types are out of scope for now
            content.append(f'({", ".join(connection_lst)})')

        return ' '.join(content)


class VerilogModule:
    def __init__(self, name: str) -> None:
        self.name = name
        self.ports: List[VerilogDeclaration] = []
        self.parameters: Dict[str, Optional[Union[int, str]]] = {}
        self.signals: List[VerilogDeclaration] = []
        self.instances: List[VerilogDeclaration] = []
        self.functionals: List[VerilogRenderable] = []

    def render(self) -> str:
        content = []
        line = f'module {self.name} '

        if len(self.parameters) != 0:
            params = []
            for p, val in self.parameters.items():
                if val is None:
                    params.append(f'parameter {p}')
                else:
                    params.append(f'parameter {p} = {val}')

            line = f'{line} #(\n{",\n".join(params)}) '

        ports = [p.render() for p in self.ports]

        line = f'{line} ({",\n".join(ports)});'

        content.append(line)

        content.extend([item.render() + ';' for item in self.signals + self.instances])
        content.extend([item.render() for item in self.functionals])

        content.append('endmodule')

        code = '\n'.join(content)

        return VerilogFormatter(code).format()

    def get_instance(self, name: str) -> VerilogDeclaration:
        for item in self.instances:
            if item.name == name:
                return item
        raise RuntimeError(f'Could not find an instance named {name}.')
