from xdsl.parser import SymbolRefAttr
from xdsl.passes import ModulePass

from xdsl.ir import MLContext, Operation, SSAValue, Use
from xdsl.dialects import irdl
from xdsl.rewriter import InsertPoint
from xdsl_pdl.dialects import irdl_extension
from xdsl.dialects.builtin import ModuleOp
from xdsl.pattern_rewriter import (
    GreedyRewritePatternApplier,
    PatternRewriteWalker,
    PatternRewriter,
    RewritePattern,
    op_type_rewrite_pattern,
)


def all_of_has_base_of_type(op: irdl.AllOfOp, base_type: SymbolRefAttr) -> int | None:
    """Return the index of the first argument of `op` that is a `BaseOp` with the given `base_type`."""
    for index, arg in enumerate(op.args):
        if not isinstance(arg.owner, irdl.BaseOp):
            continue
        if arg.owner.base_ref == base_type:
            return index
    return None


class RemoveUnusedOpPattern(RewritePattern):
    def match_and_rewrite(self, op: Operation, rewriter: PatternRewriter, /):
        if op.dialect_name() == "irdl" and op.results:
            for result in op.results:
                if result.uses:
                    return
            rewriter.erase_op(op)


class AllOfSinglePattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        if len(op.args) == 1:
            rewriter.replace_matched_op([], [op.args[0]])
            return
        if len(op.args) == 0:
            rewriter.replace_matched_op(irdl.AnyOp())
            return


class AllOfIsPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for is_arg in op.args:
            if isinstance(is_arg.owner, irdl.IsOp):
                new_args = [
                    arg for arg in op.args if arg == is_arg or len(arg.uses) != 1
                ]
                rewriter.replace_matched_op(irdl.AllOfOp(new_args))
                return


class AllOfAnyPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for index, arg in enumerate(op.args):
            if isinstance(arg.owner, irdl.AnyOp) and len(arg.uses) == 1:
                rewriter.replace_matched_op(
                    irdl.AllOfOp(op.args[:index] + op.args[index + 1 :])
                )
                return


class AllOfBaseBasePattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for index, arg in enumerate(op.args):
            if not isinstance(arg.owner, irdl.BaseOp):
                continue
            if len(arg.uses) != 1:
                continue
            for arg2 in op.args[:index] + op.args[index + 1 :]:
                if not isinstance(arg2.owner, irdl.BaseOp):
                    continue
                if (
                    arg.owner.base_ref == arg2.owner.base_ref
                    and arg.owner.base_name == arg2.owner.base_name
                ):
                    rewriter.replace_matched_op(
                        irdl.AllOfOp(op.args[:index] + op.args[index + 1 :])
                    )
                    return


class AllOfParametricBasePattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for arg in op.args:
            if not isinstance(arg.owner, irdl.ParametricOp):
                continue
            for index2, arg2 in enumerate(op.args):
                if not isinstance(arg2.owner, irdl.BaseOp):
                    continue
                if len(arg2.uses) != 1:
                    continue
                if arg.owner.base_type == arg2.owner.base_ref:
                    rewriter.replace_matched_op(
                        irdl.AllOfOp(op.args[:index2] + op.args[index2 + 1 :])
                    )
                    return


class AllOfParametricParametricPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for index, arg in enumerate(op.args):
            if not isinstance(arg.owner, irdl.ParametricOp):
                continue
            for index2, arg2 in list(enumerate(op.args))[index + 1 :]:
                if not isinstance(arg2.owner, irdl.ParametricOp):
                    continue
                if arg.owner.base_type == arg2.owner.base_type:
                    args: list[SSAValue] = []
                    for param1, param2 in zip(arg.owner.args, arg2.owner.args):
                        param_all_of = irdl.AllOfOp([param1, param2])
                        rewriter.insert_op_before_matched_op(param_all_of)
                        args.append(param_all_of.output)
                    new_parametric = irdl.ParametricOp(arg.owner.base_type, args)
                    rewriter.replace_matched_op(
                        [
                            new_parametric,
                            irdl.AllOfOp(
                                [
                                    *op.args[:index],
                                    *op.args[index + 1 : index2],
                                    *op.args[index2 + 1 :],
                                    new_parametric.output,
                                ]
                            ),
                        ]
                    )
                    return


class AllOfIdenticalPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for index1, arg1 in enumerate(op.args):
            for arg2 in op.args[index1 + 1 :]:
                if arg1 == arg2:
                    rewriter.replace_matched_op(
                        irdl.AllOfOp(
                            [
                                arg
                                for index, arg in enumerate(op.args)
                                if index != index1
                            ]
                        )
                    )
                    return


class AllOfNestedPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for index, arg in enumerate(op.args):
            if not isinstance(arg.owner, irdl.AllOfOp):
                continue
            new_args = [*op.args[:index], *arg.owner.args, *op.args[index + 1 :]]
            rewriter.replace_matched_op(irdl.AllOfOp(new_args))
            return


class RemoveEqOpPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl_extension.EqOp, rewriter: PatternRewriter, /):
        if len(op.args) != 2:
            return
        lhs = op.args[0]
        rhs = op.args[1]
        assert isinstance(lhs.owner, Operation)
        assert isinstance(rhs.owner, Operation)
        assert lhs.owner.parent_block() == rhs.owner.parent_block()
        block = lhs.owner.parent_block()
        assert block is not None

        # Get the operation indices of the operands
        block_ops = list(block.ops)
        index_lhs = block_ops.index(lhs.owner)
        index_rhs = block_ops.index(rhs.owner)

        # Get the earliest operation using either operand
        earliest_use_index = None
        for index, block_op in enumerate(block_ops):
            if lhs in block_op.operands or rhs in block_op.operands:
                earliest_use_index = index
                break
        else:
            assert False

        # Merging both operations is harder in that case, so we don't do it for now
        if earliest_use_index < max(index_lhs, index_rhs):
            return

        # Get the latest operation
        if index_lhs > index_rhs:
            insert_point = InsertPoint.after(lhs.owner)
        else:
            insert_point = InsertPoint.after(rhs.owner)

        # Create a new `AllOfOp` with the operands of the `EqOp`
        all_of_op = irdl.AllOfOp([lhs, rhs])
        rewriter.insert_op_at_location(all_of_op, insert_point)

        # Erase the `EqOp`
        rewriter.erase_matched_op()

        # Replace uses of both operands with the `AllOfOp`
        # Do not replace the uses of the `AllOfOp` itself
        for use in [*lhs.uses, *rhs.uses]:
            if use.operation is all_of_op:
                continue
            operands = use.operation.operands
            use.operation.operands = [
                *operands[: use.index],
                all_of_op.output,
                *operands[use.index + 1 :],
            ]


class OptimizeIRDL(ModulePass):
    def apply(self, ctx: MLContext, op: ModuleOp):
        walker = PatternRewriteWalker(
            GreedyRewritePatternApplier(
                [
                    RemoveUnusedOpPattern(),
                    AllOfSinglePattern(),
                    AllOfIsPattern(),
                    AllOfAnyPattern(),
                    AllOfBaseBasePattern(),
                    AllOfParametricBasePattern(),
                    AllOfParametricParametricPattern(),
                    AllOfIdenticalPattern(),
                    RemoveEqOpPattern(),
                    AllOfNestedPattern(),
                ]
            )
        )
        walker.rewrite_op(op)
