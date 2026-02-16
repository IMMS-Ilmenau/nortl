"""Verilog code formatter for proper indentation and line breaks.

This module provides a simple formatter that adds proper indentation to Verilog code
and ensures appropriate line breaks for module and always blocks.

Example:
    >>> from nortl.renderer.verilog_utils.formatter import VerilogFormatter
    >>>
    >>> code = '''module test (
    ...     input clk,
    ...     input reset
    ... );
    ...
    ... always @(*) begin
    ...     if (reset) begin
    ...         count <= 0;
    ...     end
    ... end
    ... endmodule'''
    >>>
    >>> formatter = VerilogFormatter(code)
    >>> print(formatter.format())
    module test (
        input clk,
        input reset
    );

    always @(*) begin
        if (reset) begin
            count <= 0;
        end
    end

    endmodule
"""


class VerilogFormatter:
    r"""Format Verilog code with proper indentation and line breaks.

    The formatter automatically handles indentation for begin/end blocks and
    adds newlines after module and always declarations.

    Args:
        code: The Verilog code to format.

    Example:
        >>> formatter = VerilogFormatter("always @(*) begin\n    x <= 1;\nend")
        >>> print(formatter.format())
        always @(*) begin
            x <= 1;
        end
    """

    def __init__(self, code: str) -> None:
        """Initialize the formatter with Verilog code.

        Args:
            code: The Verilog code to format.
        """
        self.code_lst = code.split('\n')
        self.indent_level = 0

    def format(self) -> str:
        """Format the Verilog code.

        Returns:
            The formatted Verilog code with proper indentation and line breaks.
        """
        self.code_lst = [self._indent(line) for line in self.code_lst]
        self.code_lst = [self._newlines(line) for line in self.code_lst]
        return '\n'.join(self.code_lst)

    def _indent(self, line: str) -> str:
        """Indent a line based on begin/end keywords.

        Args:
            line: The line to indent.

        Returns:
            The indented line.
        """
        reasons_for_indent = ['begin', 'case']
        reasons_for_dedent = ['end', 'endcase']

        if any([x in line.split() for x in reasons_for_dedent]):
            self.indent_level -= 1

        ret = '   ' * self.indent_level + line

        if any([x in line.split() for x in reasons_for_indent]):
            self.indent_level += 1

        return ret

    def _newlines(self, line: str) -> str:
        """Add newline after module or always declarations.

        Args:
            line: The line to check.

        Returns:
            The line with a newline prefix if needed.
        """
        reasons_for_newline = ['module', 'always']
        if any(line.strip().startswith(reason) for reason in reasons_for_newline):
            return f'\n{line}'
        return line
