from dataclasses import dataclass

from xdsl.interpreter import register_impls
from xdsl.interpreters.experimental import pdl


@register_impls
@dataclass
class PDLRewriteFunctionsExt(pdl.PDLRewriteFunctions):
    pass
