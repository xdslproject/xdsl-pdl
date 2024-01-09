#!/usr/bin/env python3

from __future__ import annotations

import concurrent.futures
import argparse
from os import cpu_count
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

    mlir_analysis = analyze_with_mlir(
        module.ops.first, ctx, randgen, mlir_executable_path
    )
    return analysis_correct, mlir_analysis is None


class GenerateTableMain(xDSLOptMain):
    num_tested: int
    failed_analyses: list[int]
    values: tuple[tuple[list[int], list[int]], tuple[list[int], list[int]]]

    def __init__(self):
        super().__init__()
        self.ctx.allow_unregistered = True
        self.num_tested = 0
        self.failed_analyses = []
        self.values = (([], []), ([], []))

    def register_all_dialects(self):
        super().register_all_dialects()
        self.ctx.load_dialect(PDLTest)

    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        arg_parser.add_argument("--mlir-executable", type=str, default="mlir-opt")
        arg_parser.add_argument("-n", type=int, default=10000)
        arg_parser.add_argument("-j", type=int, default=cpu_count())

    def run_one_thread(self, seed: int):
        pattern = generate_random_pdl_rewrite(seed)
        module = ModuleOp([pattern])
        randgen = Random()
        randgen.seed(seed)
        test_res = fuzz_pdl_matches(
            module, self.ctx, randgen, self.args.mlir_executable
        )
        self.num_tested += 1
        print(f"Tested {self.num_tested} patterns", end="\r")
        if test_res is None:
            self.failed_analyses.append(seed)
            return
        self.values[int(test_res[0])][int(test_res[1])].append(seed)

    def run(self):
        randgen = Random()
        randgen.seed(42)
        seeds = [randgen.randint(0, 2**30) for _ in range(self.args.n)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.args.j) as executor:
            executor.map(self.run_one_thread, seeds)

        print("Analysis failed, MLIR execution failed: ", self.values[0][0], "\n")
        print("Analysis succeeded, MLIR execution succeeded: ", self.values[1][1], "\n")
        print("Analysis failed, MLIR execution succeeded: ", self.values[0][1], "\n")
        print("Analysis succeeded, MLIR execution failed: ", self.values[1][0], "\n")
        print("PDL Analysis raised an exception: ", self.failed_analyses, "\n")

        print_results(
            len(self.values[0][0]),
            len(self.values[0][1]),
            len(self.values[1][0]),
            len(self.values[1][1]),
        )


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
