from collections import deque
from typing import Deque, Dict, List, Literal, Optional, Tuple, Union

from .utils import VerilogRenderable, to_verilog_renderable


class VerilogAssignment:
    def __init__(self, tgt: Union[str, VerilogRenderable], src: Union[str, VerilogRenderable]) -> None:
        self.tgt = to_verilog_renderable(tgt)
        self.src = to_verilog_renderable(src)
        self.operator = '<='

    def render(self) -> str:
        return f'{self.tgt} {self.operator} {self.src};'


class VerilogBlock:
    def __init__(self) -> None:
        self.items: Deque[VerilogRenderable] = deque([])

    def render(self) -> str:
        content: List[str] = ['begin']
        content.append(self.render_items())
        content.append('end')

        return '\n'.join(content)

    def render_items(self) -> str:
        content: List[str] = []
        content.extend(item.render() for item in self.items)
        return '\n'.join(content)

    def add(self, item: VerilogRenderable) -> None:
        self.items.append(item)

    def __len__(self) -> int:
        return len(self.items)


class VerilogCase:
    def __init__(self, tgt_signal: str) -> None:
        self.tgt_signal = tgt_signal
        self.cases: Dict[str, VerilogBlock] = {}
        self.compress_output = True

    def add_case(self, value: str, block: Optional[VerilogBlock] = None) -> None:
        if block is None:
            self.cases[value] = VerilogBlock()
        else:
            self.cases[value] = block

    def add_item(self, case: str, item: VerilogRenderable) -> None:
        if case not in self.cases:
            self.add_case(case)

        self.cases[case].add(item)

    def compress_cases(self) -> Dict[str, str]:
        new_cases: Dict[str, str] = {}

        for case, block in self.cases.items():
            if len(block) != 0:
                old_case = ''
                new_block = block.render()

                for existing_case, existing_block in new_cases.items():
                    if existing_block == new_block:
                        old_case = existing_case

                if old_case == '':
                    new_cases[case] = new_block
                else:
                    del new_cases[old_case]
                    new_cases[f'{case}, {old_case}'] = new_block

        return new_cases

    def render(self) -> str:
        content: List[str] = []

        if all(len(block) == 0 for block in self.cases.values()):
            return ''

        content.append(f'case ({self.tgt_signal})')

        if self.compress_output:
            for case, block in self.compress_cases().items():
                content.append(f'{case}: {block}')
        else:
            for case, vblock in self.cases.items():
                if len(vblock) != 0:
                    content.append(f'{case}: {vblock.render()}')

        content.append('endcase')

        return '\n'.join(content)


class VerilogIf:
    def __init__(self, condition: Union[VerilogRenderable, str]) -> None:
        self.condition: VerilogRenderable = to_verilog_renderable(condition)
        self.true_branch = VerilogBlock()
        self.false_branch = VerilogBlock()

    def render(self) -> str:
        if self.condition.render() == '1':
            return self.true_branch.render_items()

        content = [f'if ({self.condition})']
        content.append(self.true_branch.render())

        if len(self.false_branch) > 0:
            content.append('else ')
            content.append(self.false_branch.render())

        return '\n'.join(content)


class VerilogProcess:
    def __init__(self) -> None:
        self.sensitivity: List[Tuple[Literal['posedge', 'negedge'], VerilogRenderable]] = []
        self.content = VerilogBlock()
        self.render_sensitivity = True
        self.block_label = 'always'

    def _add(self, item: VerilogRenderable) -> None:
        self.content.add(item)

    def add_sensitivity(self, edge: Literal['posedge', 'negedge'], signal: VerilogRenderable) -> None:
        self.sensitivity.append((edge, signal))

    def render(self) -> str:
        content = []

        line = f'{self.block_label}'

        if self.render_sensitivity:
            if self.sensitivity == []:
                line = f'{line} @(*)'
            else:
                sens_lst = []
                for edge, signal in self.sensitivity:
                    sens_lst.append(f'{edge} {signal}')
                line = f'{line} @({" or ".join(sens_lst)})'

        content.append(line)

        content.append(self.content.render())

        return '\n'.join(content)


class AlwaysFF(VerilogProcess):
    def __init__(self, clk: Union[VerilogRenderable, str], reset: Union[VerilogRenderable, str]) -> None:
        super().__init__()
        self.clk = clk
        self.reset = reset

        self.behavior = VerilogIf(to_verilog_renderable(reset))
        self._add(self.behavior)

        self.block_label = 'always_ff'

    def add_reset(self, item: VerilogRenderable) -> None:
        self.behavior.true_branch.add(item)

    def add(self, item: VerilogRenderable) -> None:
        self.behavior.false_branch.add(item)

    def render(self) -> str:
        self.add_sensitivity('posedge', to_verilog_renderable(self.clk))
        self.add_sensitivity('posedge', to_verilog_renderable(self.reset))

        return super().render()


class AlwaysComb(VerilogProcess):
    def __init__(self) -> None:
        super().__init__()
        self.block_label = 'always_comb'
        self.render_sensitivity = False

    def add(self, item: VerilogRenderable) -> None:
        self._add(item)


class AlwaysLatch(VerilogProcess):
    def __init__(self, latch_en: VerilogRenderable) -> None:
        super().__init__()

        self.behavior = VerilogIf(latch_en)
        self._add(self.behavior)

        self.block_label = 'always_latch'
        self.render_sensitivity = False

    def add(self, item: VerilogRenderable) -> None:
        self.behavior.true_branch.add(item)


class VerilogPrint:
    def __init__(self, line: str, *args: str) -> None:
        self.line = line
        self.args = args

    def render(self) -> str:
        line = f'$display("{self.line}", {",".join(self.args)});'
        return line


class VerilogPrintf:
    def __init__(self, fname: str, line: str, *args: str) -> None:
        self.fname = fname
        self.line = line
        self.args = args

    def render(self) -> str:
        ret = []
        ret.append('begin')
        ret.append('int fd;')
        ret.append(f'fd = $fopen({self.fname}, "w+");')
        ret.append(f'$fdisplay("{self.line}", {",".join(self.args)});')
        ret.append('$fclose(fd);')
        ret.append('end')

        return '\n'.join(ret)
