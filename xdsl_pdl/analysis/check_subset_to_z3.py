"""
Create an SMT query to check if a group of IRDL
variables represent a subset of other IRDL variables.
"""

from typing import Any, Callable, Sequence
from xdsl.traits import SymbolTable
from xdsl.utils.hints import isa
import z3

from xdsl.dialects.builtin import (
    AnyIntegerAttr,
    ArrayAttr,
    IntAttr,
    IntegerType,
    Signedness,
    SignednessAttr,
    StringAttr,
)
from xdsl.dialects.irdl import (
    AllOfOp,
    AnyOfOp,
    AnyOp,
    AttributeOp,
    BaseOp,
    IsOp,
    ParametricOp,
    TypeOp,
    DialectOp,
)

from xdsl.ir import Attribute, Operation, SSAValue
from xdsl.parser import IndexType, ModuleOp
from xdsl_pdl.dialects.irdl_extension import CheckSubsetOp, EqOp, MatchOp, YieldOp


def add_attribute_constructors_from_irdl(
    attribute_sort: z3.DatatypeSort, module: ModuleOp
):
    """
    Add an attribute datatype constructor for each attribute and type definition
    found in the IRDL program.
    """
    for attr_def in module.walk():
        if not isinstance(attr_def, TypeOp | AttributeOp):
            continue
        parameters = attr_def.body.block.last_op
        num_parameters = len(parameters.operands) if parameters else 0
        assert isinstance(attr_def, AttributeOp | TypeOp)
        dialect_def = attr_def.parent_op()
        assert isinstance(dialect_def, DialectOp)
        name = dialect_def.sym_name.data + "." + attr_def.sym_name.data
        attribute_sort.declare(
            name,
            *[(f"{name}_arg_{i}", attribute_sort) for i in range(num_parameters)],
        )


def create_z3_attribute(attribute_sort: Any, attr_name: str, *parameters: Any) -> Any:
    if parameters:
        return attribute_sort.__dict__[attr_name](*parameters)
    return attribute_sort.__dict__[attr_name]


def convert_attr_to_z3_attr(attr: Attribute, attribute_sort: Any) -> Any:
    if attr == IndexType():
        return attribute_sort.__dict__["builtin.index"]
    if isinstance(attr, IntegerType):
        bitwidth = convert_attr_to_z3_attr(attr.width, attribute_sort)
        signedness = convert_attr_to_z3_attr(attr.signedness, attribute_sort)
        return attribute_sort.__dict__["builtin.integer_type"](bitwidth, signedness)
    if isinstance(attr, SignednessAttr):
        match attr.data:
            case Signedness.SIGNLESS:
                opcode = "signless"
            case Signedness.SIGNED:
                opcode = "signed"
            case Signedness.UNSIGNED:
                opcode = "unsigned"
        opcode_attr = convert_attr_to_z3_attr(StringAttr(opcode), attribute_sort)
        return attribute_sort.__dict__["builtin.signedness"](opcode_attr)
    if isa(attr, AnyIntegerAttr):
        value = convert_attr_to_z3_attr(attr.value, attribute_sort)
        type = convert_attr_to_z3_attr(attr.type, attribute_sort)
        return attribute_sort.__dict__["builtin.integer_attr"](value, type)
    if isinstance(attr, StringAttr):
        return attribute_sort.__dict__["string"](z3.StringVal(attr.data))
    if isinstance(attr, IntAttr):
        return attribute_sort.__dict__["int"](attr.data)
    raise Exception(f"Unknown attribute {attr}")


