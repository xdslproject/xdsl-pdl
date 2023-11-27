from xdsl.dialects.pdl import (
    ApplyNativeConstraintOp,  # Operations; Types
    ApplyNativeRewriteOp,
    AttributeOp,
    AttributeType,
    EraseOp,
    OperandOp,
    OperandsOp,
    OperationOp,
    OperationType,
    PatternOp,
    RangeOp,
    RangeType,
    ReplaceOp,
    ResultOp,
    ResultsOp,
    RewriteOp,
    TypeOp,
    TypesOp,
    TypeType,
    ValueType,
)
from xdsl.interpreter import Interpreter
from xdsl.ir import Dialect

PDL_EXT = Dialect(
    "pdl",
    [
        ApplyNativeConstraintOp,
        ApplyNativeRewriteOp,
        AttributeOp,
        OperandOp,
        EraseOp,
        OperandsOp,
        OperationOp,
        PatternOp,
        RangeOp,
        ReplaceOp,
        ResultOp,
        ResultsOp,
        RewriteOp,
        TypeOp,
        TypesOp,
    ],
    [
        AttributeType,
        OperationType,
        TypeType,
        ValueType,
        RangeType,
    ],
)
