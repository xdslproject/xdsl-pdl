from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Sequence

from xdsl.interpreter import (
    register_impls,
    InterpreterFunctions,
    Interpreter,
    impl,
    impl_terminator,
    PythonValues,
    ReturnedValues,
)
from xdsl.ir import Attribute, Operation, SSAValue
from xdsl_pdl.dialects import pdl_extension as pdl
from xdsl_pdl.analysis.pdl_analysis import PDLAnalysisAborted, PDLAnalysisException

# Goals:
# - track order of ops
# - track the insertion point

INTERPRETER_STATE_KEY = "interpreter_state_key"


class DataKeys(Enum):
    PHASE = "phase"
    # INSERTION_POINT = "insertion_point"
    GENERATED_OPS = "ops"
    ROOT_OP = "root"


class Phase(Enum):
    INIT = 0
    MATCHING = 1
    REWRITING = 2


"""
Hacks to enable this analysis:
- Enabled that a value association in the interpreter can be overwritten
- There needs to be something between `run_op` and `run_ssa_cfg_region`.
    - The former does not have any context, the latter properly keeps context for everything.
- Why only interpreter.get_values, not also interpreter.get_value?
- There could be a way of running the interpreter with an optional arg `debug=True` that prints the invoked functions and their arguments.
- There is currently no way to erase an individual value from the scope.
"""


def abort_if_not_in_scope(
    interpreter: Interpreter,
    values: SSAValue | Sequence[SSAValue],
    op: Operation,
    msg: str = "value not in scope.",
) -> bool:
    if not check_in_scope(interpreter, values):
        raise PDLAnalysisAborted(op, msg)
    return True


def check_in_scope(
    interpreter: Interpreter, values: SSAValue | Sequence[SSAValue]
) -> bool:
    if isinstance(values, SSAValue):
        values = [values]
    for value in values:
        try:
            repr = interpreter._ctx.env[value]
            if (isinstance(repr, Value) or isinstance(repr, Op)) and not repr.in_scope:
                return False
        except Exception as e:
            print(
                f"Encountered exception when checking whether the following is in scope: \n{value}\n{e}"
            )
    return True


