import subprocess
from io import StringIO
from dataclasses import dataclass

from xdsl.ir import Operation, Region, Block
from xdsl.printer import Printer

from xdsl.dialects.builtin import ModuleOp, StringAttr
from xdsl.dialects.pdl import PatternOp


@dataclass
class MLIRFailure(Exception):
    failed_program: str
    error_msg: str


def run_with_mlir(
    program: Operation, pattern: PatternOp, mlir_executable_path: str
) -> str:
    """
    Execute the pattern rewrite on the given program using MLIR.
    Return `MLIRFailure` if the rewrite fails, otherwise return the MLIR output.
    """
    mlir_input = StringIO()
    printer = Printer(stream=mlir_input)
    new_prog = program.clone()

    patterns_module = ModuleOp.create(
        attributes={"sym_name": StringAttr("patterns")},
        regions=[Region([Block()])],
    )
    patterns_module.regions[0].blocks[0].add_op(pattern.clone())
    if not isinstance(new_prog, ModuleOp):
        new_prog = ModuleOp.create(
            attributes={"sym_name": StringAttr("ir")},
            regions=[Region([Block([new_prog])])],
        )
    module = ModuleOp([patterns_module, new_prog])
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
    return res.stdout
