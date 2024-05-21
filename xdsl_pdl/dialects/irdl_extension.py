from __future__ import annotations
from typing import Sequence

from xdsl.irdl import (
    IRDLOperation,
    irdl_op_definition,
    operand_def,
    region_def,
    var_operand_def,
)
from xdsl.ir import Dialect, IsTerminator, Region, SSAValue

from xdsl.dialects.irdl import AttributeType
from xdsl.parser import DictionaryAttr, Parser
from xdsl.printer import Printer


@irdl_op_definition
class CheckSubsetOp(IRDLOperation):
    name = "irdl_ext.check_subset"

    lhs = region_def("single_block")
    rhs = region_def("single_block")

    def __init__(
        self, lhs: Region, rhs: Region, attr_dict: DictionaryAttr | None = None
    ):
        super().__init__(
            regions=[lhs, rhs],
            attributes=attr_dict.data if attr_dict is not None else None,
        )

    @classmethod
    def parse(cls: type[CheckSubsetOp], parser: Parser) -> CheckSubsetOp:
        attr_dict = parser.parse_optional_attr_dict_with_keyword()
        lhs = parser.parse_region()
        parser.parse_keyword("of")
        rhs = parser.parse_region()
        return CheckSubsetOp(lhs, rhs, attr_dict)

    def print(self, printer: Printer) -> None:
        printer.print(" ", self.lhs, " of ", self.rhs)
        printer.print_op_attributes(self.attributes)


@irdl_op_definition
class MatchOp(IRDLOperation):
    name = "irdl_ext.match"

    arg = operand_def(AttributeType())

    assembly_format = "attr-dict $arg"

    def __init__(
        self,
        arg: SSAValue,
        attr_dict: DictionaryAttr | None = None,
    ):
        super().__init__(
            operands=[arg],
            attributes=attr_dict.data if attr_dict is not None else None,
        )


@irdl_op_definition
class YieldOp(IRDLOperation):
    name = "irdl_ext.yield"

    args = var_operand_def(AttributeType())

    traits = frozenset({IsTerminator()})

    assembly_format = "attr-dict $args"

    def __init__(
        self,
        args: Sequence[SSAValue],
        attr_dict: DictionaryAttr | None = None,
    ):
        super().__init__(
            operands=[args],
            attributes=attr_dict.data if attr_dict is not None else None,
        )


@irdl_op_definition
class EqOp(IRDLOperation):
    name = "irdl_ext.eq"

    args = var_operand_def(AttributeType())

    assembly_format = "attr-dict $args"

    def __init__(
        self,
        args: Sequence[SSAValue],
        attr_dict: DictionaryAttr | None = None,
    ):
        super().__init__(
            operands=[args],
            attributes=attr_dict.data if attr_dict is not None else None,
        )


IRDLExtension = Dialect("irdl_ext", [CheckSubsetOp, MatchOp, YieldOp, EqOp])
