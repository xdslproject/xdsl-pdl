import argparse
from xdsl.xdsl_opt_main import xDSLOptMain

from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite
from xdsl.dialects.builtin import ModuleOp


class PDLRewriteFuzzMain(xDSLOptMain):
    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        pass

    def run(self):
        pattern = generate_random_pdl_rewrite()
        module = ModuleOp([pattern])
        contents = self.output_resulting_program(module)
        self.print_to_output_stream(contents)


def main():
    PDLRewriteFuzzMain().run()
