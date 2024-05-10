"""
Translate a PDL rewrite with an IRDL specification to a program that checks if the
PDL rewrite is not breaking any IRDL invariants.
"""

import argparse
from re import Pattern
import sys

from xdsl.ir import MLContext
from xdsl.parser import Parser
from xdsl.rewriter import Rewriter

from xdsl.dialects.pdl import PDL, OperationOp, PatternOp, ResultOp, RewriteOp

from xdsl.dialects.builtin import Builtin
from xdsl.dialects.irdl import IRDL
from xdsl_pdl.dialects.irdl_extension import IRDLExtension


def get_pdl_rewrite_as_match(program: PatternOp):
    """
    Transform a PDL pattern operation to a form where the `pdl.rewrite` operation is
    applied to the matching part of the rewrite. Also, returns the
    """
    pass


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
    print(rewrite)
    add_missing_pdl_result(rewrite)
    print(rewrite)


if __name__ == "__main__":
    main()
