"""
Check if a group of IRDL variables represent a subset of other IRDL variables.
"""

import argparse
import sys
import z3

from xdsl.dialects.builtin import (
    Builtin,
)
from xdsl.dialects.func import Func
from xdsl.dialects.irdl import IRDL

from xdsl.ir import MLContext
from xdsl.parser import Parser
from xdsl_pdl.analysis.check_subset_to_z3 import check_subset_to_z3
from xdsl_pdl.dialects.irdl_extension import IRDLExtension


def main():
    arg_parser = argparse.ArgumentParser(
        prog="check-irdl-subset",
        description="Check if a group of IRDL variables represent a "
        "subset of other IRDL variables.",
    )
    arg_parser.add_argument(
        "input_file", type=str, nargs="?", help="path to input file"
    )
    args = arg_parser.parse_args()

    # Setup the xDSL context
    ctx = MLContext()
    ctx.load_dialect(Builtin)
    ctx.load_dialect(Func)
    ctx.load_dialect(IRDL)
    ctx.load_dialect(IRDLExtension)

    # Grab the input program from the command line or a file
    if args.input_file is None:
        f = sys.stdin
    else:
        f = open(args.input_file)

    #
    with f:
        program = Parser(ctx, f.read()).parse_module()

    solver = z3.Solver()
    check_subset_to_z3(program, solver)

    print("SMT program:")
    print(solver)
    if solver.check() == z3.sat:
        print("sat: lhs is not a subset of rhs")
        print("model: ", solver.model())
    else:
        print("unsat: lhs is a subset of rhs")


if "__main__" == __name__:
    main()