@register_impls
@dataclass
class PDLAnalysisFunctions(InterpreterFunctions):
    """
    Interpretation of PDL rewrite patterns for the purpose of analysis is
    divided into three phases:
    1. Init phase
    2. Matching phase
    3. Rewriting phase
    """

    @staticmethod
    def run_op(
        interpreter: Interpreter, op: Operation, add_to_scope: bool = True
    ) -> None:
        # print(f"running op: {op.name}")
        # TODO: should this be op.operands?
        abort_if_not_in_scope(interpreter, op.operands, op, "operand not in scope")
        inputs = interpreter.get_values(op.operands)

        result = interpreter.run_op(op, inputs)
        interpreter.interpreter_assert(
            len(op.results) == len(result),
            f"Incorrect number of results for op {op.name}, expected {len(op.results)} but got {len(result)}",
        )
        if add_to_scope:
            interpreter.set_values(zip(op.results, result))

    @staticmethod
    def _init_state() -> dict[DataKeys, Phase | list[Op] | Optional[Op]]:
        return {
            DataKeys.PHASE: Phase.INIT,
            DataKeys.GENERATED_OPS: list(),
            DataKeys.ROOT_OP: None,
        }

    @staticmethod
    def get_state(interpreter: Interpreter, key: DataKeys) -> Any:
        return interpreter.get_data(
            PDLAnalysisFunctions,
            INTERPRETER_STATE_KEY,
            PDLAnalysisFunctions._init_state,
        )[key]

    @staticmethod
    def set_state(interpreter: Interpreter, key: DataKeys, data: Any) -> None:
        # print("setting state")
        interpreter.get_data(
            PDLAnalysisFunctions,
            INTERPRETER_STATE_KEY,
            PDLAnalysisFunctions._init_state,
        )[key] = data

    @staticmethod
    def get_value(interpreter: Interpreter, value: SSAValue) -> Any:
        return interpreter.get_values([value])[0]

    def get_actual(self, interpreter: Interpreter, repr: Any) -> SSAValue:
        # Note: This does only work in the current context, no lookup is
        #       performed in the parent context.
        return next(key for key, value in interpreter._ctx.env.items() if value == repr)

    def remove_from_scope(self, interpreter: Interpreter, value: SSAValue) -> None:
        op_or_val = interpreter.get_values([value])[0]
        op_or_val.in_scope = False
        # print(f"removing {op_or_val} from scope")
        if isinstance(op_or_val, Op):
            for result in op_or_val.results_taken:
                self.remove_from_scope(
                    interpreter, self.get_actual(interpreter, result)
                )
        interpreter.set_values([(value, op_or_val)])

    @impl(pdl.AttributeOp)
    def run_attribute(
        self, interpreter: Interpreter, op: pdl.AttributeOp, args: PythonValues
    ) -> PythonValues:
        # TODO: with example of attributes, I have to check the opt args and init
        #       the attribute accordingly

        # return (
        #     Attribute(
        #         type=op.value_type if op.value_type else None,
        #         value=op.value if op.value else None,
        #     ),
        # )
        return (Attribute(type=None, value=None),)

    @impl(pdl.EraseOp)
    def run_erase(
        self, interpreter: Interpreter, op: pdl.EraseOp, args: PythonValues
    ) -> PythonValues:
        phase = self.get_state(interpreter, DataKeys.PHASE)
        if phase == Phase.REWRITING:
            self.remove_from_scope(interpreter, op.op_value)
            erased_op: Op = self.get_value(interpreter, op.op_value)
            self.get_state(interpreter, DataKeys.GENERATED_OPS).remove(erased_op)

        return ()

    @impl(pdl.OperandOp)
    def run_operand(
        self, interpreter: Interpreter, op: pdl.OperandOp, args: PythonValues
    ) -> PythonValues:
        # print(f"running operand")

        return (Value(type=args[0] if len(args) > 0 else None),)

    @impl(pdl.OperationOp)
    def operation(
        self, interpreter: Interpreter, op: pdl.OperationOp, args: PythonValues
    ) -> PythonValues:
        # interpreter.get_values()
        phase = self.get_state(interpreter, DataKeys.PHASE)
        # print(f"running operation in {phase}")

        if phase == Phase.INIT:
            return self.init_operation(interpreter, op, args)
        elif phase == Phase.MATCHING:
            return self.match_operation(interpreter, op, args)
        elif phase == Phase.REWRITING:
            return self.run_operation(interpreter, op, args)

        raise PDLAnalysisException(op, "Phase mismatch in pdl.operation")

    def init_operation(
        self, interpreter: Interpreter, op: pdl.OperationOp, args: PythonValues
    ) -> PythonValues:
        pdl_op = Op(
            name=op.opName if op.opName else None,
            attribute_values=args[: len(op.attributeValueNames)],
            operands=args[
                len(op.attributeValueNames) : len(op.attributeValueNames)
                + len(op.operand_values)
            ],
            result_types=args[len(op.attributeValueNames) + len(op.operand_values) :],
        )
        # The uses in pdl.ResultOp ops are not known yet.

        # self.get_state(interpreter, DataKeys.GENERATED_OPS).append(pdl_op)
        return (pdl_op,)

    def match_operation(
        self, interpreter: Interpreter, op: pdl.OperationOp, args: PythonValues
    ):
        pdl_op = interpreter.get_values([op.results[0]])[0]
        # record uses in pdl.ResultOp ops
        for use in op.results[0].uses:
            if isinstance(use.operation, pdl.ResultOp) | isinstance(
                use.operation, pdl.ResultsOp
            ):
                pdl_op.results_taken.append(
                    self.get_value(interpreter, use.operation.results[0])
                )

        return (pdl_op,)

    def run_operation(
        self, interpreter: Interpreter, op: pdl.OperationOp, args: PythonValues
    ) -> PythonValues:
        pdl_op = interpreter.get_values([op.results[0]])[0]

        # Check that this does not use the root
        for operand in pdl_op.operands:
            if operand.op == self.get_state(interpreter, DataKeys.ROOT_OP):
                raise PDLAnalysisAborted(
                    op, "Rewrite operation uses the root as an operand."
                )

        # print("operands:")
        # print(interpreter.get_values(op.operands))
        # print(interpreter.get_values([args[0]]))
        gen_ops = self.get_state(interpreter, DataKeys.GENERATED_OPS)
        if len(gen_ops) == 0:
            raise PDLAnalysisAborted(
                op, "No valid insertion point set, possibly the root was deleted."
            )
        gen_ops.append(pdl_op)

        return (pdl_op,)

    @impl(pdl.PatternOp)
    def run_pattern(
        self, interpreter: Interpreter, op: pdl.PatternOp, args: PythonValues
    ) -> PythonValues:
        interpreter.push_scope(op.sym_name if op.sym_name else "pattern")
        # print("running pattern")

        for nested_op in op.body.block.ops:
            self.run_op(interpreter, nested_op, add_to_scope=True)

        self.set_state(interpreter, DataKeys.PHASE, Phase.MATCHING)

        for nested_op in op.body.block.ops_reverse:
            if isinstance(nested_op, pdl.RewriteOp):
                continue
            self.run_op(interpreter, nested_op, add_to_scope=False)

        # TODO: check that all ops are reachable?

        if not isinstance(rewrite_op := op.body.block.last_op, pdl.RewriteOp):
            raise PDLAnalysisException(op, "Pattern does not end with a rewrite")
        # Initially set insertion point to the root
        if rewrite_op.root:
            root_op = self.get_value(interpreter, rewrite_op.root)
        else:
            raise PDLAnalysisException(
                op, "Rewrites without explicit root are not supported."
            )
        self.get_state(interpreter, DataKeys.GENERATED_OPS).append(root_op)

        # Matching ready, simulating the rewriting now.
        self.run_op(interpreter, op.body.block.last_op, add_to_scope=True)

        interpreter.pop_scope()
        return ()

    @impl(pdl.ResultOp)
    def run_result(
        self, interpreter: Interpreter, op: pdl.ResultOp, args: PythonValues
    ) -> PythonValues:
        # print("running result")
        owner: Op = args[0]
        index = op.index.value.data
        return (Value(index=index, op=args[0], type=owner.result_types[index]),)

    @impl(pdl.ReplaceOp)
    def run_replace(
        self, interpreter: Interpreter, op: pdl.ReplaceOp, args: PythonValues
    ) -> PythonValues:
        if self.get_state(interpreter, DataKeys.PHASE) == Phase.INIT:
            return ()
        elif self.get_state(interpreter, DataKeys.PHASE) == Phase.REWRITING:
            # Check number of replacement values matches
            replaced_op = op.op_value
            num_replacements = (
                len(op.repl_values)
                if op.repl_values
                else len(op.repl_operation.owner.type_values)
            )
            if len(replaced_op.owner.type_values) != num_replacements:
                raise PDLAnalysisAborted(
                    op, "Number of replacement values and op results must match"
                )
            # TODO: Check replacement with self

            # update the scope
            # I can simply look up the uses of this in the env and update there

            # Erasure of the replaced op
            self.remove_from_scope(interpreter, replaced_op)
            erased_op: Op = self.get_value(interpreter, replaced_op)
            self.get_state(interpreter, DataKeys.GENERATED_OPS).remove(erased_op)

        # TODO: If arbitrary stuff is replaced I should check whether the new value is
        # statically known to be before the old value. Otherwise it could be invalid.

        return ()

    @impl_terminator(pdl.RewriteOp)
    def run_rewrite(
        self, interpreter: Interpreter, op: pdl.RewriteOp, args: PythonValues
    ) -> PythonValues:
        # print("running rewrite")
        if op.root is None:
            raise PDLAnalysisException(op, "RewriteOp must have a root")
        else:
            self.set_state(
                interpreter, DataKeys.ROOT_OP, self.get_value(interpreter, op.root)
            )

        if self.get_state(interpreter, DataKeys.PHASE) == Phase.INIT:
            if op.body:
                for nested_op in op.body.blocks[0].ops:
                    self.run_op(interpreter, nested_op, add_to_scope=True)
            return ReturnedValues(()), ()

        if self.get_state(interpreter, DataKeys.PHASE) == Phase.MATCHING:
            # To initialize the results taken of ops
            for nested_op in op.body.blocks[0].ops:
                self.run_op(interpreter, nested_op, add_to_scope=False)

        self.set_state(interpreter, DataKeys.PHASE, Phase.REWRITING)

        if op.body is None:
            return ReturnedValues(()), ()

        for nested_op in op.body.blocks[0].ops:
            self.run_op(interpreter, nested_op, add_to_scope=False)

        return ReturnedValues(()), ()

    @impl(pdl.TypeOp)
    def run_type(
        self, interpreter: Interpreter, op: pdl.TypeOp, args: PythonValues
    ) -> PythonValues:
        # print("running type")
        return (Type(op.constantType if op.constantType else None),)


## Datastructures for analysis


@dataclass
class Attribute:
    # TODO: Should these be xdsl attributes?
    type: Attribute | None
    value: Attribute | None

    def __repr__(self) -> str:
        return f"attr"


@dataclass
class Type:
    type: Attribute | None = None

    def __repr__(self) -> str:
        return f"type"


@dataclass
class Value:
    index: int | None = None
    op: Op | None = None
    type: Type | None = None
    in_scope: bool = True

    def __repr__(self) -> str:
        return f"Val"


@dataclass()
class Op:
    name: str | None = None
    attribute_values: list[Attribute] = field(default_factory=list)
    operands: list[Value] = field(default_factory=list)
    result_types: list[Type] = field(default_factory=list)
    results_taken: list[Value] = field(default_factory=list)
    in_scope: bool = True

    def __repr__(self) -> str:
        return f"{self.name}({self.operands})"
