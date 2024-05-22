from typing import TypeAlias
from xdsl.parser import SymbolRefAttr
from xdsl.passes import ModulePass

from xdsl.ir import Attribute, MLContext, Operation, SSAValue
from xdsl.dialects import irdl
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.traits import IsTerminator
from z3 import v
from xdsl_pdl.dialects import irdl_extension
from xdsl.dialects.builtin import ModuleOp, StringAttr
from xdsl.pattern_rewriter import (
    GreedyRewritePatternApplier,
    PatternRewriteWalker,
    PatternRewriter,
    RewritePattern,
    op_type_rewrite_pattern,
)

BaseInfo: TypeAlias = set[SymbolRefAttr | str] | None


def meet_bases(bases_lhs: BaseInfo, bases_rhs: BaseInfo) -> BaseInfo:
    if bases_lhs is None:
        return bases_rhs
    if bases_rhs is None:
        return bases_lhs
    return bases_lhs & bases_rhs


def join_bases(bases_lhs: BaseInfo, bases_rhs: BaseInfo) -> BaseInfo:
    if bases_lhs is None or bases_rhs is None:
        return None
    return bases_lhs | bases_rhs


def get_bases(value: SSAValue) -> set[SymbolRefAttr | str] | None:
    if not isinstance(value.owner, Operation):
        return None
    op = value.owner
    if isinstance(op, irdl.BaseOp):
        if op.base_ref is not None:
            return {op.base_ref}
        assert op.base_name is not None
        return {op.base_name.data}
    if isinstance(op, irdl.ParametricOp):
        return {op.base_type}
    if isinstance(op, irdl.AnyOp):
        return None
    if isinstance(op, irdl.AllOfOp):
        bases: BaseInfo = None
        for arg in op.args:
            bases = meet_bases(bases, get_bases(arg))
        return bases
    if isinstance(op, irdl.AnyOfOp):
        bases: BaseInfo = None
        for arg in op.args:
            bases = join_bases(bases, get_bases(arg))
        return bases
    if isinstance(op, irdl.IsOp):
        # TODO: Add support for known types
        if isinstance(op.expected, StringAttr):
            return {"#builtin.string"}
        return None


def is_pure(value: SSAValue) -> bool:
    if isinstance(value.owner, irdl.IsOp):
        return True
    if isinstance(value.owner, irdl.ParametricOp):
        return all(is_pure(arg) for arg in value.owner.args)
    return False


def is_rooted_dag_with_one_use(value: SSAValue) -> bool:
    if is_pure(value):
        return True
    assert isinstance(value.owner, Operation)
    if len(value.uses) != 1:
        return False

    values_to_walk = [value]
    walked_values = {value}

    operations: list[Operation] = []

    while values_to_walk:
        value_to_walk = values_to_walk.pop()
        assert isinstance(value_to_walk.owner, Operation)
        operations.append(value_to_walk.owner)
        for operand in value_to_walk.owner.operands:
            if operand in walked_values:
                continue
            walked_values.add(operand)
            values_to_walk.append(operand)

    for operation in operations:
        assert len(operation.results) == 1
        if operation.results[0] == value:
            continue
        if is_pure(operation.results[0]):
            continue
        for use in operation.results[0].uses:
            if use.operation not in operations:
                return False

    return True


def match_attribute(
    value: SSAValue, attr: Attribute, mappings: dict[SSAValue, Attribute] = {}
) -> bool:
    if value in mappings:
        return mappings[value] == attr
    if isinstance(value.owner, irdl.IsOp):
        return value.owner.expected == attr
    if isinstance(value.owner, irdl.AnyOfOp):
        for arg in value.owner.args:
            if match_attribute(arg, attr, mappings):
                mappings[value] = attr
                return True
        return False
    assert False


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


class AnyOfSinglePattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AnyOfOp, rewriter: PatternRewriter, /):
        if len(op.args) == 1:
            rewriter.replace_matched_op([], [op.args[0]])
            return


class AllOfIsPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        is_op: Operation
        for is_arg in op.args:
            if isinstance(is_arg.owner, irdl.IsOp):
                is_op = is_arg.owner
                break
        else:
            return

        new_args: list[SSAValue] = []
        for arg in op.args:
            if arg == is_arg:
                new_args.append(arg)
                continue
            if not is_rooted_dag_with_one_use(arg):
                new_args.append(arg)
                continue
            if match_attribute(is_arg, is_op.expected):
                continue

            # Contradiction in the AllOf
            rewriter.replace_matched_op(irdl.AnyOfOp([]))
            return

        if len(new_args) == len(op.args):
            return
        rewriter.replace_matched_op(irdl.AllOfOp(new_args))


