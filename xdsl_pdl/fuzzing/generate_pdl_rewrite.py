from dataclasses import dataclass, field
from random import Random

from xdsl.ir import Block, Operation, Region, SSAValue

from xdsl.dialects.pdl import (
    EraseOp,
    OperandOp,
    OperationOp,
    PatternOp,
    ReplaceOp,
    ResultOp,
    RewriteOp,
    TypeOp,
    TypeType,
    ValueType,
)
from xdsl.dialects.builtin import IntAttr, IntegerAttr, IntegerType, StringAttr, i32

from xdsl_pdl.pdltest import TestMatchOp, TestRewriteOp, TestTerminatorOp

i16 = IntegerType(16)


class _FuzzerOptions:
    min_operands = 0
    max_operands = 2
    min_results = 0
    max_results = 2
    min_match_operations = 1
    max_match_operations = 4
    min_rewrite_operations = 1
    max_rewrite_operations = 3


@dataclass
class _FuzzerContext:
    randgen: Random
    values: list[SSAValue] = field(default_factory=list)
    operations: list[OperationOp] = field(default_factory=list)

    def get_random_value(self) -> SSAValue:
        assert len(self.values) != 0
        return self.values[self.randgen.randrange(0, len(self.values))]

    def get_random_operation(self) -> OperationOp:
        assert len(self.operations) != 0
        return self.operations[self.randgen.randrange(0, len(self.operations))]


def _generate_random_operand(ctx: _FuzzerContext) -> tuple[SSAValue, list[Operation]]:
    """
    Generate a random operand.
    It is either a new `pdl.operand`, or an existing one in the context.
    """
    if len(ctx.values) != 0 and ctx.randgen.randrange(0, 2) == 0:
        return ctx.values[ctx.randgen.randrange(0, len(ctx.values))], []
    new_type = TypeOp(i32)
    new_operand = OperandOp.create(
        result_types=[ValueType()], operands=[new_type.result]
    )
    return new_operand.value, [new_type, new_operand]


def _generate_random_matched_operation(ctx: _FuzzerContext) -> list[Operation]:
    """
    Generate a random `pdl.operation`, along with new
    `pdl.operand` and `pdl.type` if necessary.
    """
    num_operands = ctx.randgen.randrange(
        _FuzzerOptions.min_operands, _FuzzerOptions.max_operands + 1
    )
    num_results = ctx.randgen.randrange(
        _FuzzerOptions.min_results, _FuzzerOptions.max_results + 1
    )
    new_ops: list[Operation] = []

    operands: list[SSAValue] = []
    results: list[SSAValue] = []
    for _ in range(num_operands):
        operand, operand_ops = _generate_random_operand(ctx)
        operands.append(operand)
        new_ops.extend(operand_ops)

    for _ in range(num_results):
        new_type = TypeOp(i32)
        results.append(new_type.result)
        new_ops.extend([new_type])
    # here
    op_name = ctx.randgen.choices(
        [TestMatchOp.name, TestTerminatorOp.name, None], weights=[0.9, 0.05, 0.05], k=1
    )[0]
    op = OperationOp(op_name, None, operands, None, results)
    new_ops.append(op)
    ctx.operations.append(op)

    for result_idx in range(num_results):
        result = ResultOp(IntegerAttr[IntegerType](result_idx, i32), op.op)
        new_ops.append(result)
        ctx.values.append(result.val)
    return new_ops


def _generate_random_rewrite_operation(ctx: _FuzzerContext) -> list[Operation]:
    """
    Generate a random operation in the rewrite part of the pattern.
    This can be either an `operation`, an `erase`, or a `replace`.
    """
    operation_choice = ctx.randgen.randrange(0, 4)

    # Erase operation
    if operation_choice == 0:
        op = ctx.get_random_operation()
        return [EraseOp(op.op)]

    # Replace operation with another operation
    if operation_choice == 1:
        op = ctx.get_random_operation()
        op2 = ctx.get_random_operation()
        return [ReplaceOp(op.op, op2.op)]

    # Replace operation with multiple values
    if operation_choice == 2:
        op = ctx.get_random_operation()
        # If we need values but we don't have, we restart
        if len(op.results) != 0 and len(ctx.values) == 0:
            return _generate_random_rewrite_operation(ctx)
        values = [ctx.get_random_value() for _ in op.results]
        return [ReplaceOp(op.op, None, values)]

    # Create a new operation
    assert operation_choice == 3
    num_operands = ctx.randgen.randrange(
        _FuzzerOptions.min_operands, _FuzzerOptions.max_operands + 1
    )
    num_results = ctx.randgen.randrange(
        _FuzzerOptions.min_results, _FuzzerOptions.max_results + 1
    )

    # If we need values but we don't have, we restart
    if num_operands != 0 and len(ctx.values) == 0:
        return _generate_random_rewrite_operation(ctx)

    new_ops: list[Operation] = []
    operands = [ctx.get_random_value() for _ in range(num_operands)]
    results: list[SSAValue] = []
    for _ in range(num_results):
        new_type = TypeOp(i32)
        results.append(new_type.result)
        new_ops.extend([new_type])

    op = OperationOp(StringAttr(TestRewriteOp.name), None, operands, None, results)
    ctx.operations.append(op)
    new_ops.append(op)

    for result_idx in range(num_results):
        result = ResultOp(IntegerAttr[IntegerType](result_idx, i32), op.op)
        new_ops.append(result)
        ctx.values.append(result.val)

    return new_ops


def generate_unverified_random_pdl_rewrite(randgen: Random) -> PatternOp:
    """
    Generate a random match part of a `pdl.rewrite`.
    """
    ctx = _FuzzerContext(randgen)
    num_matched_operations = randgen.randrange(
        _FuzzerOptions.min_match_operations, _FuzzerOptions.max_match_operations + 1
    )
    num_rewrite_operations = randgen.randrange(
        _FuzzerOptions.min_rewrite_operations, _FuzzerOptions.max_rewrite_operations + 1
    )

    # Generate a the matching part
    matched_ops: list[Operation] = []
    for _ in range(num_matched_operations):
        matched_ops.extend(_generate_random_matched_operation(ctx))

    # Get the last operation in the match, this is the one we use to rewrite
    rewritten_op = ctx.operations[-1]

    # Generate the rewrite part
    rewrite_ops: list[Operation] = []
    for _ in range(num_rewrite_operations):
        rewrite_ops.extend(_generate_random_rewrite_operation(ctx))

    region = Region([Block(rewrite_ops)])

    rewrite = RewriteOp(rewritten_op.op, region)

    body = Region([Block(matched_ops + [rewrite])])
    pattern = PatternOp(1, None, body)
    return pattern


def generate_random_pdl_rewrite(seed: int) -> PatternOp:
    randgen = Random()
    randgen.seed(seed)
    while True:
        pattern = generate_unverified_random_pdl_rewrite(randgen)
        pattern.attributes["seed"] = IntAttr(seed)
        try:
            pattern.verify()
        except Exception:
            continue
        return pattern
