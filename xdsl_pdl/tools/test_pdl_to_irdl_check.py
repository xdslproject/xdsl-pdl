"""
Translate a PDL rewrite with an IRDL specification to a program that checks if the
PDL rewrite is not breaking any IRDL invariants.
"""

import argparse
import sys

from xdsl.ir import MLContext
from xdsl.parser import Parser

from xdsl.dialects.pdl import PDL

from xdsl.dialects.builtin import Builtin
from xdsl.dialects.irdl import IRDL
from xdsl_pdl.dialects.irdl_extension import IRDLExtension
from xdsl_pdl.passes.pdl_to_irdl import PDLToIRDLPass
from xdsl_pdl.passes.optimize_irdl import OptimizeIRDL


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

    PDLToIRDLPass().apply(ctx, program)
    OptimizeIRDL().apply(ctx, program)

    print(program)


if __name__ == "__main__":
    main()
