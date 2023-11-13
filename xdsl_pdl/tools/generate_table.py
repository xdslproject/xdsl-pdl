#!/usr/bin/env python3

from __future__ import annotations

import argparse
import random

from xdsl.ir import MLContext
from xdsl.utils.diagnostic import Diagnostic
from xdsl.xdsl_opt_main import xDSLOptMain
from xdsl.dialects.builtin import (
    ModuleOp,
)
from xdsl.dialects.pdl import (
    PatternOp,
)
from xdsl_pdl.analysis.pdl_analysis import PDLAnalysisAborted, pdl_analysis_pass
from xdsl_pdl.analysis.mlir_analysis import (
    analyze_with_mlir,
)

from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite
from xdsl_pdl.pdltest import PDLTest


def fuzz_pdl_matches(
    module: ModuleOp, ctx: MLContext, mlir_executable_path: str
) -> tuple[bool, bool] | None:
    """
    Returns the result of the PDL analysis, and the result of the analysis using
    program fuzzing and MLIR.
    """
    if not isinstance(module.ops.first, PatternOp):
        raise Exception("Expected a single toplevel pattern op")

    # Check if the pattern is valid
    analysis_correct = True
    try:
        pdl_analysis_pass(ctx, module)
    except PDLAnalysisAborted:
        analysis_correct = False
    except Exception:
        return None

    mlir_analysis = analyze_with_mlir(module.ops.first, ctx, mlir_executable_path)
    return analysis_correct, mlir_analysis is None


class GenerateTableMain(xDSLOptMain):
    def register_all_dialects(self):
        super().register_all_dialects()
        self.ctx.register_dialect(PDLTest)

    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        arg_parser.add_argument("--mlir-executable", type=str, required=True)

    def run(self):
        random.seed(42)
        values = [[0, 0], [0, 0]]
        failed_analyses = 0
        for i in range(1000):
            print(i)
            pattern = generate_random_pdl_rewrite()
            module = ModuleOp([pattern])
            test_res = fuzz_pdl_matches(module, self.ctx, self.args.mlir_executable)
            if test_res is None:
                failed_analyses += 1
                continue
            values[int(test_res[0])][int(test_res[1])] += 1

        print("Analysis failed, MLIR analysis failed: ", values[0][0])
        print("Analysis failed, MLIR analysis succeeded: ", values[0][1])
        print("Analysis succeeded, MLIR analysis failed: ", values[1][0])
        print("Analysis succeeded, MLIR analysis succeeded: ", values[1][1])
        print("PDL Analysis raised an exception: ", failed_analyses)


def main():
    GenerateTableMain().run()
