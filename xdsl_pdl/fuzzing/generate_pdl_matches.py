from __future__ import annotations

from itertools import chain, combinations
from dataclasses import dataclass, field
from random import Random, randrange
from typing import Generator, Iterable, cast

from xdsl.ir import Attribute, Block, MLContext, OpResult, Operation, Region, SSAValue
from xdsl.dialects.builtin import (
    IntegerAttr,
    IntegerType,
    i32,
)
from xdsl.dialects.pdl import (
    AttributeOp,
    OperandOp,
    OperationOp,
    PatternOp,
    ResultOp,
    RewriteOp,
    TypeOp,
)


@dataclass
class SingleEntryDAGStructure:
    """
    A DAG structure, represented by a reverse adjency list.
    A reverse adjency list is a list of sets, where the i-th set contains
    the indices of the nodes that points to the i-th node.
    """

    size: int = field(default=0)
    reverse_adjency_list: list[set[int]] = field(default_factory=list)

    def add_node(self, parents: set[int]):
        if all(parent >= self.size for parent in parents):
            raise Exception("Can't add a node without non-self parents")
        for parent in parents:
            if parent > self.size:
                raise Exception(
                    "Can't add a node with parents that are not " "yet in the DAG"
                )
        self.reverse_adjency_list.append(parents)
        self.size += 1

    def get_adjency_list(self) -> list[set[int]]:
        adjency_list: list[set[int]] = [set() for _ in range(self.size)]
        for i, parents in enumerate(self.reverse_adjency_list):
            for parent in parents:
                adjency_list[parent].add(i)
        return adjency_list

    def copy(self) -> SingleEntryDAGStructure:
        return SingleEntryDAGStructure(self.size, self.reverse_adjency_list.copy())

    def get_dominance_list(self) -> list[set[int]]:
        dominance_list = [set[int]()]
        for i in range(1, self.size):
            reverse_strict_adjency = self.reverse_adjency_list[i].copy()
            if i in reverse_strict_adjency:
                reverse_strict_adjency.remove(i)
            assert len(self.reverse_adjency_list[i]) > 0
            if len(reverse_strict_adjency) == 1:
                parent = list(reverse_strict_adjency)[0]
                dominance_list.append(dominance_list[parent] | {parent})
            else:
                first_parent = list(reverse_strict_adjency)[0]
                dominance = dominance_list[first_parent] | {first_parent}
                for parent in reverse_strict_adjency:
                    dominance = dominance & (dominance_list[parent] | {parent})
                dominance_list.append(dominance)

        return dominance_list


def powerset(iterable: Iterable[int]) -> chain[tuple[int, ...]]:
    "powerset([1,2,3]) --> () (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)"
    s = list(iterable)
    return chain.from_iterable(combinations(s, r) for r in range(len(s) + 1))


def generate_all_dags(num_blocks: int = 5) -> list[SingleEntryDAGStructure]:
    """
    Create all possible single-entry DAGs with the given number of blocks.
    First, generate all possible DAGs, then remove the ones that are not
    single-entry.
    There should be only 2 ^ (n*(n-1)/2) possible DAGs, so this should be fine.
    This is because a DAG can always be represented as a lower triangular
    matrix.
    """
    if num_blocks < 1:
        raise Exception("Can't generate a DAG with less than 1 block")
    if num_blocks == 1:
        return [SingleEntryDAGStructure(1, [set()]), SingleEntryDAGStructure(1, [{0}])]
    previous_dags = generate_all_dags(num_blocks - 1)
    res: list[SingleEntryDAGStructure] = []
    for dag in previous_dags:
        for parents in powerset(range(num_blocks)):
            if all(parent >= num_blocks - 1 for parent in parents):
                continue
            new_dag = dag.copy()
            new_dag.add_node(set(parents))
            res.append(new_dag)
    return res


@dataclass
class PDLSynthContext:
    """
    Context used for generating an Operation DAG being matched by a pattern.
    """

    types: dict[SSAValue, Attribute] = field(default_factory=dict)
    attributes: dict[SSAValue, Attribute] = field(default_factory=dict)
    values: dict[SSAValue, SSAValue] = field(default_factory=dict)
    ops: dict[SSAValue, Operation] = field(default_factory=dict)

    def possible_values_of_type(self, type: Attribute) -> list[SSAValue]:
        values: list[SSAValue] = []
        for value in self.values.values():
            if value.type == type:
                values.append(value)
        for op in self.ops.values():
            for result in op.results:
                if result.type == type:
                    values.append(result)
        return values


