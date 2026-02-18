"""Verilog process and control flow constructs.

This module provides classes for constructing Verilog procedural blocks,
including assignments, conditionals, loops, and process blocks.

Example:
    >>> from nortl.renderer.verilog_utils.process import (
    ...     VerilogAssignment, VerilogBlock, VerilogIf, AlwaysFF
    ... )
    >>>
    >>> # Create an assignment
    >>> assignment = VerilogAssignment("count", "count + 1")
    >>> print(assignment.render())
    count <= count + 1;
    >>>
    >>> # Create a block with multiple items
    >>> block = VerilogBlock()
    >>> block.add(VerilogAssignment("state", "next_state"))
    >>> block.add(VerilogAssignment("valid", "1'b1"))
    >>> print(block.render())
    begin
        count <= count + 1;
        valid <= 1'b1;
    end
    >>>
    >>> # Create an always_ff block
    >>> always_ff = AlwaysFF("clk", "reset")
    >>> always_ff.add(VerilogAssignment("state", "next_state"))
    >>> print(always_ff.render())
    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            state <= next_state;
        end
    end
"""

from collections import deque
from typing import Deque, Dict, List, Literal, Optional, Tuple, Union

from .utils import VerilogRenderable, to_verilog_renderable


class VerilogAssignment:
    """Represents a Verilog assignment.

    Args:
        tgt: The target signal or expression.
        src: The source signal or expression.

    Example:
        >>> assignment = VerilogAssignment("count", "count + 1")
        >>> print(assignment.render())
        count <= count + 1;
    """

    def __init__(self, tgt: Union[str, VerilogRenderable], src: Union[str, VerilogRenderable]) -> None:
        """Initialize the assignment.

        Args:
            tgt: The target signal or expression.
            src: The source signal or expression.
        """
        self.tgt = to_verilog_renderable(tgt)
        self.src = to_verilog_renderable(src)
        self.operator = '<='

    def render(self) -> str:
        """Render the assignment.

        Returns:
            The Verilog assignment string.
        """
        return f'{self.tgt} {self.operator} {self.src};'


class VerilogBlock:
    """Represents a Verilog begin-end block.

    Example:
        >>> block = VerilogBlock()
        >>> block.add(VerilogAssignment("x", "1'b1"))
        >>> block.add(VerilogAssignment("y", "x"))
        >>> print(block.render())
        begin
            x <= 1'b1;
            y <= x;
        end
    """

    def __init__(self) -> None:
        """Initialize an empty block."""
        self.items: Deque[VerilogRenderable] = deque([])

    def render(self) -> str:
        """Render the block.

        Returns:
            The Verilog block string.
        """
        content: List[str] = ['begin']
        content.append(self.render_items())
        content.append('end')

        return '\n'.join(content)

    def render_items(self) -> str:
        """Render all items in the block.

        Returns:
            The rendered items as a string.
        """
        content: List[str] = []
        content.extend(item.render() for item in self.items)
        return '\n'.join(content)

    def add(self, item: VerilogRenderable) -> None:
        """Add an item to the block.

        Args:
            item: The item to add.
        """
        self.items.append(item)

    def __len__(self) -> int:
        """Return the number of items in the block.

        Returns:
            The number of items.
        """
        return len(self.items)


