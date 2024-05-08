"""
Check if a group of IRDL variables represent a subset of other IRDL variables.
"""

import argparse
import sys

from xdsl.dialects.builtin import Builtin
from xdsl.ir import MLContext
from xdsl.parser import Parser
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
    ctx.load_dialect(IRDLExtension)

    # Grab the input program from the command line or a file
    if args.input_file is None:
        f = sys.stdin
    else:
        f = open(args.input_file)

    #
    with f:
        program = Parser(ctx, f.read()).parse_module()

    print(program)


if "__main__" == __name__:
    main()
