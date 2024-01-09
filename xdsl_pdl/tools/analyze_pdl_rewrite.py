from __future__ import annotations
import argparse
from random import randint
from xdsl.dialects.builtin import ModuleOp

from xdsl.printer import Printer
from xdsl.utils.diagnostic import Diagnostic
from xdsl.xdsl_opt_main import xDSLOptMain

from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite
from xdsl_pdl.analysis.pdl_analysis import (
    PDLAnalysisAborted,
    PDLAnalysisException,
    pdl_analysis_pass,
)
from xdsl_pdl.pdltest import PDLTest


class PDLAnalyzeRewrite(xDSLOptMain):
    def __init__(self):
        super().__init__()
        self.ctx.allow_unregistered = True

    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        arg_parser.add_argument(
            "--seed",
            type=int,
            required=False,
            help="Seed used for random number generation when generating a new PDL rewrite",
        )

    def register_all_dialects(self):
        super().register_all_dialects()
        self.ctx.load_dialect(PDLTest)

    def run(self):
        if self.args.input_file is None:
            seed = self.args.seed
            if seed is None:
                seed = randint(0, 2**30)
            pattern = generate_random_pdl_rewrite(seed)
            module = ModuleOp([pattern])
        else:
            chunks, extension = self.prepare_input()
            assert len(chunks) == 1
            module = self.parse_chunk(chunks[0], extension)
            assert module is not None

        diagnostic = Diagnostic()
        try:
            pdl_analysis_pass(self.ctx, module)
        except PDLAnalysisAborted as e:
            diagnostic.add_message(e.op, e.msg)
        except PDLAnalysisException as e:
            diagnostic.add_message(e.op, e.msg)
            print("PDL analysis terminated unexpectedly")
        else:
            print("PDL analysis succeeded")
        printer = Printer(diagnostic=diagnostic)
        printer.print_op(module)


def main():
    PDLAnalyzeRewrite().run()


if "__main__" == __name__:
    main()