def is_dag_equivalent(
    val1: SSAValue, val2: SSAValue, mappings: dict[SSAValue, SSAValue] | None = None
):
    if mappings is None:
        mappings = {}
    if val1 in mappings:
        return mappings[val1] == val2

    assert isinstance(val1.owner, Operation)
    assert isinstance(val2.owner, Operation)
    op1 = val1.owner
    op2 = val2.owner

    if op1 == op2:
        return True

    if op1.attributes != op2.attributes:
        return False

    if len(op1.operands) != len(op2.operands):
        return False
    for operand1, operand2 in zip(op1.operands, op2.operands, strict=True):
        if not is_dag_equivalent(operand1, operand2, mappings):
            return False
    mappings[val1] = val2
    return True


class AllOfEquivPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for index, arg in enumerate(op.args):
            if not is_rooted_dag_with_one_use(arg):
                continue
            for index2, arg2 in list(enumerate(op.args))[index + 1 :]:
                if not is_rooted_dag_with_one_use(arg2):
                    continue
                if not is_dag_equivalent(arg, arg2):
                    continue

                rewriter.replace_matched_op(
                    irdl.AllOfOp(
                        [
                            *op.args[:index2],
                            *op.args[index2 + 1 :],
                        ]
                    )
                )
                return


class AnyOfEquivPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AnyOfOp, rewriter: PatternRewriter, /):
        for index, arg in enumerate(op.args):
            if not is_rooted_dag_with_one_use(arg):
                continue
            for index2, arg2 in list(enumerate(op.args))[index + 1 :]:
                if not is_rooted_dag_with_one_use(arg2):
                    continue
                if not is_dag_equivalent(arg, arg2):
                    continue

                rewriter.replace_matched_op(
                    irdl.AnyOfOp(
                        [
                            *op.args[:index2],
                            *op.args[index2 + 1 :],
                        ]
                    )
                )
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


class AnyOfNestedPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AnyOfOp, rewriter: PatternRewriter, /):
        for index, arg in enumerate(op.args):
            if not isinstance(arg.owner, irdl.AnyOfOp):
                continue
            new_args = [*op.args[:index], *arg.owner.args, *op.args[index + 1 :]]
            rewriter.replace_matched_op(irdl.AnyOfOp(new_args))
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


class NestAllOfInAnyOfPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for index, arg in enumerate(op.args):
            if not isinstance(arg.owner, irdl.AnyOfOp):
                continue
            if len(arg.owner.output.uses) != 1:
                continue
            new_all_ofs: list[irdl.AllOfOp] = []
            for any_of_arg in arg.owner.args:
                new_all_ofs.append(
                    irdl.AllOfOp([*op.args[:index], any_of_arg, *op.args[index + 1 :]])
                )
            rewriter.insert_op_before_matched_op(new_all_ofs)
            rewriter.replace_matched_op(
                irdl.AnyOfOp([new_all_of.output for new_all_of in new_all_ofs])
            )
            return


class RemoveAllOfContradictionPatterns(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        bases = get_bases(op.output)
        if bases == set():
            rewriter.replace_matched_op(irdl.AnyOfOp([]))

        is_value = None
        for arg in op.args:
            if not isinstance(arg.owner, irdl.IsOp):
                continue
            if is_value is None:
                is_value = arg.owner.expected
                continue
            if is_value != arg.owner.expected:
                rewriter.replace_matched_op(irdl.AnyOfOp([]))
                return


class RemoveBaseFromAllOfInNestedAnyOfPattern(RewritePattern):
    """
    On a pattern like this: "AllOf(AnyOf(y, z), x)", if the AnyOf is only used in
    the AllOf, we can remove y or z if their bases are incompatible with x.
    """

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AllOfOp, rewriter: PatternRewriter, /):
        for any_of_arg in op.args:
            if not isinstance(any_of_arg.owner, irdl.AnyOfOp):
                continue
            if not is_rooted_dag_with_one_use(any_of_arg):
                continue

            for arg in op.args:
                if arg == any_of_arg:
                    continue
                bases = get_bases(arg)
                if bases is None:
                    continue
                new_any_of_args: list[SSAValue] = []
                for arg_any_of in any_of_arg.owner.args:
                    if meet_bases(bases, get_bases(arg_any_of)) != set():
                        new_any_of_args.append(arg_any_of)
                if len(new_any_of_args) == len(any_of_arg.owner.args):
                    continue
                rewriter.replace_op(any_of_arg.owner, irdl.AnyOfOp(new_any_of_args))
                return