def get_constraint_as_z3(
    op: Operation,
    attribute_sort: Any,
    values_to_z3: dict[SSAValue, z3.ExprRef],
    create_value: Callable[[SSAValue], z3.ExprRef],
    add_constraint: Callable[[Any], None],
) -> None:
    if isinstance(op, AnyOp):
        values_to_z3[op.output] = create_value(op.output)
        return
    if isinstance(op, AnyOfOp):
        values_to_z3[op.output] = create_value(op.output)
        add_constraint(
            z3.Or(
                [
                    values_to_z3[op.output] == values_to_z3[operand]
                    for operand in op.operands
                ]
                + [values_to_z3[op.output] == attribute_sort.unassigned]
            )
        )
        return
    if isinstance(op, AllOfOp):
        values_to_z3[op.output] = create_value(op.output)
        and_constraint = z3.And(
            [
                values_to_z3[op.output] == values_to_z3[operand]
                for operand in op.operands
            ]
        )
        add_constraint(
            z3.Or(and_constraint, values_to_z3[op.output] == attribute_sort.unassigned)
        )
        return
    if isinstance(op, IsOp):
        values_to_z3[op.output] = convert_attr_to_z3_attr(op.expected, attribute_sort)
        return
    if isinstance(op, BaseOp):
        if op.base_name is not None:
            attribute_name = op.base_name.data[1:]
        else:
            assert op.base_ref is not None
            base_attr_def = SymbolTable.lookup_symbol(op, op.base_ref)
            if not isinstance(base_attr_def, AttributeOp | TypeOp):
                raise Exception(f"Cannot find symbol {op.base_ref}")
            dialect_def = base_attr_def.parent_op()
            assert isinstance(dialect_def, DialectOp)
            attribute_name = (
                dialect_def.sym_name.data + "." + base_attr_def.sym_name.data
            )
        values_to_z3[op.output] = create_value(op.output)
        is_base = attribute_sort.__dict__["is_" + attribute_name](
            values_to_z3[op.output]
        )
        add_constraint(
            z3.Or(is_base, values_to_z3[op.output] == attribute_sort.unassigned)
        )
        return
    if isinstance(op, ParametricOp):
        base_attr_def = SymbolTable.lookup_symbol(op, op.base_type)
        if not isinstance(base_attr_def, AttributeOp | TypeOp):
            raise Exception(f"Cannot find symbol {op.base_type}")
        dialect_def = base_attr_def.parent_op()
        assert isinstance(dialect_def, DialectOp)

        parameters = [values_to_z3[arg] for arg in op.args]
        attribute_name = dialect_def.sym_name.data + "." + base_attr_def.sym_name.data

        values_to_z3[op.output] = create_value(op.output)
        add_constraint(
            values_to_z3[op.output]
            == z3.If(
                z3.Or(*[arg == attribute_sort.unassigned for arg in parameters]),
                attribute_sort.unassigned,
                create_z3_attribute(attribute_sort, attribute_name, *parameters),
            )
        )
        return
    if isinstance(op, EqOp):
        val0 = values_to_z3[op.args[0]]
        for arg in op.args[1:]:
            add_constraint(val0 == values_to_z3[arg])
        return
    if isinstance(op, MatchOp):
        add_constraint(values_to_z3[op.arg] != attribute_sort.unassigned)
        return
    if isinstance(op, YieldOp):
        for arg in op.args:
            add_constraint(values_to_z3[arg] != attribute_sort.unassigned)
        for arg in op.args:
            named_value = create_value(arg)
            add_constraint(values_to_z3[arg] == named_value)
        return
    assert False, f"Unsupported op {op.name}"


def check_subset_to_z3(program: ModuleOp, solver: z3.Solver):
    assert isinstance(main := program.ops.last, CheckSubsetOp)

    # Set name_hints on values that don't have one and that are used in YieldOp
    for op in program.walk():
        if isinstance(op, YieldOp) and "name_hints" in op.attributes:
            assert isa(op.attributes["name_hints"], ArrayAttr[StringAttr])
            for index, arg in enumerate(op.args):
                if not arg.name_hint:
                    arg.name_hint = op.attributes["name_hints"].data[index].data

    # The Attribute datatype is an union of all possible attributes found in the
    # IRDL program, plus an "Other" attribute that correspond to any other
    # attribute not explicitely defined in the program. Other has a parameter,
    # so two other attributes may be distincts.
    # int correspond to an integer value. It is used for an integer bitwidth for
    # instance.
    attribute_sort: Any = z3.Datatype("Attribute")
    attribute_sort.declare("unassigned")
    attribute_sort.declare("other", ("other_arg_0", z3.IntSort()))
    attribute_sort.declare("int", ("int_arg_0", z3.IntSort()))
    attribute_sort.declare("string", ("string_arg_0", z3.StringSort()))
    add_attribute_constructors_from_irdl(attribute_sort, program)
    attribute_sort = attribute_sort.create()

    # Mapping from IRDL attribute values to their corresponding z3 value
    values_to_z3: dict[SSAValue, z3.ExprRef] = {}

    name_index = 0

    def create_z3_constant(val: SSAValue) -> Any:
        nonlocal name_index
        name_index += 1
        return z3.Const((val.name_hint or "tmp") + str(name_index), attribute_sort)

    # Walk the lhs, and create the z3 expressions of each constraint
    for op in main.lhs.walk():
        get_constraint_as_z3(
            op,
            attribute_sort,
            values_to_z3,
            create_z3_constant,
            lambda x: solver.add(x),
        )

    # Maintain a list of constants and constraints to
    constants: list[Any] = []
    constraints: list[Any] = []

    def add_constant(val: SSAValue) -> Any:
        constant = create_z3_constant(val)
        constants.append(constant)
        return constant

    def add_constraint(constraint: Any):
        constraints.append(constraint)

    for op in main.rhs.walk():
        get_constraint_as_z3(
            op,
            attribute_sort,
            values_to_z3,
            add_constant,
            add_constraint,
        )

    lhs_yield = main.lhs.block.last_op
    assert isinstance(lhs_yield, YieldOp)
    rhs_yield = main.rhs.block.last_op
    assert isinstance(rhs_yield, YieldOp)

    for lhs_arg, rhs_arg in zip(lhs_yield.args, rhs_yield.args):
        constraints.append(values_to_z3[lhs_arg] == values_to_z3[rhs_arg])
    solver.add(z3.Not(z3.Exists(constants, z3.And(constraints))))
