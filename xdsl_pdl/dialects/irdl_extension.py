from __future__ import annotations

from xdsl.irdl import (
    AttrSizedOperandSegments,
    IRDLOperation,
    irdl_op_definition,
    region_def,
    var_operand_def,
)
from xdsl.ir import Dialect, Region

from xdsl.dialects.irdl import AttributeType
from xdsl.parser import DictionaryAttr, Parser
from xdsl.printer import Printer


@irdl_op_definition
class CheckSubsetOp(IRDLOperation):
    name = "irdl_ext.check_subset"

    irdl_options = [AttrSizedOperandSegments()]

    lhs = region_def("single_block")
    rhs = region_def("single_block")

    # assembly_format = "attr-dict $lhs `of` $rhs"

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
        printer.print(self.lhs, " of ", self.rhs)
        printer.print_attr_dict(self.attributes)


@irdl_op_definition
class YieldOp(IRDLOperation):
    name = "irdl_ext.yield"

    args = var_operand_def(AttributeType())

    assembly_format = "attr-dict $args"


IRDLExtension = Dialect("irdl_ext", [CheckSubsetOp, YieldOp])
