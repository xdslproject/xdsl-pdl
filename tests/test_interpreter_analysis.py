from typing import Callable

from xdsl.builder import Builder, ImplicitBuilder
from xdsl.dialects import arith, func, builtin
from xdsl.dialects.test import TestOp
from xdsl.dialects.builtin import ArrayAttr, IntegerAttr, ModuleOp, StringAttr, i32
from xdsl.interpreter import Interpreter
from xdsl.interpreters.experimental.pdl import PDLMatcher, PDLRewritePattern
from xdsl.ir import MLContext, Block
from xdsl.pattern_rewriter import (
    PatternRewriter,
    PatternRewriteWalker,
    RewritePattern,
    op_type_rewrite_pattern,
)
from xdsl_pdl.dialects import pdl_extension as pdl
from xdsl.parser import Parser
from xdsl.printer import Printer
from xdsl_pdl.interpreters.pdl_analysis_interpreter import (
    PDLAnalysisFunctions,
    PDLAnalysisException,
)
import pytest

tests: list[Callable[[], None]] = []

type_t = pdl.TypeType()
attribute_t = pdl.AttributeType()
value_t = pdl.ValueType()
operation_t = pdl.OperationType()

block = Block(
    arg_types=[
        type_t,
        attribute_t,
        value_t,
        operation_t,
    ]
)

type_val, attr_val, val_val, op_val = block.args


def run_interpreter(f: Callable[[MLContext, Interpreter], None]):
    def test():
        print("\nTEST:", f.__name__)

        ctx = MLContext()
        ctx.load_dialect(builtin.Builtin)
        ctx.load_dialect(func.Func)
        ctx.load_dialect(pdl.PDL_EXT)
        interpreter = Interpreter(ModuleOp([]))
        interpreter.register_implementations(PDLAnalysisFunctions())
        f(ctx, interpreter)

    tests.append(test)
    return test


@run_interpreter
def test_simple_pattern(ctx: MLContext, interpreter: Interpreter):
    pattern_str = """
"builtin.module"() ({
  "pdl.pattern"() <{benefit = 1 : i16, sym_name = "rewrite_with_args"}> ({
    %0 = "pdl.operand"() : () -> !pdl.value
    %1 = "pdl.operation"(%0) <{attributeValueNames = [], operandSegmentSizes = array<i32: 1, 0, 0>}> : (!pdl.value) -> !pdl.operation
    "pdl.rewrite"(%1, %0) <{name = "rewriter", operandSegmentSizes = array<i32: 1, 1>}> ({
    }) : (!pdl.operation, !pdl.value) -> ()
  }) : () -> ()
}) : () -> ()
    """

    bigger_pattern_str = """
"builtin.module"() ({
  "pdl.pattern"() <{benefit = 1 : i16}> ({
    %0 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %1 = "pdl.operation"(%0) <{attributeValueNames = [], opName = "pdltest.matchop", operandSegmentSizes = array<i32: 0, 0, 1>}> : (!pdl.type) -> !pdl.operation
    %2 = "pdl.result"(%1) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
    %3 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %4 = "pdl.operand"(%3) : (!pdl.type) -> !pdl.value
    %5 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %6 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %7 = "pdl.operation"(%4, %2, %5, %6) <{attributeValueNames = [], opName = "pdltest.matchop", operandSegmentSizes = array<i32: 2, 0, 2>}> : (!pdl.value, !pdl.value, !pdl.type, !pdl.type) -> !pdl.operation
    %8 = "pdl.result"(%7) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
    %9 = "pdl.result"(%7) <{index = 1 : i32}> : (!pdl.operation) -> !pdl.value
    "pdl.rewrite"(%7) <{operandSegmentSizes = array<i32: 1, 0>}> ({
      %10 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
      %11 = "pdl.operation"(%10) <{attributeValueNames = [], opName = "pdltest.rewriteop", operandSegmentSizes = array<i32: 0, 0, 1>}> : (!pdl.type) -> !pdl.operation
      %12 = "pdl.result"(%11) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
      "pdl.replace"(%11, %1) <{operandSegmentSizes = array<i32: 1, 1, 0>}> : (!pdl.operation, !pdl.operation) -> ()
    }) : (!pdl.operation) -> ()
  }) : () -> ()
}) : () -> ()
"""
    parser = Parser(ctx=ctx, input=bigger_pattern_str)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    interpreter.run_op(pattern, ())