class RemoveDuplicateAnyOfAllOfPattern(RewritePattern):
    # AnyOf(AllOf(x, y), AllOf(x, y), z) -> AnyOf(AllOf(x, y), z)

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: irdl.AnyOfOp, rewriter: PatternRewriter, /):
        for index, arg in enumerate(op.args):
            if not isinstance(arg.owner, irdl.AllOfOp) or not len(arg.uses) == 1:
                continue
            for index2, arg2 in list(enumerate(op.args))[index + 1 :]:
                if not isinstance(arg2.owner, irdl.AllOfOp) or not len(arg2.uses) == 1:
                    continue
                if arg.owner.args == arg2.owner.args:
                    rewriter.replace_matched_op(
                        irdl.AnyOfOp(
                            [
                                *op.args[:index2],
                                *op.args[index2 + 1 :],
                            ]
                        )
                    )
                    return


class RemoveDuplicateMatchOpPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(
        self, op: irdl_extension.CheckSubsetOp, rewriter: PatternRewriter, /
    ):
        for block in [op.lhs.block, op.rhs.block]:
            match_ops: list[irdl_extension.MatchOp] = []
            for match_op in block.ops:
                if isinstance(match_op, irdl_extension.MatchOp):
                    match_ops.append(match_op)

            if not match_ops:
                return

            # Detach the match operations
            for match_op in match_ops:
                match_op.detach()

            # Deduplicate them
            dedup_match_ops: list[irdl_extension.MatchOp | None] = list(match_ops)
            for index, match_op in enumerate(dedup_match_ops):
                if match_op is None:
                    continue
                for index2, match_op2 in list(enumerate(dedup_match_ops))[index + 1 :]:
                    if match_op2 is None:
                        continue
                    if match_op.arg == match_op2.arg:
                        match_op2.erase()
                        dedup_match_ops[index2] = None

            if None not in dedup_match_ops:
                return

            deduped_match_ops = [
                match_op for match_op in dedup_match_ops if match_op is not None
            ]
            if block.ops.last is not None and block.ops.last.has_trait(IsTerminator):
                Rewriter.insert_ops_at_location(
                    deduped_match_ops, InsertPoint.before(block.ops.last)
                )
            else:
                Rewriter.insert_ops_at_location(
                    deduped_match_ops, InsertPoint.at_end(block)
                )


class CSEIsParametricPattern(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(
        self, op: irdl.IsOp | irdl.ParametricOp, rewriter: PatternRewriter, /
    ):
        current_op = op.next_op
        while current_op is not None:
            if (
                current_op.name == op.name
                and list(current_op.operands) == list(op.operands)
                and current_op.attributes == op.attributes
            ):
                rewriter.replace_op(current_op, [], [op.output])
                return
            current_op = current_op.next_op


class OptimizeIRDL(ModulePass):
    def apply(self, ctx: MLContext, op: ModuleOp):
        walker = PatternRewriteWalker(
            GreedyRewritePatternApplier(
                [
                    RemoveUnusedOpPattern(),
                    AllOfSinglePattern(),
                    AnyOfSinglePattern(),
                    AllOfAnyPattern(),
                    AllOfBaseBasePattern(),
                    AllOfParametricBasePattern(),
                    AllOfParametricParametricPattern(),
                    AllOfIdenticalPattern(),
                    RemoveEqOpPattern(),
                    AllOfNestedPattern(),
                    AnyOfNestedPattern(),
                    # NestAllOfInAnyOfPattern(),
                    AllOfEquivPattern(),
                    AnyOfEquivPattern(),
                    AllOfIsPattern(),
                    RemoveAllOfContradictionPatterns(),
                    RemoveDuplicateAnyOfAllOfPattern(),
                    RemoveBaseFromAllOfInNestedAnyOfPattern(),
                    RemoveDuplicateMatchOpPattern(),
                    CSEIsParametricPattern(),
                ]
            )
        )

        walker.rewrite_op(op)
