from xdsl.ir import Dialect
from xdsl.irdl import (
    IRDLOperation,
    VarOpResult,
    VarOperand,
    VarRegion,
    irdl_op_definition,
    var_operand_def,
    var_region_def,
    var_result_def,
)


@irdl_op_definition
class TestMatchOp(IRDLOperation):
    """A test operation representing an operation that will be matched."""

    name = "pdltest.matchop"

    res: VarOpResult = var_result_def()
    ops: VarOperand = var_operand_def()
    regs: VarRegion = var_region_def()


@irdl_op_definition
class TestRewriteOp(IRDLOperation):
    """A test operation representing an operation that has been rewritten."""

    name = "pdltest.rewriteop"

    res: VarOpResult = var_result_def()
    ops: VarOperand = var_operand_def()
    regs: VarRegion = var_region_def()


@irdl_op_definition
class TestUseOp(IRDLOperation):
    """A test operation representing an operation that has been rewritten."""

    name = "test.use_op"

    res: VarOpResult = var_result_def()
    ops: VarOperand = var_operand_def()
    regs: VarRegion = var_region_def()


@irdl_op_definition
class TestTerminatorOp(IRDLOperation):
    """A test operation representing an operation that has been rewritten."""

    name = "test.terminator"

    res: VarOpResult = var_result_def()
    ops: VarOperand = var_operand_def()
    regs: VarRegion = var_region_def()


PDLTest = Dialect("PDLTest", [TestMatchOp, TestRewriteOp, TestUseOp, TestTerminatorOp])