class VerilogCase:
    """Represents a Verilog case statement.

    Args:
        tgt_signal: The signal to switch on.
        case_type: The case type ('unique', 'priority', or empty for regular case).

    Example:
        >>> case_stmt = VerilogCase("state", "unique")
        >>> case_stmt.add_item("IDLE", VerilogAssignment("count", "0"))
        >>> case_stmt.add_item("RUNNING", VerilogAssignment("count", "count + 1"))
        >>> print(case_stmt.render())
        unique case (state)
            IDLE: begin
                count <= 0;
            end
            RUNNING: begin
                count <= count + 1;
            end
        endcase
    """

    def __init__(self, tgt_signal: str, case_type: Literal['unique', 'priority', ''] = '') -> None:
        """Initialize the case statement.

        Args:
            tgt_signal: The signal to switch on.
            case_type: The case type ('unique', 'priority', or empty for regular case).
        """
        self.tgt_signal = tgt_signal
        self.cases: Dict[str, VerilogBlock] = {}
        self.compress_output = True
        self.case_type = case_type + ' '

    def add_case(self, value: str, block: Optional[VerilogBlock] = None) -> None:
        """Add a case value and its associated block.

        Args:
            value: The case value.
            block: The VerilogBlock for this case (creates a new one if None).
        """
        if block is None:
            self.cases[value] = VerilogBlock()
        else:
            self.cases[value] = block

    def add_item(self, case: str, item: VerilogRenderable) -> None:
        """Add an item to a specific case.

        Args:
            case: The case value.
            item: The item to add.
        """
        if case not in self.cases:
            self.add_case(case)

        self.cases[case].add(item)

    def compress_cases(self) -> Dict[str, str]:
        """Compress duplicate case blocks.

        Returns:
            A dictionary of compressed case values to block content.
        """
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
        """Render the case statement.

        Returns:
            The Verilog case statement string.
        """
        content: List[str] = []

        if all(len(block) == 0 for block in self.cases.values()):
            return ''

        content.append(f'{self.case_type} case ({self.tgt_signal})')

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
    """Represents a Verilog if-else statement.

    Example:
        >>> if_stmt = VerilogIf("reset")
        >>> if_stmt.true_branch.add(VerilogAssignment("state", "IDLE"))
        >>> if_stmt.false_branch.add(VerilogAssignment("state", "next_state"))
        >>> print(if_stmt.render())
        if (reset) begin
            state <= IDLE;
        end
        else begin
            state <= next_state;
        end
    """

    def __init__(
        self,
        condition: Union[VerilogRenderable, str],
        true_branch: Optional[VerilogRenderable] = None,
        false_branch: Optional[VerilogRenderable] = None,
    ) -> None:
        """Initialize the if statement.

        Args:
            condition: The condition for the if statement.
            true_branch: What is to be put in the true branch of the statement
            false_branch: Similar to true branch -- but for the false branch, obviously
        """
        self.condition: VerilogRenderable = to_verilog_renderable(condition)
        self.true_branch = VerilogBlock()
        self.false_branch = VerilogBlock()

        if true_branch is not None:
            self.true_branch.add(true_branch)
        if false_branch is not None:
            self.false_branch.add(false_branch)

    def render(self) -> str:
        """Render the if-else statement.

        Returns:
            The Verilog if-else statement string.
        """
        if self.condition.render() == '1':
            return self.true_branch.render_items()

        content = [f'if ({self.condition})']
        content.append(self.true_branch.render())

        if len(self.false_branch) > 0:
            content.append('else ')
            content.append(self.false_branch.render())

        return '\n'.join(content)


class VerilogProcess:
    """Base class for Verilog procedural blocks.

    Example:
        >>> process = VerilogProcess()
        >>> process.add_sensitivity('posedge', 'clk')
        >>> process.content.add(VerilogAssignment("state", "next_state"))
        >>> print(process.render())
        always @(posedge clk) begin
            state <= next_state;
        end
    """

    def __init__(self) -> None:
        """Initialize the process."""
        self.sensitivity: List[Tuple[Literal['posedge', 'negedge'], VerilogRenderable]] = []
        self.content = VerilogBlock()
        self.render_sensitivity = True
        self.block_label = 'always'

    def _add(self, item: VerilogRenderable) -> None:
        """Add an item to the content.

        Args:
            item: The item to add.
        """
        self.content.add(item)

    def add_sensitivity(self, edge: Literal['posedge', 'negedge'], signal: VerilogRenderable) -> None:
        """Add a sensitivity list entry.

        Args:
            edge: The edge ('posedge' or 'negedge').
            signal: The signal to monitor.
        """
        self.sensitivity.append((edge, signal))

    def render(self) -> str:
        """Render the process.

        Returns:
            The Verilog process string.
        """
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
    """Represents an always_ff block with clock and reset.

    Args:
        clk: The clock signal.
        reset: The reset signal.

    Example:
        >>> always_ff = AlwaysFF("clk", "reset")
        >>> always_ff.add(VerilogAssignment("state", "next_state"))
        >>> print(always_ff.render())
        always_ff @(posedge clk or posedge reset) begin
            if (reset) begin
                state <= next_state;
            end
        end
    """

    def __init__(self, clk: Union[VerilogRenderable, str], reset: Union[VerilogRenderable, str]) -> None:
        """Initialize the always_ff block.

        Args:
            clk: The clock signal.
            reset: The reset signal.
        """
        super().__init__()
        self.clk = clk
        self.reset = reset

        self.behavior = VerilogIf(to_verilog_renderable(reset))
        self._add(self.behavior)

        self.block_label = 'always_ff'

    def add_reset(self, item: VerilogRenderable) -> None:
        """Add an item to the reset branch.

        Args:
            item: The item to add.
        """
        self.behavior.true_branch.add(item)

    def add(self, item: VerilogRenderable) -> None:
        """Add an item to the non-reset branch.

        Args:
            item: The item to add.
        """
        self.behavior.false_branch.add(item)

    def render(self) -> str:
        """Render the always_ff block.

        Returns:
            The Verilog always_ff string.
        """
        self.add_sensitivity('posedge', to_verilog_renderable(self.clk))
        self.add_sensitivity('posedge', to_verilog_renderable(self.reset))

        return super().render()


