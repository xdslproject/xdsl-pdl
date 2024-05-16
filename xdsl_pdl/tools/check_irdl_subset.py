"""
Check if a group of IRDL variables represent a subset of other IRDL variables.
"""

import argparse
import sys
from typing import Any, Callable
from xdsl.traits import SymbolTable
from xdsl.utils.hints import isa
import z3

from xdsl.dialects.builtin import (
    AnyIntegerAttr,
    Builtin,
    IntAttr,
    IntegerAttr,
    IntegerType,
)
from xdsl.dialects.func import Func
from xdsl.dialects.irdl import (
    IRDL,
    AnyOfOp,
    AnyOp,
    AttributeOp,
    BaseOp,
    IsOp,
    ParametersOp,
    ParametricOp,
    TypeOp,
    DialectOp,
)

from xdsl.ir import Attribute, MLContext, Operation, SSAValue
from xdsl.parser import IndexType, ModuleOp, Parser
from xdsl_pdl.dialects.irdl_extension import CheckSubsetOp, EqOp, IRDLExtension, YieldOp


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


def convert_attr_to_z3_attr(attr: Attribute, attribute_sort: Any) -> Any:
    if attr == IndexType():
        return attribute_sort.__dict__["builtin.index"]
    if isinstance(attr, IntegerType):
        bitwidth = convert_attr_to_z3_attr(attr.width, attribute_sort)
        return attribute_sort.__dict__["builtin.integer_type"](bitwidth)
    if isa(attr, AnyIntegerAttr):
        value = convert_attr_to_z3_attr(attr.value, attribute_sort)
        type = convert_attr_to_z3_attr(attr.type, attribute_sort)
        return attribute_sort.__dict__["builtin.integer_attr"](value, type)
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
            )
        )
        return
    if isinstance(op, IsOp):
        values_to_z3[op.output] = convert_attr_to_z3_attr(op.expected, attribute_sort)
        return
    if isinstance(op, BaseOp):
        if op.base_name is not None:
            attribute_name = op.base_name.data
        else:
            assert op.base_ref is not None
            base_attr_def = SymbolTable.lookup_symbol(op, op.base_ref)
            assert isinstance(base_attr_def, AttributeOp | TypeOp)
            dialect_def = base_attr_def.parent_op()
            assert isinstance(dialect_def, DialectOp)
            attribute_name = (
                dialect_def.sym_name.data + "." + base_attr_def.sym_name.data
            )
        values_to_z3[op.output] = create_value(op.output)
        add_constraint(
            attribute_sort.__dict__["is_" + attribute_name](values_to_z3[op.output])
        )
        return
    if isinstance(op, ParametricOp):
        base_attr_def = SymbolTable.lookup_symbol(op, op.base_type)
        assert isinstance(base_attr_def, AttributeOp | TypeOp)
        dialect_def = base_attr_def.parent_op()
        assert isinstance(dialect_def, DialectOp)

        parameters = [values_to_z3[arg] for arg in op.args]
        attribute_name = dialect_def.sym_name.data + "." + base_attr_def.sym_name.data

        values_to_z3[op.output] = attribute_sort.__dict__[attribute_name](*parameters)
        return
    if isinstance(op, EqOp):
        val0 = values_to_z3[op.args[0]]
        for arg in op.args[1:]:
            add_constraint(val0 == values_to_z3[arg])
        return
    if isinstance(op, YieldOp):
        return
    assert False, f"Unsupported op {op.name}"


def main():
    arg_parser = argparse.ArgumentParser(
        prog="check-irdl-subset",
        description="Check if a group of IRDL variables represent a "
        "subset of other IRDL variables.",
    )
    arg_parser.add_argument(
        "input_file", type=str, nargs="?", help="path to input file"
    )
    args = arg_parser.parse_args()

    # Setup the xDSL context
    ctx = MLContext()
    ctx.load_dialect(Builtin)
    ctx.load_dialect(Func)
    ctx.load_dialect(IRDL)
    ctx.load_dialect(IRDLExtension)

    # Grab the input program from the command line or a file
    if args.input_file is None:
        f = sys.stdin
    else:
        f = open(args.input_file)

    #
    with f:
        program = Parser(ctx, f.read()).parse_module()

    solver = z3.Solver()

    assert isinstance(main := program.ops.last, CheckSubsetOp)

    # The Attribute datatype is an union of all possible attributes found in the
    # IRDL program, plus an "Other" attribute that correspond to any other
    # attribute not explicitely defined in the program. Other has a parameter,
    # so two other attributes may be distincts.
    # int correspond to an integer value. It is used for an integer bitwidth for
    # instance.
    attribute_sort: Any = z3.Datatype("Attribute")
    add_attribute_constructors_from_irdl(attribute_sort, program)
    attribute_sort.declare("other", ("other_arg_0", z3.IntSort()))
    attribute_sort.declare("int", ("other_arg_0", z3.IntSort()))
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

    print("SMT program:")
    print(solver)
    if solver.check() == z3.sat:
        print("sat: lhs is not a subset of rhs")
        print("model: ", solver.model())
    else:
        print("unsat: lhs is a subset of rhs")


if "__main__" == __name__:
    main()
