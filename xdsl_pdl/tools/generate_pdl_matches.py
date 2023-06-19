#!/usr/bin/env python3

from __future__ import annotations

import argparse

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
from xdsl_pdl.analysis.pdl_analysis import PDLAnalysisFailed, pdl_analysis_pass
from xdsl_pdl.analysis.mlir_analysis import (
    MLIRFailure,
    analyze_with_mlir,
)

from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite
from xdsl_pdl.pdltest import PDLTest


def fuzz_pdl_matches(module: ModuleOp, ctx: MLContext, mlir_executable_path: str):
    if not isinstance(module.ops.first, PatternOp):
        raise Exception("Expected a single toplevel pattern op")

    print("Analysis result of the pattern:")
    # Check if the pattern is valid
    analysis_correct = True
    diagnostic = Diagnostic()
    try:
        pdl_analysis_pass(ctx, module)
    except PDLAnalysisFailed as e:
        diagnostic.add_message(e.op, e.msg)
        analysis_correct = False
        print("PDL analysis failed")
    else:
        print("PDL analysis succeeded")
    printer = Printer(diagnostic=diagnostic)
    printer.print_op(module)

    mlir_analysis = analyze_with_mlir(module.ops.first, ctx, mlir_executable_path)
    if mlir_analysis is None:
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
        if mlir_analysis is None:
            print("GOOD: Analysis succeeded, MLIR analysis succeeded")
        else:
            print("BAD: Analysis succeeded, MLIR analysis failed")
    else:
        if mlir_analysis is None:
            print("BAD: Analysis failed, MLIR analysis succeeded")
        else:
            print("GOOD: Analysis failed, MLIR analysis failed")


class PDLMatchFuzzMain(xDSLOptMain):
    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        arg_parser.add_argument("--mlir-executable", type=str, required=True)

    def register_all_dialects(self):
        super().register_all_dialects()
        self.ctx.register_dialect(PDLTest)

    def run(self):
        if self.args.input_file is None:
            pattern = generate_random_pdl_rewrite()
            module = ModuleOp([pattern])
        else:
            chunks, extension = self.prepare_input()
            assert len(chunks) == 1
            module = self.parse_chunk(chunks[0], extension)
            assert module is not None

        fuzz_pdl_matches(module, self.ctx, self.args.mlir_executable)


def main():
    PDLMatchFuzzMain().run()
