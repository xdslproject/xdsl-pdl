import argparse
from xdsl.xdsl_opt_main import xDSLOptMain

from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite
from xdsl.dialects.builtin import ModuleOp

from xdsl_pdl.pdltest import PDLTest


class PDLRewriteFuzzMain(xDSLOptMain):
    def register_all_dialects(self):
        super().register_all_dialects()
        self.ctx.register_dialect(PDLTest)

    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        pass

    def run(self):
        pattern = generate_random_pdl_rewrite()
        module = ModuleOp([pattern])
        output_stream = self.prepare_output()
        output_stream.write(self.output_resulting_program(module))


def main():
    PDLRewriteFuzzMain().run()
