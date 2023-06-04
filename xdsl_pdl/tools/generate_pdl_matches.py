#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import argparse

from random import randrange
from io import StringIO

from xdsl.ir import Block, MLContext, Region
from xdsl.xdsl_opt_main import xDSLOptMain
from xdsl.dialects.builtin import (
    ModuleOp,
    StringAttr,
)
from xdsl.dialects.pdl import (
    PatternOp,
)
from xdsl.printer import Printer

from xdsl_pdl.fuzzing.generate_pdl_matches import (
    create_dag_in_region,
    generate_all_dags,
    pdl_to_operations,
    put_operations_in_region,
)
from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite


counter = 0


def run_with_mlir(
    region: Region, ctx: MLContext, mlir_executable_path: str, pattern: PatternOp
):
    mlir_input = StringIO()
    printer = Printer(stream=mlir_input)
    new_region = Region()
    region.clone_into(new_region)
    test_op = ctx.get_op("test", allow_unregistered=True).create(regions=[new_region])

    patterns_module = ModuleOp.create(
        attributes={"sym_name": StringAttr("patterns")},
        regions=[Region([Block()])],
    )
    patterns_module.regions[0].blocks[0].add_op(pattern.clone())
    ir_module = ModuleOp.create(
        attributes={"sym_name": StringAttr("ir")},
        regions=[Region([Block()])],
    )
    ir_module.regions[0].blocks[0].add_op(test_op)
    module = ModuleOp([patterns_module, ir_module])
    printer.print_op(module)

    print(mlir_input.getvalue())

    res = subprocess.run(
        [
            mlir_executable_path,
            "--mlir-print-op-generic",
            "-allow-unregistered-dialect",
            "--test-pdl-bytecode-pass",
        ],
        input=mlir_input.getvalue(),
        text=True,
        capture_output=True,
    )

    if res.returncode != 0:
        print(res.stderr)
        raise Exception("MLIR failed")
    print(res.stdout)
    global counter
    print(counter)
    counter += 1


def fuzz_pdl_matches(module: ModuleOp, ctx: MLContext, mlir_executable_path: str):
    if not isinstance(module.ops.first, PatternOp):
        raise Exception("Expected a single toplevel pattern op")
    region, ops = pdl_to_operations(module.ops.first, ctx)
    all_dags = generate_all_dags(5)
    dag = all_dags[randrange(0, len(all_dags))]
    create_dag_in_region(region, dag, ctx)
    for populated_region in put_operations_in_region(dag, region, ops):
        run_with_mlir(populated_region, ctx, mlir_executable_path, module.ops.first)


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

        for _ in range(0, 10):
            fuzz_pdl_matches(module, self.ctx, self.args.mlir_executable)


def main():
    PDLMatchFuzzMain().run()
