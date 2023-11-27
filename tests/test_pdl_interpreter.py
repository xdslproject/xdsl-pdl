from xdsl.dialects import arith
from xdsl.dialects.builtin import (
    ModuleOp,
    i32,
)
from xdsl.interpreter import Interpreter
from xdsl.ir import MLContext
from xdsl.utils.test_value import TestSSAValue

from xdsl_pdl.dialects import pdl_extension as pdl
from xdsl_pdl.interpreters.pdl_interpreter_extension import PDLRewriteFunctionsExt


def test_pdl_result_op():
    interpreter = Interpreter(ModuleOp([]))
    interpreter.register_implementations(PDLRewriteFunctionsExt(MLContext()))

    c0 = TestSSAValue(i32)
    c1 = TestSSAValue(i32)
    add = arith.Addi(c0, c1)
    add_res = add.result

    assert interpreter.run_op(
        pdl.ResultOp(0, TestSSAValue(pdl.OperationType())), (add,)
    ) == (add_res,)
