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
    DataKeys,
    PDLAnalysisFunctions,
    PDLAnalysisException,
    PDLAnalysisAborted,
    UseCheckingStrictness,
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
def test_disconnected_matching_op(ctx: MLContext, interpreter: Interpreter):
    """ """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %disconnected = pdl.operation "pdltest.matchop"
    %root = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    pdl.rewrite %root {
      %new = pdl.operation "pdltest.rewriteop" -> (%type : !pdl.type)
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(PDLAnalysisAborted, match="not a connected component"):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_disconnected_matching_result_allowed(ctx: MLContext, interpreter: Interpreter):
    """
    This tests that taking a pdl.result from an op without it being used in the
    matching part is allowed.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %root = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    %disconnected = pdl.result 0 of %root
    pdl.rewrite %root {
      %new = pdl.operation "pdltest.rewriteop"
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    interpreter.run_op(pattern, ())


@run_interpreter
def test_disconnected_matching_type(ctx: MLContext, interpreter: Interpreter):
    """ """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %disconnected = pdl.type
    %root = pdl.operation "pdltest.matchop"
    pdl.rewrite %root {
      %new = pdl.operation "pdltest.rewriteop"
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(PDLAnalysisAborted, match="not a connected component"):
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
    with pytest.raises(PDLAnalysisAborted, match="operand not in scope"):
        PDLAnalysisFunctions.set_state(
            interpreter,
            DataKeys.USE_CHECKING_STRICTNESS,
            UseCheckingStrictness.ASSUME_NO_USE_OUTSIDE,
        )
        interpreter.run_op(pattern, ())


@run_interpreter
def test_erase_strict(ctx: MLContext, interpreter: Interpreter):
    """
    This erases the root op which might have uses outside of the matched IR.
    This should fail.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %root = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    pdl.rewrite %root {
      pdl.erase %root
    }
  }
}
"""

    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(
        PDLAnalysisAborted, match="Op might have uses outside of the matched IR"
    ):
        PDLAnalysisFunctions.set_state(
            interpreter, DataKeys.USE_CHECKING_STRICTNESS, UseCheckingStrictness.STRICT
        )
        interpreter.run_op(pattern, ())


@run_interpreter
def test_erase_strict_but_no_uses(ctx: MLContext, interpreter: Interpreter):
    """
    This is similar to the test above, except the erased op has no uses. This
    should succeed
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %root = pdl.operation "pdltest.matchop"
    pdl.rewrite %root {
      pdl.erase %root
    }
  }
}
"""

    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    PDLAnalysisFunctions.set_state(
        interpreter, DataKeys.USE_CHECKING_STRICTNESS, UseCheckingStrictness.STRICT
    )
    interpreter.run_op(pattern, ())


@run_interpreter
def test_double_replace(ctx: MLContext, interpreter: Interpreter):
    program = """
