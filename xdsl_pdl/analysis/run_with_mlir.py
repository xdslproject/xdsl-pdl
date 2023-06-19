import subprocess
from io import StringIO
from dataclasses import dataclass

from xdsl.ir import Region, MLContext, Block
from xdsl.printer import Printer

from xdsl.dialects.builtin import ModuleOp, StringAttr
from xdsl.dialects.pdl import PatternOp


@dataclass
class MLIRFailure(Exception):
    failed_program: str
    error_msg: str


def run_with_mlir(
    region: Region, ctx: MLContext, mlir_executable_path: str, pattern: PatternOp
):
    mlir_input = StringIO()
    printer = Printer(stream=mlir_input)
    new_region = Region()
    region.clone_into(new_region)
    test_op = ctx.get_op("test.op", allow_unregistered=True).create(
        regions=[new_region]
    )

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
        raise MLIRFailure(mlir_input.getvalue(), res.stderr)
    print(res.stdout)
    global counter
    print(counter)
    counter += 1
