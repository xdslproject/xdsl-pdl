from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Generator, Generic, Iterable, TypeVar

from xdsl.ir import Attribute, Block, MLContext, Operation, Region, SSAValue
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
    pattern: PatternOp, region: Region, ctx: MLContext, randgen: Random
) -> tuple[Region, list[Operation]]:
    assert len(region.blocks) == 1
    assert len(region.blocks[0].ops) == 0
    assert len(region.blocks[0].args) == 0
    pattern_ops = pattern.body.ops
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


T = TypeVar("T")


@dataclass
class UnionFind(Generic[T]):
    """Union-find data structure for representing equivalence classes."""

    parents: dict[T, T] = field(default_factory=dict)

    def find(self, value: T) -> T:
        if value not in self.parents:
            self.parents[value] = value
        if self.parents[value] == value:
            return value
        while self.parents[value] != value:
            parent = self.parents[value]
            grand_parent = self.parents[parent]
            (value, self.parents[value]) = (parent, grand_parent)
        return value

    def union(self, value1: T, value2: T) -> None:
        self.parents[self.find(value1)] = self.find(value2)


def get_edges(ops: Iterable[Operation]) -> set[tuple[Operation, Operation]]:
    """Get all edges of the DAG formed by the given operations."""
    edges = set[tuple[Operation, Operation]]()
    for op in ops:
        for operand in op.operands:
            if isinstance(operand.owner, Operation) and operand.owner in ops:
                edges.add((operand.owner, op))
    return edges


def get_roots(ops: list[Operation]) -> list[Operation]:
    """Get all operations that do not depend on any other operations on the list."""
    roots = set(ops)
    for _, to_op in get_edges(ops):
        roots.discard(to_op)
    return list(roots)


def get_connected_components(ops: list[Operation]) -> list[list[Operation]]:
    """Get all connected components of the DAG formed by the given operations."""
    uf = UnionFind[Operation]()
    for from_op, to_op in get_edges(ops):
        uf.union(from_op, to_op)
    components: dict[Operation, list[Operation]] = {}
    for op in ops:
        root = uf.find(op)
        components.setdefault(root, []).append(op)
    return list(components.values())


def get_all_interleavings(
    ops: list[Operation],
    current_block: Block,
    region: Region,
    ctx: MLContext,
) -> Generator[Region, None, None]:
    """
    Generate all possible interleaving of the given operations,
    while respecting dominance order.
    """
    if not ops:
        yield region
        return

    components = get_connected_components(ops)

    # If we have multiple connected components, we can split them,
    # and recurse on each component.
    if len(components) != 1:
        component1 = components[0]
        component2 = [op for component in components[1:] for op in component]
        block1 = Block()
        block2 = Block()
        region.add_block(block1)
        region.add_block(block2)
        terminator = ctx.get_op("test.terminator").create(successors=[block1, block2])
        current_block.add_op(terminator)

        for _ in get_all_interleavings(component1, block1, region, ctx):
            yield from get_all_interleavings(component2, block2, region, ctx)

        # Rollback the changes
        current_block.erase_op(terminator)
        region.erase_block(block1)
        region.erase_block(block2)
        return

    # If we have a single connected component, we add a root to the current block
    roots = get_roots(ops)
    assert roots
    for root in roots:
        current_block.add_op(root)
        use_op = ctx.get_op("test.use_op").create(operands=root.results)
        current_block.add_op(use_op)
        for _ in get_all_interleavings(ops[1:], current_block, region, ctx):
            yield region
        current_block.erase_op(use_op)
        current_block.erase_op(root)

    return


def get_all_matches(
    pattern: PatternOp, region: Region, randgen: Random, ctx: MLContext
) -> Iterable[Region]:
    """
    Generate all possible matches of the pattern in the given region with a
    single empty block.
    """
    assert len(region.blocks) == 1
    assert len(region.blocks[0].ops) == 0

    region, ops = pdl_to_operations(pattern, region, ctx, randgen)
    yield from get_all_interleavings(ops, region.blocks[0], region, ctx)