@run_interpreter
def test_erase_out_of_scope(ctx: MLContext, interpreter: Interpreter):
    program = """
"builtin.module"() ({
  "pdl.pattern"() <{benefit = 1 : i16}> ({
    %0 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %1 = "pdl.operation"(%0) <{attributeValueNames = [], opName = "pdltest.matchop", operandSegmentSizes = array<i32: 0, 0, 1>}> : (!pdl.type) -> !pdl.operation
    "pdl.rewrite"(%1) <{operandSegmentSizes = array<i32: 1, 0>}> ({
        "pdl.erase"(%1) : (!pdl.operation) -> ()
        "pdl.erase"(%1) : (!pdl.operation) -> ()
    }) : (!pdl.operation) -> ()
  }) : () -> ()
}) : () -> ()
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(PDLAnalysisException, match="operand not in scope"):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_double_replace(ctx: MLContext, interpreter: Interpreter):
    program = """
"builtin.module"() ({
  "pdl.pattern"() <{benefit = 1 : i16}> ({
    %0 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %1 = "pdl.operation"(%0) <{attributeValueNames = [], opName = "pdltest.matchop", operandSegmentSizes = array<i32: 0, 0, 1>}> : (!pdl.type) -> !pdl.operation
    %2 = "pdl.result"(%1) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
    %3 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %4 = "pdl.operand"(%3) : (!pdl.type) -> !pdl.value
    %5 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %6 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %7 = "pdl.operation"(%4, %2, %5, %6) <{attributeValueNames = [], opName = "pdltest.matchop", operandSegmentSizes = array<i32: 2, 0, 2>}> : (!pdl.value, !pdl.value, !pdl.type, !pdl.type) -> !pdl.operation
    %8 = "pdl.result"(%7) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
    %9 = "pdl.result"(%7) <{index = 1 : i32}> : (!pdl.operation) -> !pdl.value
    "pdl.rewrite"(%7) <{operandSegmentSizes = array<i32: 1, 0>}> ({
      %10 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
      %11 = "pdl.operation"(%10) <{attributeValueNames = [], opName = "pdltest.rewriteop", operandSegmentSizes = array<i32: 0, 0, 1>}> : (!pdl.type) -> !pdl.operation
      %12 = "pdl.result"(%11) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
      "pdl.replace"(%11, %1) <{operandSegmentSizes = array<i32: 1, 1, 0>}> : (!pdl.operation, !pdl.operation) -> ()
      "pdl.replace"(%11, %1) <{operandSegmentSizes = array<i32: 1, 1, 0>}> : (!pdl.operation, !pdl.operation) -> ()
    }) : (!pdl.operation) -> ()
  }) : () -> ()
}) : () -> ()
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    interpreter.run_op(pattern, ())
    # TODO: replace scope changes not implemented yet


@run_interpreter
def test_insertion_point_invalid_single_erase(ctx: MLContext, interpreter: Interpreter):
    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %2 = pdl.operation "pdltest.matchop"
    pdl.rewrite %2 {
      pdl.erase %2
      %new = pdl.operation "pdltest.rewriteop"
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(PDLAnalysisException, match="No valid insertion point set"):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_insertion_point_invalid_indirect(ctx: MLContext, interpreter: Interpreter):
    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %2 = pdl.operation "pdltest.matchop"
    pdl.rewrite %2 {
      %new = pdl.operation "pdltest.rewriteop"
      pdl.erase %2
      pdl.erase %new
      %new2 = pdl.operation "pdltest.rewriteop"
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(PDLAnalysisException, match="No valid insertion point set"):
        interpreter.run_op(pattern, ())


if __name__ == "__main__":
    for test in tests:
        test()
