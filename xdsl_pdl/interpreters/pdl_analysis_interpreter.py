from __future__ import annotations
from dataclasses import dataclass, field
from email.policy import strict
from enum import Enum
from re import U
from typing import Any, List, Optional, Sequence
from pluggy import Result

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
    USE_CHECKING_STRICTNESS = "strictness"


class Phase(Enum):
    INIT = 0
    MATCHING = 1
    REWRITING = 2


class UseCheckingStrictness(Enum):
    STRICT = 0
    ASSUME_NO_USE_OUTSIDE = 1


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


def check_op_erased(interpreter: Interpreter, op: Operation) -> bool:
    for result in op.results:
        for use in result.uses:
            if isinstance(use.operation, pdl.EraseOp) or isinstance(
                use.operation, pdl.ReplaceOp
            ):
                return True
    return False


@register_impls
@dataclass
class PDLAnalysisFunctions(InterpreterFunctions):
    """
    Interpretation of PDL rewrite patterns for the purpose of analysis is
    divided into three phases:
    1. Init phase
    2. Matching phase
    3. Rewriting phase

    # Notes:
    - The use of operation results is modeled in the result_types of the op.
        All results taken via pdl.result always refer to the result_types of the
        op. This way the uses are modeled in one place and we don't have to care
        about updating them all over the place.
    - If a replacement of an op with another op happens, we introduce "virtual"
        pdl.Result ops to represent the results of the replacement op.
    """

    @staticmethod
    def run_op(
        interpreter: Interpreter, op: Operation, add_to_scope: bool = True
    ) -> None:
        # If op is not erased later check that all operands are in scope
        if not check_op_erased(interpreter, op):
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
    def _init_state() -> (
        dict[DataKeys, Phase | list[Op] | Optional[Op] | UseCheckingStrictness]
    ):
        return {
            DataKeys.PHASE: Phase.INIT,
            DataKeys.GENERATED_OPS: list(),
            DataKeys.ROOT_OP: None,
            DataKeys.USE_CHECKING_STRICTNESS: UseCheckingStrictness.STRICT,
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

    def check_no_uses(
        self, op_or_val: Op | Value | ResultType, interpreter: Interpreter
    ) -> None:
        # SETUP
        if isinstance(op_or_val, Op):
            op = op_or_val
            values: list[ResultType] = op_or_val.result_types
        elif isinstance(op_or_val, Value):
            if op_or_val.op:
                op = op_or_val.op
                values: list[ResultType] = [op_or_val.op.result_types[op_or_val.index]]
            else:
                raise ValueError("Can not check uses for Value not stemming from an op")
        else:
            op = op_or_val.op
            values = [op_or_val]

        # ACTUAL IMPLEMENTATION
        for value in values:
            if len(value.uses) > 0 and all(
                isinstance(use, UnknownUse) for use in value.uses
            ):
                raise PDLAnalysisAborted(
                    self.get_actual(interpreter, op).owner,
                    "Erased or replaced Op might have uses outside of the matched IR.",
                )
            if len(value.uses) > 0:
                raise PDLAnalysisAborted(
                    self.get_actual(interpreter, op).owner,
                    f"Value {value} still has {len(value.uses)} uses.",
                )

    def remove_from_scope(
        self, interpreter: Interpreter, value: SSAValue | Value | Op
    ) -> None:
        if isinstance(value, SSAValue):
            op_or_val = interpreter.get_values([value])[0]
        else:
            op_or_val = value
        op_or_val.in_scope = False
        # print(f"removing {op_or_val} from scope")
        self.check_no_uses(op_or_val, interpreter)
        if isinstance(op_or_val, Op):
            # For ops remove all uses of the operands (if they stem from ops)
            for operand in op_or_val.operands:
                if operand.op:
                    operand.uses.remove(op_or_val)
        elif isinstance(op_or_val, Value):
            # if OpResult then remove the op that created this value from the scope as well
            if op_or_val.op and op_or_val.op.in_scope:
                self.remove_from_scope(interpreter, op_or_val.op)
        if not isinstance(op_or_val, SSAValue):
            actual_value = self.get_actual(interpreter, op_or_val)
        else:
            actual_value = op_or_val
        interpreter.set_values([(actual_value, op_or_val)])

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
        if self.get_state(interpreter, DataKeys.PHASE) == Phase.INIT:
            return (Attribute(type=None, value=None),)
        elif self.get_state(interpreter, DataKeys.PHASE) == Phase.MATCHING:
            pdl_op = self.get_value(interpreter, op.results[0])
            pdl_op.matched = True
            return (pdl_op,)
        else:
            pdl_op = self.get_value(interpreter, op.results[0])
            return (pdl_op,)

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
        if self.get_state(interpreter, DataKeys.PHASE) == Phase.INIT:
            return (Value(type=args[0] if len(args) > 0 else None),)
        elif self.get_state(interpreter, DataKeys.PHASE) == Phase.MATCHING:
            pdl_op = self.get_value(interpreter, op.results[0])
            pdl_op.matched = True
            self.run_op(interpreter, op.operands[0].owner, add_to_scope=False)
            return (pdl_op,)
        else:
            pdl_op = self.get_value(interpreter, op.results[0])
            return (pdl_op,)

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
        def init_uses() -> list[Op | UnknownUse]:
            # Add an unknown use if the op stems from the matching portion and
            # we strict checking is enabled
            strictness = self.get_state(interpreter, DataKeys.USE_CHECKING_STRICTNESS)
            if strictness == UseCheckingStrictness.STRICT and not isinstance(
                op.parent_op(), pdl.RewriteOp
            ):
                return [UnknownUse()]
            else:
                return []

        pdl_op = Op(
            name=op.opName if op.opName else None,
            attribute_values=args[: len(op.attributeValueNames)],
            operands=list(
                args[
                    len(op.attributeValueNames) : len(op.attributeValueNames)
                    + len(op.operand_values)
                ]
            ),
            result_types=[
                ResultType(uses=init_uses(), type=type)
                for type in args[len(op.attributeValueNames) + len(op.operand_values) :]
            ],
        )
        for operand in op.operand_values:
            self.get_value(interpreter, operand).uses.append(pdl_op)
        # The uses in pdl.ResultOp ops are not known yet.

        return (pdl_op,)

    def match_operation(
        self, interpreter: Interpreter, op: pdl.OperationOp, args: PythonValues
    ):
        pdl_op = interpreter.get_values([op.results[0]])[0]
        pdl_op.matched = True
        # record uses in pdl.ResultOp ops
        for use in op.results[0].uses:
            if isinstance(use.operation, pdl.ResultOp) | isinstance(
                use.operation, pdl.ResultsOp
            ):
                pdl_op.results_taken.append(
                    self.get_value(interpreter, use.operation.results[0])
                )
        # match the operands that stem form pdl.operation ops

        for operand in op.operands:
            self.run_op(
                interpreter,
                operand.owner,
                add_to_scope=False,
            )

        return (pdl_op,)

    def run_operation(
        self, interpreter: Interpreter, op: pdl.OperationOp, args: PythonValues
    ) -> PythonValues:
        pdl_op = interpreter.get_values([op.results[0]])[0]

        # Check that this does not use the root
        for operand in pdl_op.operands:
            # Check that op is not erased afterwards
            if operand.op == self.get_state(
                interpreter, DataKeys.ROOT_OP
            ) and not check_op_erased(interpreter, op):
                raise PDLAnalysisAborted(
                    op, "Rewrite operation uses the root as an operand."
                )

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
        def check_matching_is_connected_component(
            interpreter: Interpreter, op: pdl.PatternOp
        ):
            for nested_op in op.body.block.ops:
                if isinstance(nested_op, pdl.RewriteOp) or isinstance(
                    nested_op, pdl.ResultOp
                ):
                    continue
                if not self.get_value(interpreter, nested_op.results[0]).matched:
                    raise PDLAnalysisAborted(
                        nested_op, "Matching is not a connected component."
                    )

        interpreter.push_scope(op.sym_name if op.sym_name else "pattern")

        for nested_op in op.body.block.ops:
            self.run_op(interpreter, nested_op, add_to_scope=True)

        # Check pattern ends with a rewrite operation
        if not isinstance(rewrite_op := op.body.block.last_op, pdl.RewriteOp):
            raise PDLAnalysisException(op, "Pattern does not end with a rewrite")
        if rewrite_op.root:
            root_op = self.get_value(interpreter, rewrite_op.root)
        else:
            raise PDLAnalysisException(
                op, "Rewrites without explicit root are not supported."
            )

        self.set_state(interpreter, DataKeys.PHASE, Phase.MATCHING)
        self.run_op(
            interpreter, self.get_actual(interpreter, root_op).owner, add_to_scope=False
        )
        # for nested_op in op.body.block.ops_reverse:
        #     if isinstance(nested_op, pdl.RewriteOp):
        #         continue
        #     self.run_op(interpreter, nested_op, add_to_scope=False)
        check_matching_is_connected_component(interpreter, op)

        # Matching ready, simulating the rewriting now.
        # Add the root op to the generated ops for modeling the insertion point
        self.get_state(interpreter, DataKeys.GENERATED_OPS).append(root_op)
        self.run_op(interpreter, op.body.block.last_op, add_to_scope=True)

        interpreter.pop_scope()
        return ()

    @impl(pdl.ResultOp)
    def run_result(
        self, interpreter: Interpreter, op: pdl.ResultOp, args: PythonValues
    ) -> PythonValues:
        # print("running result")
        if self.get_state(interpreter, DataKeys.PHASE) == Phase.INIT:
            owner: Op = args[0]
            index = op.index.value.data
            return (Value(index=index, op=args[0], type=owner.result_types[index]),)
        elif self.get_state(interpreter, DataKeys.PHASE) == Phase.MATCHING:
            pdl_op = self.get_value(interpreter, op.results[0])
            pdl_op.matched = True
            self.run_op(interpreter, op.operands[0].owner, add_to_scope=False)
            return (pdl_op,)
        else:
            pdl_op = self.get_value(interpreter, op.results[0])
            return (pdl_op,)

    @impl(pdl.ReplaceOp)
    def run_replace(
        self, interpreter: Interpreter, op: pdl.ReplaceOp, args: PythonValues
    ) -> PythonValues:
        # HELPERS
        def check_num_replacement_matches(op: pdl.ReplaceOp):
            replaced_pdl_op = op.op_value
            num_replacements = (
                len(op.repl_values)
                if op.repl_values
                else len(op.repl_operation.owner.type_values)
            )
            if len(replaced_pdl_op.owner.type_values) != num_replacements:
                raise PDLAnalysisAborted(
                    op, "Number of replacement values and op results must match"
                )

        def is_self_replacement(op: Op, repl_values: list[ResultType]) -> bool:
            for repl_value in repl_values:
                if repl_value.op == op:
                    return True
            return False

        def replace_uses(
            replaced_op: Op,
            replacements: Sequence[Value | ResultType],
        ):
            for type_result, replacement in zip(replaced_op.result_types, replacements):
                if isinstance(replacement, ResultType):
                    replacement = Value(
                        op=replacement.op,
                        index=replacement.index,
                        type=replacement.type,
                    )

                replacement.uses.extend(type_result.uses)

                # replace the actual use (i.e. the operand of the user op)
                for user in type_result.uses:
                    if isinstance(user, UnknownUse):
                        continue
                    for i, operand in enumerate(user.operands):
                        if operand.op == replaced_op:
                            user.operands[i] = replacement

                type_result.uses = []

        replaced_pdl_op = op.op_value
        # ACTUAL IMPLEMENTATION
        if self.get_state(interpreter, DataKeys.PHASE) == Phase.INIT:
            return ()
        elif self.get_state(interpreter, DataKeys.PHASE) == Phase.REWRITING:
            replaced_op = self.get_value(interpreter, replaced_pdl_op)
            repl_operation = (
                self.get_value(interpreter, op.repl_operation)
                if op.repl_operation
                else None
            )
            repl_values = (
                [self.get_value(interpreter, repl) for repl in op.repl_values]
                if op.repl_values
                else repl_operation.result_types  # type: ignore
            )
            # Check number of replacement values matches. If the replaced op has
            # no results this is considered legal in any case.
            # if len(replaced_op.result_types) > 0:
            check_num_replacement_matches(op)
            if not is_self_replacement(replaced_op, repl_values):
                # update the uses
                replace_uses(replaced_op, repl_values)

            # Erasure of the replaced op
            self.remove_from_scope(interpreter, replaced_pdl_op)
            erased_op: Op = self.get_value(interpreter, replaced_pdl_op)
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
        if self.get_state(interpreter, DataKeys.PHASE) == Phase.INIT:
            return (Type(op.constantType if op.constantType else None),)
        elif self.get_state(interpreter, DataKeys.PHASE) == Phase.MATCHING:
            pdl_op = self.get_value(interpreter, op.result)
            pdl_op.matched = True
            return (pdl_op,)
        else:
            pdl_op = self.get_value(interpreter, op.result)
            return (pdl_op,)


## Datastructures for analysis


@dataclass
class Attribute:
    # TODO: Should these be xdsl attributes?
    type: Attribute | None
    value: Attribute | None
    matched: bool = False

    def __repr__(self) -> str:
        return f"attr"


@dataclass
class Type:
    type: Attribute | None = None
    matched: bool = False

    def __repr__(self) -> str:
        return f"type"


@dataclass
class ResultType:
    uses: list[Op | UnknownUse]
    type: Type | None = None
    op: Op | None = None
    index: int | None = None

    def __repr__(self) -> str:
        return f"result_type"


@dataclass
class Value:
    index: int | None = None
    op: Op | None = None
    type: Type | None = None
    matched: bool = False

    @property
    def in_scope(self) -> bool:
        # The value is in scope if its op is in scope. If it does not stem from
        # an op, then it from pdl.operands and is always in scope.
        if self.op:
            return self.op.in_scope
        else:
            return True

    @in_scope.setter
    def in_scope(self, value: bool) -> None:
        if self.op:
            self.op.in_scope = value
        else:
            raise ValueError(
                "Cannot set in_scope for value that does not stem from an op"
            )

    @property
    def uses(self) -> list[Op | UnknownUse]:
        if self.op:
            return self.op.result_types[0 if not self.index else self.index].uses
        else:
            return []

    def __repr__(self) -> str:
        return f"Val"


@dataclass(eq=False)
class Op:
    name: str | None = None
    attribute_values: list[Attribute] = field(default_factory=list)
    operands: list[Value] = field(default_factory=list)
    result_types: list[ResultType] = field(default_factory=list)
    results_taken: list[Value] = field(default_factory=list)
    in_scope: bool = True
    matched: bool = False

    def __post_init__(self) -> None:
        for i, result_type in enumerate(self.result_types):
            result_type.op = self
            result_type.index = i

    def __repr__(self) -> str:
        return f"{self.name}({self.operands})"


@dataclass(eq=True)
class UnknownUse:
    pass
