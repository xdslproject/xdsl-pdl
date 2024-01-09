#!/usr/bin/env python3

from __future__ import annotations

import argparse
from random import Random
from tabulate import tabulate

from xdsl.ir import MLContext
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
    module: ModuleOp, ctx: MLContext, randgen: Random, mlir_executable_path: str
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

    mlir_analysis = analyze_with_mlir(module.ops.first, ctx, randgen, mlir_executable_path)
    return analysis_correct, mlir_analysis is None


class GenerateTableMain(xDSLOptMain):
    def __init__(self):
        super().__init__()
        self.ctx.allow_unregistered = True

    def register_all_dialects(self):
        super().register_all_dialects()
        self.ctx.load_dialect(PDLTest)

    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        arg_parser.add_argument("--mlir-executable", type=str, default="mlir-opt")
        arg_parser.add_argument("--num-patterns", type=int, default=10000)
        arg_parser.add_argument("-j", type=int, default=-1)

    def run(self):
        randgen = Random()
        randgen.seed(42)
        values = [[0, 0], [0, 0]]
        failed_analyses = 0
        for i in range(10000):
            print(i)
            pattern = generate_random_pdl_rewrite(randgen)
            module = ModuleOp([pattern])
            test_res = fuzz_pdl_matches(module, self.ctx, randgen, self.args.mlir_executable)
            if test_res is None:
                failed_analyses += 1
                continue
            values[int(test_res[0])][int(test_res[1])] += 1

        print("Analysis failed, MLIR execution failed: ", values[0][0])
        print("Analysis failed, MLIR execution succeeded: ", values[0][1])
        print("Analysis succeeded, MLIR execution failed: ", values[1][0])
        print("Analysis succeeded, MLIR execution succeeded: ", values[1][1])
        print("PDL Analysis raised an exception: ", failed_analyses)

        print_results(values[0][0], values[0][1], values[1][0], values[1][1])


def print_results(
    s_fail_d_fail: int, s_fail_d_succ: int, s_succ_d_fail: int, s_succ_d_succ: int
):
    """
    Prints the results of the analysis in a table, similar to the one
    we plan to have in the paper.
    """
    static_success = s_succ_d_succ + s_succ_d_fail
    static_fail = s_fail_d_succ + s_fail_d_fail
    dynamic_success = s_succ_d_succ + s_fail_d_succ
    dynamic_fail = s_fail_d_fail + s_succ_d_fail
    total = s_fail_d_fail + s_fail_d_succ + s_succ_d_fail + s_succ_d_succ

    table: str = tabulate(
        headers=["", "Passes Dynamic Check", "Fails Dynamic Check", "Total"],
        tabular_data=[
            [
                "Passes Static Check",
                s_succ_d_succ / static_success,
                s_succ_d_fail / static_success,
                static_success,
            ],
            [
                "Fails Static Check",
                s_fail_d_succ / static_fail,
                s_fail_d_fail / static_fail,
                static_fail,
            ],
            [
                "Total",
                dynamic_success,
                dynamic_fail,
                total,
            ],
        ],
        tablefmt="orgtbl",
    )

    print(f"\n{table}")


def main():
    GenerateTableMain().run()


if __name__ == "__main__":
    main()
