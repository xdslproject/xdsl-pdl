from typing import Callable

from xdsl.builder import Builder, ImplicitBuilder
from xdsl.dialects import arith
from xdsl.dialects.test import TestOp
from xdsl.dialects.builtin import ArrayAttr, IntegerAttr, ModuleOp, StringAttr, i32
from xdsl.interpreter import Interpreter
from xdsl.interpreters.experimental.pdl import PDLMatcher, PDLRewritePattern
from xdsl.ir import MLContext
from xdsl.pattern_rewriter import (
    PatternRewriter,
    PatternRewriteWalker,
    RewritePattern,
    op_type_rewrite_pattern,
)
from xdsl.utils.test_value import TestSSAValue as Val

from xdsl_pdl.dialects import pdl_extension as pdl
from xdsl_pdl.interpreters.pdl_interpreter_extension import PDLRewriteFunctionsExt

tests: list[Callable[[], None]] = []


def run(f: Callable[[], None]):
    def test():
        print("\nTEST:", f.__name__)
        f()

    tests.append(test)
    return f


@run
def test_pdl_result_op():
    interpreter = Interpreter(ModuleOp([]))
    interpreter.register_implementations(PDLRewriteFunctionsExt(MLContext()))

    add = arith.Addi(Val(i32), Val(i32))
    add_res = add.result

    assert interpreter.run_op(pdl.ResultOp(0, Val(pdl.OperationType())), (add,)) == (
        add_res,
    )


@run
def test_new_block():
    @ModuleOp
    @Builder.implicit_region
    def input_module_true():
        TestOp.create(properties={"attr": StringAttr("foo")})

    @ModuleOp
    @Builder.implicit_region
    def input_module_false():
        TestOp.create(properties={"attr": StringAttr("baar")})

    @ModuleOp
    @Builder.implicit_region
    def pdl_module():
        with ImplicitBuilder(pdl.PatternOp(42, None).body):
            attr = pdl.AttributeOp().output
            four = pdl.AttributeOp(IntegerAttr(4, i32)).output
            pdl.ApplyNativeConstraintOp("length_string", [attr, four])
            # These new ops are emitted by they do not have an implementation
            # in the interpreter yet
            blockArg = pdl.BlockArgOp().val
            block = pdl.BlockOp([blockArg])
            region = pdl.RegionOp([block])
            op = pdl.OperationOp(
                op_name=None,
                attribute_value_names=ArrayAttr([StringAttr("attr")]),
                attribute_values=[attr],
            ).op
            with ImplicitBuilder(pdl.RewriteOp(op).body):
                pdl.EraseOp(op)

    pdl_rewrite_op = next(
        op for op in pdl_module.walk() if isinstance(op, pdl.RewriteOp)
    )

    print(pdl_module)

    ctx = MLContext()
    interpreter = Interpreter(ModuleOp([]))
    interpreter.register_implementations(PDLRewriteFunctionsExt(MLContext()))

    PDLMatcher.native_constraints["length_string"] = (
        lambda attr, size: isinstance(attr, StringAttr)
        and isinstance(size, IntegerAttr)
        and len(attr.data) == size.value.data
    )

    pattern_walker = PatternRewriteWalker(PDLRewritePattern(pdl_rewrite_op, ctx))

    new_input_module_true = input_module_true.clone()
    pattern_walker.rewrite_module(new_input_module_true)

    new_input_module_false = input_module_false.clone()
    pattern_walker.rewrite_module(new_input_module_false)

    print(new_input_module_true)
    print(new_input_module_false)

    assert new_input_module_false.is_structurally_equivalent(ModuleOp([]))
    assert new_input_module_true.is_structurally_equivalent(input_module_true)


if __name__ == "__main__":
    for test_fun in tests:
        test_fun()
