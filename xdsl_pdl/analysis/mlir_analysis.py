import subprocess
from io import StringIO
from dataclasses import dataclass
from random import Random

from xdsl.ir import MLContext, Operation, Region, Block
from xdsl.printer import Printer

from xdsl.dialects.builtin import FunctionType, ModuleOp, StringAttr
from xdsl.dialects.pdl import PatternOp
from xdsl.dialects.func import FuncOp

from xdsl_pdl.fuzzing.generate_pdl_matches import get_all_matches


@dataclass
class MLIRInfiniteLoop(Exception):
    failed_program: str


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

    try:
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
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        raise MLIRInfiniteLoop(mlir_input.getvalue())

    if res.returncode != 0:
        raise MLIRFailure(mlir_input.getvalue(), res.stderr)
    return res.stdout


def analyze_with_mlir(
    pattern: PatternOp, ctx: MLContext, randgen: Random, mlir_executable_path: str
) -> MLIRFailure | MLIRInfiniteLoop | None:
    """
    Run the pattern on multiple examples with MLIR.
    If MLIR returns an error in any of the examples, returns the error.
    """
    try:
        pattern = pattern.clone()
        for populated_region in get_all_matches(
            pattern, Region([Block()]), randgen, ctx
        ):
            cloned_region = Region()
            populated_region.clone_into(cloned_region)
            program = FuncOp(
                "test",
                FunctionType.from_lists(
                    [arg.type for arg in cloned_region.blocks[0].args], []
                ),
                cloned_region,
            )
            run_with_mlir(program, pattern, mlir_executable_path)
    except MLIRFailure as e:
        return e
    except MLIRInfiniteLoop as e:
        return e
    return None
