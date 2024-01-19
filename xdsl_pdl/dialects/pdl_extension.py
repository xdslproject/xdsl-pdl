from __future__ import annotations

from typing import Sequence, Iterable

from xdsl.dialects.builtin import ArrayAttr, StringAttr
from xdsl.dialects.pdl import ApplyNativeConstraintOp  # Operations; Types
from xdsl.dialects.pdl import (
    ApplyNativeRewriteOp,
    AttributeOp,
    AttributeType,
    EraseOp,
    OperandOp,
    OperandsOp,
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
    parse_operands_with_types,
    print_operands_with_types,
)
from xdsl.dialects import pdl
from xdsl.ir import Dialect, ParametrizedAttribute, TypeAttribute
from xdsl.irdl import (
    IRDLOperation,
    OpResult,
    SSAValue,
    VarOperand,
    attr_def,
    opt_attr_def,
    irdl_attr_definition,
    irdl_op_definition,
    result_def,
    var_operand_def,
    AttrSizedOperandSegments,
)
from xdsl.parser import Parser
from xdsl.printer import Printer


@irdl_attr_definition
class BlockType(ParametrizedAttribute, TypeAttribute):
    name = "pdl.block"


@irdl_attr_definition
class RegionType(ParametrizedAttribute, TypeAttribute):
    name = "pdl.region"


@irdl_op_definition
class BlockArgOp(IRDLOperation):
    """ """

    name = "pdl.blockarg"
    val: OpResult = result_def(ValueType())

    def __init__(self) -> None:
        super().__init__(result_types=[ValueType()])

    @classmethod
    def parse(cls, parser: Parser) -> BlockArgOp:
        return BlockArgOp()

    def print(self, printer: Printer) -> None:
        printer.print("")


@irdl_op_definition
class BlockOp(IRDLOperation):
    """ """

    name = "pdl.block"
    args: VarOperand = var_operand_def(ValueType)
    block: OpResult = result_def(BlockType)

    def __init__(self, args: Sequence[SSAValue]) -> None:
        super().__init__(operands=[args], result_types=[BlockType()])

    @classmethod
    def parse(cls, parser: Parser) -> BlockOp:
        args = parser.parse_comma_separated_list(
            parser.Delimiter.BRACES, parser.parse_operand
        )
        return BlockOp(args)

    def print(self, printer: Printer) -> None:
        printer.print_operands(self.args)


@irdl_op_definition
class RegionOp(IRDLOperation):
    """ """

    name = "pdl.region"
    blocks: VarOperand = var_operand_def(BlockType)
    region: OpResult = result_def(RegionType)

    def __init__(self, blocks: Sequence[SSAValue]) -> None:
        super().__init__(operands=[blocks], result_types=[RegionType()])

    @classmethod
    def parse(cls, parser: Parser) -> RegionOp:
        blocks = parser.parse_comma_separated_list(
            parser.Delimiter.BRACES, parser.parse_operand
        )
        return RegionOp(blocks)

    def print(self, printer: Printer) -> None:
        printer.print_operands(self.blocks)


@irdl_op_definition
class OperationOp(IRDLOperation):
    """
    https://mlir.llvm.org/docs/Dialects/PDLOps/#pdloperation-mlirpdloperationop
    """

    name = "pdl.operation"
    opName: StringAttr | None = opt_attr_def(StringAttr)
    attributeValueNames: ArrayAttr[StringAttr] = attr_def(ArrayAttr[StringAttr])

    operand_values: VarOperand = var_operand_def(ValueType | RangeType[ValueType])
    attribute_values: VarOperand = var_operand_def(AttributeType)
    type_values: VarOperand = var_operand_def(TypeType | RangeType[TypeType])

    op: OpResult = result_def(OperationType)

    irdl_options = [AttrSizedOperandSegments()]

    # Extension:
    region_values: VarOperand = var_operand_def(RegionType)

    def __init__(
        self,
        op_name: str | StringAttr | None,
        attribute_value_names: Iterable[StringAttr] | None = None,
        operand_values: Sequence[SSAValue] | None = None,
        attribute_values: Sequence[SSAValue] | None = None,
        type_values: Sequence[SSAValue] | None = None,
        region_values: Sequence[SSAValue] | None = None,
    ):
        if isinstance(op_name, str):
            op_name = StringAttr(op_name)
        if attribute_value_names is not None:
            attribute_value_names = ArrayAttr(attribute_value_names)
        if attribute_value_names is None:
            attribute_value_names = ArrayAttr([])

        if operand_values is None:
            operand_values = []
        if attribute_values is None:
            attribute_values = []
        if type_values is None:
            type_values = []
        if region_values is None:
            region_values = []

        super().__init__(
            operands=[operand_values, attribute_values, type_values, region_values],
            result_types=[OperationType()],
            attributes={
                "attributeValueNames": attribute_value_names,
                "opName": op_name,
            },
        )

    @classmethod
    def parse(cls, parser: Parser) -> OperationOp:
        name = parser.parse_optional_str_literal()
        operands = []
        if parser.parse_optional_punctuation("(") is not None:
            operands = parse_operands_with_types(parser)
            parser.parse_punctuation(")")

        def parse_attribute_entry() -> tuple[str, SSAValue]:
            name = parser.parse_str_literal()
            parser.parse_punctuation("=")
            type = parser.parse_operand()
            return (name, type)

        attributes = parser.parse_optional_comma_separated_list(
            Parser.Delimiter.BRACES, parse_attribute_entry
        )
        if attributes is None:
            attributes = []
        attribute_names = [StringAttr(attr[0]) for attr in attributes]
        attribute_values = [attr[1] for attr in attributes]

        results = []
        if parser.parse_optional_punctuation("->"):
            parser.parse_punctuation("(")
            results = parse_operands_with_types(parser)
            parser.parse_punctuation(")")

        return OperationOp(name, attribute_names, operands, attribute_values, results)

    def print(self, printer: Printer) -> None:
        if self.opName is not None:
            printer.print(" ", self.opName)

        if len(self.operand_values) != 0:
            printer.print(" (")
            print_operands_with_types(printer, self.operand_values)
            printer.print(")")

        def print_attribute_entry(entry: tuple[StringAttr, SSAValue]):
            printer.print(entry[0], " = ", entry[1])

        if len(self.attributeValueNames) != 0:
            printer.print(" {")
            printer.print_list(
                zip(self.attributeValueNames, self.attribute_values),
                print_attribute_entry,
            )
            printer.print("}")

        if len(self.type_values) != 0:
            printer.print(" -> (")
            print_operands_with_types(printer, self.type_values)
            printer.print(")")


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
        # Extensions:
        BlockArgOp,
        BlockOp,
        RegionOp,
    ],
    [
        AttributeType,
        OperationType,
        TypeType,
        ValueType,
        RangeType,
        # Extensions:
        BlockType,
        RegionType,
    ],
)
