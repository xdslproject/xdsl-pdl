"""
Verify that a PDL rewrite satisfies the constraints of the IRDL description of the
dialects.
"""

import argparse
import sys
import z3

from xdsl.ir import MLContext
from xdsl.parser import Parser
from xdsl.rewriter import Rewriter
from xdsl_pdl.analysis.check_subset_to_z3 import check_subset_to_z3
from xdsl_pdl.dialects.irdl_extension import IRDLExtension
from xdsl_pdl.dialects.transfer import Transfer

from xdsl.dialects.builtin import (
    Builtin,
    ModuleOp,
)
from xdsl.dialects.irdl import IRDL
from xdsl.dialects.pdl import PDL, PatternOp
from xdsl_pdl.passes.optimize_irdl import OptimizeIRDL
from xdsl_pdl.passes.pdl_to_irdl import PDLToIRDLPass


def main():
    arg_parser = argparse.ArgumentParser(
        prog="pdl-to-irdl-check",
        description="Translate a PDL rewrite with an IRDL specification to a program that "
        "checks if the PDL rewrite is not breaking any IRDL invariants",
    )
    arg_parser.add_argument("input_file", type=str, help="path to input file")
    arg_parser.add_argument("irdl_file", type=str, help="path to IRDL file")
    arg_parser.add_argument("--debug", action="store_true", help="enable debug mode")
    args = arg_parser.parse_args()

    # Setup the xDSL context
    ctx = MLContext()
    ctx.load_dialect(Builtin)
    ctx.load_dialect(IRDL)
    ctx.load_dialect(IRDLExtension)
    ctx.load_dialect(PDL)
    ctx.load_dialect(Transfer)

    # Parse the input program
    with open(args.input_file) as f:
        all_patterns_program = Parser(ctx, f.read()).parse_module()

    # Parse the IRDL program
    with open(args.irdl_file) as f:
        irdl_program = Parser(ctx, f.read()).parse_module()

    has_broken_pattern = False
    for pattern_op in (
        op for op in all_patterns_program.ops if isinstance(op, PatternOp)
    ):
        print("Pattern ", pattern_op.sym_name)
        program = ModuleOp([pattern_op.clone()])

        # Move the IRDL file at the beginning of the program
        Rewriter.inline_block_at_start(
            irdl_program.clone().regions[0].block, program.regions[0].block
        )

        PDLToIRDLPass().apply(ctx, program)
        if args.debug:
            print("Converted IRDL program before optimization:")
            print(program)
        OptimizeIRDL().apply(ctx, program)
        if args.debug:
            print("Converted IRDL program after optimization:")
            print(program)
        solver = z3.Solver()
        check_subset_to_z3(program, solver)

        if args.debug:
            print("SMT program:")
            print(solver.to_smt2())
        if solver.check() == z3.sat:
            print("sat: PDL rewrite may break IRDL invariants")
            print("model: ", solver.model())
            has_broken_pattern = True
        else:
            print("unsat: PDL rewrite will not break IRDL invariants")

    if has_broken_pattern:
        print("Some patterns may break IRDL invariants")
        sys.exit(1)

    print("All patterns will not break IRDL invariants")
    return


if __name__ == "__main__":
    main()