class AlwaysComb(VerilogProcess):
    """Represents an always_comb block.

    Example:
        >>> always_comb = AlwaysComb()
        >>> always_comb.add(VerilogAssignment("next_state", "state + 1"))
        >>> print(always_comb.render())
        always_comb begin
            next_state <= state + 1;
        end
    """

    def __init__(self) -> None:
        """Initialize the always_comb block."""
        super().__init__()
        self.block_label = 'always_comb'
        self.render_sensitivity = False

    def add(self, item: VerilogRenderable) -> None:
        """Add an item to the block.

        Args:
            item: The item to add.
        """
        self._add(item)


class AlwaysLatch(VerilogProcess):
    """Represents an always_latch block with latch enable.

    Args:
        latch_en: The latch enable condition.

    Example:
        >>> always_latch = AlwaysLatch("enable")
        >>> always_latch.add(VerilogAssignment("data", "input_data"))
        >>> print(always_latch.render())
        always_latch begin
            if (enable) begin
                data <= input_data;
            end
        end
    """

    def __init__(self, latch_en: VerilogRenderable) -> None:
        """Initialize the always_latch block.

        Args:
            latch_en: The latch enable condition.
        """
        super().__init__()

        self.behavior = VerilogIf(latch_en)
        self._add(self.behavior)

        self.block_label = 'always_latch'
        self.render_sensitivity = False

    def add(self, item: VerilogRenderable) -> None:
        """Add an item to the latch enable branch.

        Args:
            item: The item to add.
        """
        self.behavior.true_branch.add(item)


class VerilogPrint:
    """Represents a Verilog $display statement.

    Args:
        line: The format string.
        args: The arguments to display.

    Example:
        >>> print_stmt = VerilogPrint("State: %d", "state")
        >>> print(print_stmt.render())
        $display("State: %d", state);
    """

    def __init__(self, line: str, *args: str) -> None:
        """Initialize the print statement.

        Args:
            line: The format string.
            args: The arguments to display.
        """
        self.line = line
        self.args = args

    def render(self) -> str:
        """Render the print statement.

        Returns:
            The Verilog $display string.
        """
        line = f'$display("{self.line}", {",".join(self.args)});'
        return line


class VerilogPrintf:
    """Represents a Verilog $fdisplay statement for file output.

    Args:
        fname: The filename.
        line: The format string.
        args: The arguments to display.

    Example:
        >>> printf_stmt = VerilogPrintf("output.log", "State: %d", "state")
        >>> print(printf_stmt.render())
        begin
            int fd;
            fd = $fopen(output.log, "w+");
            $fdisplay("State: %d", state);
            $fclose(fd);
        end
    """

    def __init__(self, fname: str, line: str, *args: str) -> None:
        """Initialize the printf statement.

        Args:
            fname: The filename.
            line: The format string.
            args: The arguments to display.
        """
        self.fname = fname
        self.line = line
        self.args = args

    def render(self) -> str:
        """Render the printf statement.

        Returns:
            The Verilog $fdisplay string.
        """
        ret = []
        ret.append('begin')
        ret.append('int fd;')
        ret.append(f'fd = $fopen({self.fname}, "w+");')
        ret.append(f'$fdisplay("{self.line}", {",".join(self.args)});')
        ret.append('$fclose(fd);')
        ret.append('end')

        return '\n'.join(ret)
