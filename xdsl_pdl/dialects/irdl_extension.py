from __future__ import annotations

from xdsl.irdl import (
    AttrSizedOperandSegments,
    IRDLOperation,
    irdl_op_definition,
    var_operand_def,
)
from xdsl.ir import Dialect

from xdsl.dialects.irdl import AttributeType


@irdl_op_definition
class CheckSubsetOp(IRDLOperation):
    name = "irdl_ext.check_subset"

    irdl_options = [AttrSizedOperandSegments()]

    lhs = var_operand_def(AttributeType())
    rhs = var_operand_def(AttributeType())

    assembly_format = "attr-dict `` `(` $lhs `)` `of` `` `(` $rhs `)`"


IRDLExtension = Dialect("irdl_ext", [CheckSubsetOp])
