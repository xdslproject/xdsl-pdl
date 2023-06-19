#!/usr/bin/env python3

from __future__ import annotations

import argparse

from random import randrange

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
from xdsl_pdl.analysis.run_with_mlir import run_with_mlir, MLIRFailure

from xdsl_pdl.fuzzing.generate_pdl_matches import (
    create_dag_in_region,
    generate_all_dags,
    pdl_to_operations,
    put_operations_in_region,
)
from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite


counter = 0


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

    region, ops = pdl_to_operations(module.ops.first, ctx)
    all_dags = generate_all_dags(5)
    try:
        for _ in range(0, 10):
            dag = all_dags[randrange(0, len(all_dags))]
            create_dag_in_region(region, dag, ctx)
            for populated_region in put_operations_in_region(dag, region, ops):
                run_with_mlir(
                    populated_region, ctx, mlir_executable_path, module.ops.first
                )
    except MLIRFailure as e:
        print("Failed program:")
        print(e.failed_program)
        print("Error message:")
        print(e.error_msg)
        if analysis_correct:
            print("Unexpected MLIR failure, analysis did not report it")
        else:
            print("Expected MLIR failure, analysis did report it")


class PDLMatchFuzzMain(xDSLOptMain):
    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        arg_parser.add_argument("--mlir-executable", type=str, required=True)

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
