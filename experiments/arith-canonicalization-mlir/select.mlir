// RUN: analyze-irdl-invariants %s arith.irdl | FileCheck %s

builtin.module {
    // select(not(pred), a, b) => select(pred, b, a)
    pdl.pattern @SelectNotCond : benefit(0) {
        %i1 = pdl.type : i1
        %type = pdl.type : !transfer.integer

        %pred = pdl.operand : %i1
        %a = pdl.operand : %type
        %b = pdl.operand : %type

        %one_attr = pdl.attribute = 1 : i1
        %one_op = pdl.operation "arith.constant" {"value" = %one_attr} -> (%i1 : !pdl.type)
        %one = pdl.result 0 of %one_op

        %not_pred_op = pdl.operation "arith.xori"(%pred, %one : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
        %not_pred = pdl.result 0 of %not_pred_op

        %select_op = pdl.operation "arith.select"(%not_pred, %a, %b : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)

        pdl.rewrite %select_op {
            %new_select_op = pdl.operation "arith.select"(%pred, %b, %a : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
            pdl.replace %select_op with %new_select_op
        }
    }

    // select(pred, select(pred, a, b), c) => select(pred, a, c)
    pdl.pattern @RedundantSelectTrue : benefit(0) {
        %i1 = pdl.type : i1
        %type = pdl.type : !transfer.integer

        %pred = pdl.operand : %i1
        %a = pdl.operand : %type
        %b = pdl.operand : %type
        %c = pdl.operand : %type

        %select_op = pdl.operation "arith.select"(%pred, %a, %b : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
        %select = pdl.result 0 of %select_op

        %select_op2 = pdl.operation "arith.select"(%pred, %select, %c : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)

        pdl.rewrite %select_op2 {
            %new_select_op = pdl.operation "arith.select"(%pred, %a, %c : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
            pdl.replace %select_op2 with %new_select_op
        }
    }

    // select(pred, a, select(pred, b, c)) => select(pred, a, c)
    pdl.pattern @RedundantSelectFalse : benefit(0) {
        %i1 = pdl.type : i1
        %type = pdl.type : !transfer.integer

        %pred = pdl.operand : %i1
        %a = pdl.operand : %type
        %b = pdl.operand : %type
        %c = pdl.operand : %type

        %select_op = pdl.operation "arith.select"(%pred, %b, %c : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
        %select = pdl.result 0 of %select_op

        %select_op2 = pdl.operation "arith.select"(%pred, %a, %select : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)

        pdl.rewrite %select_op2 {
            %new_select_op = pdl.operation "arith.select"(%pred, %a, %c : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
            pdl.replace %select_op2 with %new_select_op
        }
    }

    // Transforms a select of a boolean to arithmetic operations
    //
    //  arith.select %pred, %x, %y : i1
    //
    //  becomes
    //
    //  and(%pred, %x) or and(not(%pred), %y) where not(x) = xor(x, 1)
    pdl.pattern @SelectOrNotCond : benefit(0) {
        %i1 = pdl.type : i1

        %pred = pdl.operand : %i1
        %x = pdl.operand : %i1
        %y = pdl.operand : %i1

        %select_op = pdl.operation "arith.select"(%pred, %x, %y : !pdl.value, !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
        %select = pdl.result 0 of %select_op

        pdl.rewrite %select_op {
            %one_attr = pdl.attribute = 1 : i1
            %one_op = pdl.operation "arith.constant" {"value" = %one_attr} -> (%i1 : !pdl.type)
            %one = pdl.result 0 of %one_op

            %not_pred_op = pdl.operation "arith.xori"(%pred, %one : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            %not_pred = pdl.result 0 of %not_pred_op

            %x_choice_op = pdl.operation "arith.andi"(%pred, %x : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            %x_choice = pdl.result 0 of %x_choice_op

            %y_choice_op = pdl.operation "arith.andi"(%not_pred, %y : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            %y_choice = pdl.result 0 of %y_choice_op

            %res_op = pdl.operation "arith.ori"(%x_choice, %y_choice : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            pdl.replace %select_op with %res_op
        }
    }

    // select(predA, select(predB, x, y), y) => select(and(predA, predB), x, y)
    pdl.pattern @SelectAndCond : benefit(0) {
        %i1 = pdl.type : i1
        %type = pdl.type : !transfer.integer

        %predA = pdl.operand : %i1
        %predB = pdl.operand : %i1
        %x = pdl.operand : %type
        %y = pdl.operand : %type

        %select_op = pdl.operation "arith.select"(%predB, %x, %y : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
        %select = pdl.result 0 of %select_op

        %select_op2 = pdl.operation "arith.select"(%predA, %select, %y : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)

        pdl.rewrite %select_op2 {
            %and_op = pdl.operation "arith.andi"(%predA, %predB : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            %and = pdl.result 0 of %and_op

            %new_select_op = pdl.operation "arith.select"(%and, %x, %y : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
            pdl.replace %select_op2 with %new_select_op
        }
    }

    // select(predA, select(predB, y, x), y) => select(and(predA, not(predB)), x, y)
    pdl.pattern @SelectAndNotCond : benefit(0) {
        %i1 = pdl.type : i1
        %type = pdl.type : !transfer.integer

        %predA = pdl.operand : %i1
        %predB = pdl.operand : %i1
        %x = pdl.operand : %type
        %y = pdl.operand : %type

        %select_op = pdl.operation "arith.select"(%predB, %y, %x : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
        %select = pdl.result 0 of %select_op

        %select_op2 = pdl.operation "arith.select"(%predA, %select, %y : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)

        pdl.rewrite %select_op2 {
            %one_attr = pdl.attribute = 1 : i1
            %one_op = pdl.operation "arith.constant" {"value" = %one_attr} -> (%i1 : !pdl.type)
            %one = pdl.result 0 of %one_op

            %not_predB_op = pdl.operation "arith.xori"(%predB, %one : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            %not_predB = pdl.result 0 of %not_predB_op

            %and_op = pdl.operation "arith.andi"(%predA, %not_predB : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            %and = pdl.result 0 of %and_op

            %new_select_op = pdl.operation "arith.select"(%and, %x, %y : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
            pdl.replace %select_op2 with %new_select_op
        }
    }

    // select(predA, x, select(predB, x, y)) => select(or(predA, predB), x, y)
    pdl.pattern @SelectOrCond : benefit(0) {
        %i1 = pdl.type : i1
        %type = pdl.type : !transfer.integer

        %predA = pdl.operand : %i1
        %predB = pdl.operand : %i1
        %x = pdl.operand : %type
        %y = pdl.operand : %type

        %select_op = pdl.operation "arith.select"(%predB, %x, %y : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
        %select = pdl.result 0 of %select_op

        %select_op2 = pdl.operation "arith.select"(%predA, %x, %select : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)

        pdl.rewrite %select_op2 {
            %or_op = pdl.operation "arith.ori"(%predA, %predB : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            %or = pdl.result 0 of %or_op

            %new_select_op = pdl.operation "arith.select"(%or, %x, %y : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
            pdl.replace %select_op2 with %new_select_op
        }
    }

    // select(predA, x, select(predB, y, x)) => select(or(predA, not(predB)), x, y)
    pdl.pattern @SelectOrNotCond : benefit(0) {
        %i1 = pdl.type : i1
        %type = pdl.type : !transfer.integer

        %predA = pdl.operand : %i1
        %predB = pdl.operand : %i1
        %x = pdl.operand : %type
        %y = pdl.operand : %type

        %select_op = pdl.operation "arith.select"(%predB, %y, %x : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
        %select = pdl.result 0 of %select_op

        %select_op2 = pdl.operation "arith.select"(%predA, %x, %select : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)

        pdl.rewrite %select_op2 {
            %one_attr = pdl.attribute = 1 : i1
            %one_op = pdl.operation "arith.constant" {"value" = %one_attr} -> (%i1 : !pdl.type)
            %one = pdl.result 0 of %one_op

            %not_predB_op = pdl.operation "arith.xori"(%predB, %one : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            %not_predB = pdl.result 0 of %not_predB_op

            %and_op = pdl.operation "arith.ori"(%predA, %not_predB : !pdl.value, !pdl.value) -> (%i1 : !pdl.type)
            %and = pdl.result 0 of %and_op

            %new_select_op = pdl.operation "arith.select"(%and, %x, %y : !pdl.value, !pdl.value, !pdl.value) -> (%type : !pdl.type)
            pdl.replace %select_op2 with %new_select_op
        }
    }
}

// CHECK: All patterns will not break IRDL invariants
