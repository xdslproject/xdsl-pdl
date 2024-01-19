from dataclasses import dataclass

from xdsl.interpreter import register_impls
from xdsl.interpreters.experimental import pdl


@register_impls
@dataclass
class PDLRewriteFunctionsExt(pdl.PDLRewriteFunctions):
    # Here can go new and overwritten implementations of the PDL rewrite functions
    pass


@dataclass
class PDLRewritePatternExt(pdl.PDLRewritePattern):
    functions: PDLRewriteFunctionsExt
    pdl_rewrite_op: pdl.pdl.RewriteOp
    interpreter: pdl.Interpreter
