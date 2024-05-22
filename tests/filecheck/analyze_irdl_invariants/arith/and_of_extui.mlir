// RUN: analyze-irdl-invariants %s %S/arith.irdl | filecheck %s

// and extui(x), extui(y) -> extui(and(x,y))
pdl.pattern @AndOfExtUI : benefit(0) {
    %type = pdl.type
    %new_type = pdl.type

    pdl.apply_native_constraint "is_greater_integer_type"(%new_type, %type : !pdl.type, !pdl.type)
    pdl.apply_native_constraint "is_tensor"(%type : !pdl.type)
    pdl.apply_native_constraint "is_tensor"(%new_type : !pdl.type)

    %i64 = pdl.type : i64

    %x = pdl.operand : %type
    %y = pdl.operand : %type

    %extui_x_op = pdl.operation "arith.extui"(%x : !pdl.value) -> (%new_type : !pdl.type)
    %extui_x = pdl.result 0 of %extui_x_op

    %extui_y_op = pdl.operation "arith.extui"(%y : !pdl.value) -> (%new_type : !pdl.type)
    %extui_y = pdl.result 0 of %extui_y_op

    %and_op = pdl.operation "arith.andi"(%extui_x, %extui_y : !pdl.value, !pdl.value) -> (%new_type : !pdl.type)

    pdl.rewrite %and_op {
        %new_and = pdl.operation "arith.andi"(%x, %y : !pdl.value, !pdl.value) -> (%type : !pdl.type)
        %and = pdl.result 0 of %new_and

        %new_extui = pdl.operation "arith.extui"(%and : !pdl.value) -> (%new_type : !pdl.type)
        pdl.replace %and_op with %new_extui
    }
}

// CHECK: PDL rewrite will not break IRDL invariants