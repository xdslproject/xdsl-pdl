from __future__ import annotations
import argparse
from xdsl.dialects.builtin import ModuleOp

from xdsl.printer import Printer
from xdsl.utils.diagnostic import Diagnostic
from xdsl.xdsl_opt_main import xDSLOptMain

from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite
from xdsl_pdl.analysis.pdl_analysis import PDLAnalysisFailed, pdl_analysis_pass


class PDLAnalyzeRewrite(xDSLOptMain):
    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)

    def run(self):
        if self.args.input_file is None:
            pattern = generate_random_pdl_rewrite()
            module = ModuleOp([pattern])
        else:
            chunks, extension = self.prepare_input()
            assert len(chunks) == 1
            module = self.parse_chunk(chunks[0], extension)
            assert module is not None

        diagnostic = Diagnostic()
        try:
            pdl_analysis_pass(self.ctx, module)
        except PDLAnalysisFailed as e:
            diagnostic.add_message(e.op, e.msg)
        else:
            print("PDL analysis succeeded")
        printer = Printer(diagnostic=diagnostic)
        printer.print_op(module)


def main():
    PDLAnalyzeRewrite().run()
