from dataclasses import dataclass

from xdsl.ir import OpResult, Operation, Region, SSAValue, MLContext
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.pattern_rewriter import (
    GreedyRewritePatternApplier,
    PatternRewriteWalker,
    PatternRewriter,
    RewritePattern,
    op_type_rewrite_pattern,
)

from xdsl.dialects.pdl import (
    ApplyNativeConstraintOp,
    ApplyNativeRewriteOp,
    AttributeOp,
    OperandOp,
    OperationOp,
    PatternOp,
    ReplaceOp,
    ResultOp,
    RewriteOp,
    TypeOp,
)

from xdsl.dialects.builtin import SymbolRefAttr, ModuleOp
from xdsl.dialects import irdl
from xdsl_pdl.dialects.irdl_extension import CheckSubsetOp, EqOp, YieldOp


def add_missing_pdl_result(program: PatternOp):
    """
    Add `pdl.result` for each operation result that is missing it.
    """
    for op in program.body.walk():
        if not isinstance(op, OperationOp):
            continue
        num_results = len(op.type_values)
        if num_results == 0:
            continue
        results_found = [False] * num_results
        for use in op.op.uses:
            if isinstance(use.operation, ResultOp):
                if results_found[use.index]:
                    raise Exception(
                        "Error: multiple `pdl.result` found for the same operation and index"
                    )
                results_found[use.index] = True
        for index, found in enumerate(results_found):
            if not found:
                Rewriter.insert_op_after(op, ResultOp(index, op.op))


def convert_pattern_to_check_subset(program: PatternOp) -> CheckSubsetOp:
    """
    Transform a PDL pattern operation to a form where the `pdl.rewrite` operation is
    applied to the matching part of the rewrite.
    Returns this as a `irdl_extension.check_subset` operation, with PDL operations in
    both regions.
    """

    # Move the pdl pattern to the lhs of a check_subset operation
    check_subset = CheckSubsetOp(Region(), Region())
    program.body.clone_into(check_subset.lhs)
    program.body.clone_into(check_subset.rhs)

    # Remove the rewrite part of the lhs
    assert check_subset.lhs.ops.last is not None
    Rewriter.erase_op(check_subset.lhs.ops.last)

    # Get the rewrite part in the rhs
    rewrite = check_subset.rhs.ops.last
    assert isinstance(rewrite, RewriteOp)

    # Find the values that should be equivalent between the lhs and rhs
    yield_lhs_args: list[SSAValue] = []
    yield_rhs_args: list[SSAValue] = []
    for op_lhs, op_rhs in zip(check_subset.lhs.ops, check_subset.rhs.ops):
        if isinstance(op_lhs, ResultOp):
            assert isinstance(op_rhs, ResultOp)
            yield_lhs_args.append(op_lhs.val)
            yield_rhs_args.append(op_rhs.val)
            continue
        if isinstance(op_lhs, OperandOp):
            assert isinstance(op_rhs, OperandOp)
            yield_lhs_args.append(op_lhs.value)
            yield_rhs_args.append(op_rhs.value)
            continue

    Rewriter.insert_ops_at_location(
        [YieldOp(yield_lhs_args)], InsertPoint.at_end(check_subset.lhs.block)
    )
    Rewriter.insert_ops_at_location(
        [YieldOp(yield_rhs_args)], InsertPoint.at_end(check_subset.rhs.block)
    )

    # Start rewriting the PDL operations in the rhs part:
    assert rewrite.body is not None

    if (root := rewrite.root) is None:
        raise Exception("Error: expected a root operation in the rewrite")
    assert isinstance(root, OpResult)

    while (op := rewrite.body.ops.first) is not None:
        if isinstance(op, AttributeOp):
            op.detach()
            if op.value_type:
                assert isinstance(op.value_type, OpResult)
                Rewriter.insert_op_after(op.value_type.owner, op)
            else:
                Rewriter.insert_op_before(root.owner, op)
            continue
        if isinstance(op, TypeOp | OperationOp | ApplyNativeRewriteOp):
            op.detach()
            Rewriter.insert_op_before(root.owner, op)
            continue
        if isinstance(op, ResultOp):
            op.detach()
            assert isinstance(op.parent_, OpResult)
            Rewriter.insert_op_after(op.parent_.owner, op)
            continue
        if isinstance(op, ReplaceOp):
            matched_op_val = op.op_value
            assert isinstance(matched_op_val.owner, OperationOp)
            matched_op = matched_op_val.owner
            if (new_op_val := op.repl_operation) is not None:
                matched_op_val.replace_by(new_op_val)
                Rewriter.erase_op(matched_op)
            Rewriter.erase_op(op)
            continue

        raise Exception("Unsupported operation in the pdl rewrite: ", op.name)

    Rewriter.erase_op(rewrite)
    return check_subset


class PDLToIRDLTypePattern(RewritePattern):
    """
    Replace `pdl.type` to either `irdl.is` or `irdl.any`.
    """

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: TypeOp, rewriter: PatternRewriter, /):
        if op.constantType is None:
            rewriter.replace_matched_op(irdl.AnyOp())
            return
        rewriter.replace_matched_op(irdl.IsOp(op.constantType))


class PDLToIRDLOperandPattern(RewritePattern):
    """
    Replace `pdl.operand` to either `irdl.any`, or its type constraint.
    """

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: OperandOp, rewriter: PatternRewriter, /):
        if op.value_type is None:
            rewriter.replace_matched_op(irdl.AnyOp())
            return
        rewriter.replace_matched_op([], new_results=[op.value_type])


