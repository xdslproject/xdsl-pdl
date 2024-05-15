"""
Translate a PDL rewrite with an IRDL specification to a program that checks if the
PDL rewrite is not breaking any IRDL invariants.
"""

import argparse
from re import Pattern
import sys

from xdsl.ir import MLContext, OpResult, Region, SSAValue
from xdsl.parser import Parser
from xdsl.rewriter import InsertPoint, Rewriter

from xdsl.dialects.pdl import (
    PDL,
    AttributeOp,
    OperandOp,
    OperationOp,
    PatternOp,
    ReplaceOp,
    ResultOp,
    RewriteOp,
    TypeOp,
)

from xdsl.dialects.builtin import Builtin
from xdsl.dialects.irdl import IRDL
from xdsl_pdl.dialects.irdl_extension import CheckSubsetOp, IRDLExtension, YieldOp


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
                    print(
                        "Error: multiple `pdl.result` found for the same operation and index",
                        sys.stderr,
                    )
                    exit(1)
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
        print("Error: expected a root operation in the rewrite", file=sys.stderr)
        exit(1)
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
        if isinstance(op, TypeOp):
            op.detach()
            Rewriter.insert_op_before(root.owner, op)
            continue
        if isinstance(op, OperationOp):
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

        print(check_subset)
        print("Unsupported operation in the pdl rewrite: ", op.name, file=sys.stderr)
        exit(1)

    Rewriter.erase_op(rewrite)
    return check_subset


def main():
    arg_parser = argparse.ArgumentParser(
        prog="pdl-to-irdl-check",
        description="Translate a PDL rewrite with an IRDL specification to a program that "
        "checks if the PDL rewrite is not breaking any IRDL invariants",
    )
    arg_parser.add_argument(
        "input_file", type=str, nargs="?", help="path to input file"
    )
    args = arg_parser.parse_args()

    # Setup the xDSL context
    ctx = MLContext()
    ctx.load_dialect(Builtin)
    ctx.load_dialect(IRDL)
    ctx.load_dialect(IRDLExtension)
    ctx.load_dialect(PDL)

    # Grab the input program from the command line or a file
    if args.input_file is None:
        f = sys.stdin
    else:
        f = open(args.input_file)

    # Parse the input program
    with f:
        program = Parser(ctx, f.read()).parse_module()

    rewrite = program.ops.last
    if not isinstance(rewrite, PatternOp):
        print(
            "Error: expected a PDL pattern operation as "
            "the last operation in the program",
            sys.stderr,
        )
        exit(1)

    # Add `pdl.result` operation for each `pdl.operation`.
    # This allows us to easily map the input values to the output values.
    add_missing_pdl_result(rewrite)
    print(convert_pattern_to_check_subset(rewrite))


if __name__ == "__main__":
    main()
