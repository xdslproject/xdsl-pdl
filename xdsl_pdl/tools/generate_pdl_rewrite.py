import argparse
from random import Random
from xdsl.xdsl_opt_main import xDSLOptMain

from xdsl_pdl.fuzzing.generate_pdl_rewrite import generate_random_pdl_rewrite
from xdsl.dialects.builtin import ModuleOp

from xdsl_pdl.pdltest import PDLTest


class PDLRewriteFuzzMain(xDSLOptMain):
    def __init__(self):
        super().__init__()
        self.ctx.allow_unregistered = True

    def register_all_dialects(self):
        super().register_all_dialects()
        self.ctx.load_dialect(PDLTest)

    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        arg_parser.add_argument("--seed", type=int, optional=True)
        pass

    def run(self):
        seed = self.args.seed
        if seed is None:
            seed = Random().randint(0, 2**30)
        pattern = generate_random_pdl_rewrite(seed)
        module = ModuleOp([pattern])
        output_stream = self.prepare_output()
        output_stream.write(self.output_resulting_program(module))


def main():
    PDLRewriteFuzzMain().run()


if "__main__" == __name__:
    main()