class PDLToIRDLAttributePattern(RewritePattern):
    """
    Replace `pdl.attribute` to `irdl.is`, `irdl.any`, or a constraint over an
    IntegerAttr. We assume that typed attributes are always IntegerAttr.
    """

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: AttributeOp, rewriter: PatternRewriter, /):
        # In the case of a constant attribute, we can replace it with an `irdl.is`
        # operation.
        if op.value is not None:
            rewriter.replace_matched_op(irdl.IsOp(op.value))
            return
        # In the case of an untyped attribute, we can replace it with an `irdl.any`
        if op.value_type is not None:
            value = irdl.AnyOp()
            rewriter.replace_matched_op(
                [
                    value,
                    irdl.ParametricOp(
                        SymbolRefAttr("builtin", ["integer_attr"]),
                        [value.output, op.value_type],
                    ),
                ]
            )
            return
        # Otherwise, it could by anything
        rewriter.replace_matched_op(irdl.AnyOp())


class PDLToIRDLNativeConstraintPattern(RewritePattern):
    """
    Remove `pdl.native_constraint` operations
    """

    @op_type_rewrite_pattern
    def match_and_rewrite(
        self, op: ApplyNativeConstraintOp, rewriter: PatternRewriter, /
    ):
        rewriter.erase_matched_op()


@dataclass
class PDLToIRDLOperationPattern(RewritePattern):
    """Replace `pdl.operation` to its constraints."""

    irdl_ops: dict[str, irdl.OperationOp]

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: OperationOp, rewriter: PatternRewriter, /):
        if op.opName is None:
            raise Exception("All PDL operations are expected to have a name.")
        if op.opName.data not in self.irdl_ops:
            raise Exception("Operation not found in IRDL: " + op.opName.data)
        irdl_op = self.irdl_ops[op.opName.data]

        # Grab the constraints corresponding to the operands and results
        irdl_operands = []
        irdl_results = []

        # Clone all the operation constraints
        cloned_op = irdl_op.clone()
        for constraint in list(cloned_op.body.ops):
            if isinstance(constraint, irdl.OperandsOp):
                irdl_operands = constraint.args
                continue
            if isinstance(constraint, irdl.ResultsOp):
                irdl_results = constraint.args
                continue
            constraint.detach()
            rewriter.insert_op_before_matched_op(constraint)

        cloned_op.erase()

        operand_matches = list(zip(irdl_operands, op.operand_values, strict=True))
        results_matches = list(zip(irdl_results, op.type_values, strict=True))

        # Merge irdl_operand and pdl_operand
        for irdl_operand, pdl_operand in [*operand_matches, *results_matches]:
            merge_op = EqOp([irdl_operand, pdl_operand])
            rewriter.insert_op_before_matched_op(merge_op)

        for uses in list(op.op.uses):
            if not isinstance(uses.operation, ResultOp):
                raise Exception("Expected a `pdl.result` operation")
            rewriter.replace_op(
                uses.operation, [], new_results=[results_matches[uses.index][1]]
            )
        rewriter.erase_matched_op()


class PDLToIRDLNativeRewritePattern(RewritePattern):
    """
    Replace `pdl.native_rewrite` operations with our hardcoded implementation.
    """

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: ApplyNativeRewriteOp, rewriter: PatternRewriter, /):
        if op.constraint_name.data == "get_zero":
            # We do not currently support the 0 part of the rewrite
            # We only say it is an integer_attr with the given type
            zero = irdl.AnyOp()
            res = irdl.ParametricOp(
                SymbolRefAttr("builtin", ["integer_attr"]), [zero.output, op.args[0]]
            )
            rewriter.replace_matched_op([zero, res])
            return
        raise Exception(f"Unknown native rewrite {op.constraint_name}")


def convert_pdl_match_to_irdl_match(
    program: Operation, irdl_ops: dict[str, irdl.OperationOp]
):
    """
    Convert PDL operations to IRDL operations in the given program.
    """
    walker = PatternRewriteWalker(
        GreedyRewritePatternApplier(
            [
                PDLToIRDLTypePattern(),
                PDLToIRDLOperandPattern(),
                PDLToIRDLAttributePattern(),
                PDLToIRDLNativeConstraintPattern(),
                PDLToIRDLOperationPattern(irdl_ops),
                PDLToIRDLNativeRewritePattern(),
            ]
        )
    )
    walker.rewrite_op(program)


class PDLToIRDLPass(ModulePass):
    def apply(self, ctx: MLContext, op: ModuleOp):
        # Grab the rewrite operation which should be the last one
        rewrite = op.ops.last
        if not isinstance(rewrite, PatternOp):
            raise Exception(
                "Error: expected a PDL pattern operation as "
                "the last operation in the program",
            )

        # Grab the IRDL operations that exist in the program
        irdl_ops: dict[str, irdl.OperationOp] = {}
        for op_op in op.walk():
            if not isinstance(op_op, irdl.OperationOp):
                continue
            assert isinstance((parent := op_op.parent_op()), irdl.DialectOp)
            name = parent.sym_name.data + "." + op_op.sym_name.data
            irdl_ops[name] = op_op

        # Add `pdl.result` operation for each `pdl.operation` result.
        # This simplifies the following transformations.
        add_missing_pdl_result(rewrite)

        # Convert the PDL pattern to a `irdl_extension.check_subset`
        # operation that still uses PDL operations.
        # This executes the rewrite on PDL itself
        check_subset = convert_pattern_to_check_subset(rewrite)
        Rewriter.replace_op(rewrite, check_subset)

        # Convert the remaining PDL operations to IRDL operations
        convert_pdl_match_to_irdl_match(check_subset, irdl_ops)
