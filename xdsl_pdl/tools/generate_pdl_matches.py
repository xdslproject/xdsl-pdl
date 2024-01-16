#!/usr/bin/env python3

from __future__ import annotations

import argparse
from random import randint, Random

from xdsl.ir import MLContext
from xdsl.utils.diagnostic import Diagnostic
from xdsl.xdsl_opt_main import xDSLOptMain
from xdsl.dialects.builtin import (
    ModuleOp,
)
from xdsl.dialects.pdl import (
    PatternOp,
)
from xdsl.printer import Printer
from xdsl_pdl.analysis.pdl_analysis import (
    PDLAnalysisAborted,
    PDLAnalysisException,
    pdl_analysis_pass,
)
from xdsl_pdl.analysis.mlir_analysis import (
    MLIRFailure,
    MLIRSuccess,
    analyze_with_mlir,
)

from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite
from xdsl_pdl.pdltest import PDLTest


def fuzz_pdl_matches(
    module: ModuleOp, ctx: MLContext, mlir_executable_path: str, seed: int
):
    if not isinstance(module.ops.first, PatternOp):
        raise Exception("Expected a single toplevel pattern op")

    print("Analysis result of the pattern:")
    # Check if the pattern is valid
    analysis_correct = True
    diagnostic = Diagnostic()
    try:
        pdl_analysis_pass(ctx, module)
    except PDLAnalysisAborted as e:
        diagnostic.add_message(e.op, e.msg)
        analysis_correct = False
        print("PDL analysis found error")
    except PDLAnalysisException as e:
        diagnostic.add_message(e.op, e.msg)
        analysis_correct = False
        print("PDL analysis found terminated unexpectedly")
    else:
        print("PDL analysis succeeded")
    printer = Printer(diagnostic=diagnostic)
    printer.print_op(module)

    mlir_analysis = analyze_with_mlir(
        module.ops.first, ctx, Random(seed), mlir_executable_path
    )
    if isinstance(mlir_analysis, MLIRSuccess):
        print("MLIR analysis succeeded")
    else:
        print("MLIR analysis failed")
        print("Failed program:")
        print(mlir_analysis.failed_program)
        if isinstance(mlir_analysis, MLIRFailure):
            print("Error message:")
            print(mlir_analysis.error_msg)
        else:
            print("Infinite loop")

    if analysis_correct:
        if isinstance(mlir_analysis, MLIRSuccess):
            print("GOOD: Analysis succeeded, MLIR analysis succeeded")
        else:
            print("BAD: Analysis succeeded, MLIR analysis failed")
    else:
        if isinstance(mlir_analysis, MLIRSuccess):
            print("BAD: Analysis failed, MLIR analysis succeeded")
        else:
            print("GOOD: Analysis failed, MLIR analysis failed")


class PDLMatchFuzzMain(xDSLOptMain):
    def __init__(self):
        super().__init__()
        self.ctx.allow_unregistered = True

    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        arg_parser.add_argument("--mlir-executable", type=str, default="mlir-opt")
        arg_parser.add_argument("--seed", type=int, required=False)

    def register_all_dialects(self):
        super().register_all_dialects()
        self.ctx.load_dialect(PDLTest)

    def run(self):
        seed = self.args.seed
        if seed is None:
            seed = randint(0, 2**30)
        if self.args.input_file is None:
            pattern = generate_random_pdl_rewrite(seed)
            module = ModuleOp([pattern])
        else:
            chunks, extension = self.prepare_input()
            assert len(chunks) == 1
            module = self.parse_chunk(chunks[0], extension)
            assert module is not None

        fuzz_pdl_matches(module, self.ctx, self.args.mlir_executable, seed)


def main():
    PDLMatchFuzzMain().run()


if "__main__" == __name__:
    main()