"builtin.module"() ({
  "pdl.pattern"() <{benefit = 1 : i16}> ({
    %0 = "pdl.type"() <{constantType = i1}> : () -> !pdl.type
    %1 = "pdl.operation"(%0) <{attributeValueNames = [], opName = "pdltest.matchop", operandSegmentSizes = array<i32: 0, 0, 1>}> : (!pdl.type) -> !pdl.operation
    %2 = "pdl.result"(%1) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
    %3 = "pdl.type"() <{constantType = i2}> : () -> !pdl.type
    %4 = "pdl.operand"(%3) : (!pdl.type) -> !pdl.value
    %5 = "pdl.type"() <{constantType = i4}> : () -> !pdl.type
    %6 = "pdl.type"() <{constantType = i8}> : () -> !pdl.type
    %7 = "pdl.operation"(%4, %2, %5, %6) <{attributeValueNames = [], opName = "pdltest.matchop", operandSegmentSizes = array<i32: 2, 0, 2>}> : (!pdl.value, !pdl.value, !pdl.type, !pdl.type) -> !pdl.operation
    %8 = "pdl.result"(%7) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
    %9 = "pdl.result"(%7) <{index = 1 : i32}> : (!pdl.operation) -> !pdl.value
    "pdl.rewrite"(%7) <{operandSegmentSizes = array<i32: 1, 0>}> ({
      %10 = "pdl.type"() <{constantType = i16}> : () -> !pdl.type
      %11 = "pdl.operation"(%10) <{attributeValueNames = [], opName = "pdltest.rewriteop", operandSegmentSizes = array<i32: 0, 0, 1>}> : (!pdl.type) -> !pdl.operation
      %12 = "pdl.result"(%11) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
      "pdl.replace"(%11, %1) <{operandSegmentSizes = array<i32: 1, 1, 0>}> : (!pdl.operation, !pdl.operation) -> ()
      //"pdl.replace"(%11, %1) <{operandSegmentSizes = array<i32: 1, 1, 0>}> : (!pdl.operation, !pdl.operation) -> ()
      //%13 = "pdl.operation"(%12) <{attributeValueNames = [], opName = "pdltest.rewriteop", operandSegmentSizes = array<i32: 1, 0, 0>}> : (!pdl.value) -> !pdl.operation


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
    with pytest.raises(PDLAnalysisAborted, match="No valid insertion point set"):
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
    with pytest.raises(PDLAnalysisAborted, match="No valid insertion point set"):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_invalid_op_erased_later(ctx: MLContext, interpreter: Interpreter):
    """
    This tests whether a newly generated invalid op that is erased later
    triggers an error. This should succeed as dominance in MLIR is only checked
    on the final IR.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %root = pdl.operation "pdltest.matchop"-> (%type : !pdl.type)
    %root_res = pdl.result 0 of %root
    pdl.rewrite %root {
      %invalid = pdl.operation "pdltest.rewriteop" (%root_res : !pdl.value)
      pdl.erase %invalid
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    # with pytest.raises(PDLAnalysisAborted, match="No valid insertion point set"):
    interpreter.run_op(pattern, ())


@run_interpreter
def test_remove_related_from_scope_erase_op(ctx: MLContext, interpreter: Interpreter):
    program = """
"builtin.module"() ({
  "pdl.pattern"() <{benefit = 1 : i16}> ({
    %0 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %1 = "pdl.operation"(%0) <{attributeValueNames = [], opName = "pdltest.matchop", operandSegmentSizes = array<i32: 0, 0, 1>}> : (!pdl.type) -> !pdl.operation
    %2 = "pdl.result"(%1) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
    "pdl.rewrite"(%1) <{operandSegmentSizes = array<i32: 1, 0>}> ({
        "pdl.erase"(%1) : (!pdl.operation) -> ()
        %11 = "pdl.operation"(%2) <{attributeValueNames = [], opName = "pdltest.rewriteop", operandSegmentSizes = array<i32: 0, 1, 0>}> : (!pdl.value) -> !pdl.operation
    }) : (!pdl.operation) -> ()
  }) : () -> ()
}) : () -> ()
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(PDLAnalysisAborted, match="operand not in scope"):
        PDLAnalysisFunctions.set_state(
            interpreter,
            DataKeys.USE_CHECKING_STRICTNESS,
            UseCheckingStrictness.ASSUME_NO_USE_OUTSIDE,
        )
        interpreter.run_op(pattern, ())


@run_interpreter
def test_remove_related_from_scope_replace_val(
    ctx: MLContext, interpreter: Interpreter
):
    """
    This test replaces the root op with a value and then tries to use the result
    of the root op as operand for anther op. This should fail.
    """

    program = """
"builtin.module"() ({
  "pdl.pattern"() <{benefit = 1 : i16}> ({
    %0 = "pdl.type"() <{constantType = i32}> : () -> !pdl.type
    %operand = "pdl.operand"(%0) : (!pdl.type) -> !pdl.value
    %1 = "pdl.operation"(%operand, %0) <{attributeValueNames = [], opName = "pdltest.matchop", operandSegmentSizes = array<i32: 1, 0, 1>}> : (!pdl.value, !pdl.type) -> !pdl.operation
    %2 = "pdl.result"(%1) <{index = 0 : i32}> : (!pdl.operation) -> !pdl.value
    "pdl.rewrite"(%1) <{operandSegmentSizes = array<i32: 1, 0>}> ({
        "pdl.replace"(%1, %operand) <{operandSegmentSizes = array<i32: 1, 0, 1>}> : (!pdl.operation, !pdl.value) -> ()
        %11 = "pdl.operation"(%2) <{attributeValueNames = [], opName = "pdltest.rewriteop", operandSegmentSizes = array<i32: 0, 1, 0>}> : (!pdl.value) -> !pdl.operation
    }) : (!pdl.operation) -> ()
  }) : () -> ()
}) : () -> ()
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(PDLAnalysisAborted, match="operand not in scope"):
        PDLAnalysisFunctions.set_state(
            interpreter,
            DataKeys.USE_CHECKING_STRICTNESS,
            UseCheckingStrictness.ASSUME_NO_USE_OUTSIDE,
        )
        interpreter.run_op(pattern, ())


@run_interpreter
def test_replace(ctx: MLContext, interpreter: Interpreter):
    """
    This checks whether replacing an op with another op works. This should
    succeed.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %_ = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    pdl.rewrite %_ {

      %A = pdl.operation "pdltest.rewriteop1" -> (%type : !pdl.type)
      %a = pdl.result 0 of %A
      %B = pdl.operation "pdltest.rewriteop2" -> (%type : !pdl.type)

      %user = pdl.operation "pdltest.rewriteop3"(%a : !pdl.value) -> (%type : !pdl.type)
      pdl.replace %A with %B
    }
  }
}
"""

    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    # with pytest.raises(PDLAnalysisAborted, match="still has 1 uses"):
    interpreter.run_op(pattern, ())


@run_interpreter
def test_replace_and_invalid_erase(ctx: MLContext, interpreter: Interpreter):
    """
    This checks whether the uses are correctly updated when an op is replaced.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %_ = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    pdl.rewrite %_ {

      %A = pdl.operation "pdltest.rewriteop1" -> (%type : !pdl.type)
      %a = pdl.result 0 of %A
      %B = pdl.operation "pdltest.rewriteop2" -> (%type : !pdl.type)

      %user = pdl.operation "pdltest.rewriteop3"(%a : !pdl.value) -> (%type : !pdl.type)
      pdl.replace %A with %B
      pdl.erase %B
    }
  }
}
"""

    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(PDLAnalysisAborted, match="still has 1 uses"):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_replace_multiple_times(ctx: MLContext, interpreter: Interpreter):
    """
    This checks whether the uses are correctly updated when an op is replaced.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %_ = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    pdl.rewrite %_ {

      %A = pdl.operation "pdltest.rewriteop1" -> (%type : !pdl.type)
      %a = pdl.result 0 of %A
      %B = pdl.operation "pdltest.rewriteop2" -> (%type : !pdl.type)
      %C = pdl.operation "pdltest.rewriteop3" -> (%type : !pdl.type)
      %user = pdl.operation "pdltest.rewriteop4"(%a : !pdl.value) -> (%type : !pdl.type)
      pdl.replace %A with %B
      pdl.replace %B with %C
    }
  }
}
"""

    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    # with pytest.raises(PDLAnalysisAborted, match="still has 1 uses"):
    interpreter.run_op(pattern, ())


@run_interpreter
def test_replace_with_self(ctx: MLContext, interpreter: Interpreter):
    """ """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %root = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    pdl.rewrite %root {
      pdl.replace %root with %root
    }
  }
}
"""

    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(
        PDLAnalysisAborted, match="Op might have uses outside of the matched IR"
    ):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_root_replacement(ctx: MLContext, interpreter: Interpreter):
    """ """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %root = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    pdl.rewrite %root {
      %new = pdl.operation "pdltest.rewriteop" -> (%type : !pdl.type)
      pdl.replace %root with %new
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    interpreter.run_op(pattern, ())


@run_interpreter
def test_still_in_use(ctx: MLContext, interpreter: Interpreter):
    """
    This test erases an op that is still in use. As the op is generated in this
    rewrite we know that it has exactly this use. This should fail.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %2 = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    pdl.rewrite %2 {
      %new = pdl.operation "pdltest.rewriteop" -> (%type : !pdl.type)
      %new_res = pdl.result 0 of %new
      %user = pdl.operation "pdltest.rewriteop"(%new_res : !pdl.value)
      pdl.erase %new
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(PDLAnalysisAborted, match="still has 1 uses"):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_still_in_use_repaired(ctx: MLContext, interpreter: Interpreter):
    """
    This test is the same as test_still_in_use but the one use of the op to be
    erased is removed before the erase. This should succeed.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %2 = pdl.operation "pdltest.matchop" -> (%type : !pdl.type)
    pdl.rewrite %2 {
      %new = pdl.operation "pdltest.rewriteop" -> (%type : !pdl.type)
      %new_res = pdl.result 0 of %new
      %user = pdl.operation "pdltest.rewriteop"(%new_res : !pdl.value)
      pdl.erase %user
      pdl.erase %new
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    interpreter.run_op(pattern, ())


@run_interpreter
def test_replace_terminator(ctx: MLContext, interpreter: Interpreter):
    """
    This test checks that the replacement of a terminator op with a non-terminator
    op is not allowed.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %2 = pdl.operation "pdltest.terminator" -> (%type : !pdl.type)
    pdl.rewrite %2 {
      %new = pdl.operation "pdltest.rewriteop" -> (%type : !pdl.type)
      pdl.replace %2 with %new
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(
        PDLAnalysisAborted, match="Replacing a terminator with a non-terminator."
    ):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_replace_terminator_with_values(ctx: MLContext, interpreter: Interpreter):
    """
    This test checks that the replacement of a terminator op with a non-terminator
    op is not allowed.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %type = pdl.type
    %2 = pdl.operation "pdltest.terminator" -> (%type : !pdl.type)
    pdl.rewrite %2 {
      %new = pdl.operation "pdltest.rewriteop" -> (%type : !pdl.type)
      %new_res = pdl.result 0 of %new
      pdl.replace %2 with (%new_res : !pdl.value)
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(
        PDLAnalysisAborted, match="Replacing a terminator with a non-terminator."
    ):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_erase_terminator(ctx: MLContext, interpreter: Interpreter):
    """
    This test checks that the erasure of a terminator op is not allowed.
    """

    program = """
builtin.module {
  pdl.pattern : benefit(1) {
    %2 = pdl.operation "pdltest.terminator"
    pdl.rewrite %2 {
      pdl.erase %2
    }
  }
}
"""
    parser = Parser(ctx=ctx, input=program)
    module = parser.parse_op()
    assert isinstance(module, ModuleOp)
    pattern = module.body.ops.first
    with pytest.raises(
        PDLAnalysisAborted, match="Erasing a terminator is not allowed."
    ):
        interpreter.run_op(pattern, ())


@run_interpreter
def test_insert_after_terminator(ctx: MLContext, interpreter: Interpreter):
    """
    This test checks that ops cannot be inserted after a terminator op.
    """
    # Question: Is this even possible with insertion before the root op?
    # This can never happen, as we always insert ops before the matched root op.
    # New ops we insert can never be terminators, as we can not construct them
    # (No way to specifiy successors)


if __name__ == "__main__":
    for test in tests:
        test()
