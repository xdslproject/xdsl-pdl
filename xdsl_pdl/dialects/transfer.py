from xdsl.ir import ParametrizedAttribute, TypeAttribute, Dialect

from xdsl.irdl import (
    irdl_attr_definition,
    ParametrizedAttribute,
)


@irdl_attr_definition
class IntegerType(ParametrizedAttribute, TypeAttribute):
    name = "transfer.integer"


Transfer = Dialect("transfer", [], [IntegerType])