def pdl_to_operations(
    pattern: PatternOp, ctx: MLContext, randgen: Random
) -> tuple[Region, list[Operation]]:
    pattern_ops = pattern.body.ops
    region = Region([Block()])
    synth_ops: list[Operation] = []
    pdl_context = PDLSynthContext()

    for op in pattern_ops:
        if isinstance(op, RewriteOp):
            continue
        # TODO: For simplification, we are defaulting to i32 for now.
        # However, this is dangerous as this type might want to be equal
        # to another type that is not i32.
        if isinstance(op, TypeOp):
            pdl_context.types[op.result] = op.attributes.get("constantType", i32)
            continue

        # TODO: Do not assume that we cannot have an operand that is the result
        # of another operation later in the pattern.
        # This assumption could be remove by moving all operands as down as
        # possible.
        if isinstance(op, OperandOp):
            if op.value_type is not None:
                operand_type = pdl_context.types[op.value_type]
            else:
                operand_type = i32
            possible_values = pdl_context.possible_values_of_type(operand_type)
            region_args = region.blocks[0].args
            possible_values.extend(
                [arg for arg in region_args if arg.type == operand_type]
            )
            choice = randgen.randrange(0, len(possible_values) + 1)
            if choice == len(possible_values):
                arg = region.blocks[0].insert_arg(operand_type, 0)
            else:
                arg = possible_values[choice]
            pdl_context.values[op.value] = arg
            continue

        if isinstance(op, AttributeOp):
            attribute_type: Attribute
            if op.value is not None:
                attribute_type = op.value
            else:
                attribute_type = IntegerAttr[IntegerType](5, i32)
            pdl_context.attributes[op.output] = attribute_type
            continue

        if isinstance(op, ResultOp):
            assert isinstance(op.parent_.owner, Operation)
            pdl_context.values[op.val] = pdl_context.ops[op.parent_].results[
                op.index.value.data
            ]
            continue

        if isinstance(op, OperationOp):
            if len(op.attributeValueNames.data) != len(op.attribute_values):
                raise Exception(
                    "Number of attribute names does not match number of values"
                )
            attributes = {}
            for name, value in zip(op.attributeValueNames.data, op.attribute_values):
                attributes[name.data] = pdl_context.attributes[value]
            operands = [pdl_context.values[operand] for operand in op.operand_values]
            result_types = [pdl_context.types[types] for types in op.type_values]
            if op.opName is None:
                op_def = ctx.get_op("unknown")
            else:
                op_def = ctx.get_optional_op(op.opName.data)
                if op_def is None:
                    op_def = ctx.get_op(op.opName.data)
            new_op = op_def.create(
                operands=operands, attributes=attributes, result_types=result_types
            )
            pdl_context.ops[op.op] = new_op
            synth_ops.append(new_op)
            continue

        raise Exception(f"Can't handle {op.name} op")

    return region, synth_ops


def create_dag_in_region(region: Region, dag: SingleEntryDAGStructure, ctx: MLContext):
    assert len(region.blocks) == 1
    blocks: list[Block] = []
    for _ in range(dag.size):
        block = Block()
        region.add_block(block)
        blocks.append(block)

    region.blocks[0].add_op(ctx.get_op("test.entry").create(successors=[blocks[0]]))

    for i, adjency_set in enumerate(dag.get_adjency_list()):
        block = blocks[i]
        successors = [blocks[j] for j in adjency_set]
        branch_op = ctx.get_op("test.branch")
        block.add_op(branch_op.create(successors=successors))


def put_operations_in_region(
    dag: SingleEntryDAGStructure, region: Region, ops: list[Operation]
) -> Generator[Region, None, None]:
    block_to_idx: dict[Block, int] = {}
    for i, block in enumerate(region.blocks[1:]):
        block_to_idx[block] = i
    dominance_list = dag.get_dominance_list()

    def rec(i: int, ops: list[Operation]) -> Generator[Region, None, None]:
        # Finished placing all operations.
        if len(ops) == 0:
            yield region
            return
        # No more blocks to place operations in.
        if i == dag.size:
            return

        # Try to place operations in next blocks
        yield from rec(i + 1, ops)

        # Check if we can place the first operation in this block
        operands_index = set(
            block_to_idx[cast(Block, operand.owner.parent_block())]
            for operand in ops[0].operands
            if isinstance(operand, OpResult)
        )
        if operands_index.issubset(dominance_list[i]):
            # Place the operation, and recurse
            block = region.blocks[i + 1]
            assert block.ops.last is not None
            block.insert_op_before(ops[0], block.ops.last)
            yield from rec(i, ops[1:])
            ops[0].detach()

    yield from rec(0, ops)
