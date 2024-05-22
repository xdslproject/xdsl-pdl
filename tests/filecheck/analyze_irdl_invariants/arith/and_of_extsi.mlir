// RUN: analyze-irdl-invariants %s %S/arith.irdl | filecheck %s

// and extsi(x), extsi(y) -> extsi(and(x,y))
pdl.pattern @AndOfExtSI : benefit(0) {
    %type = pdl.type
    %new_type = pdl.type

    pdl.apply_native_constraint "is_greater_integer_type"(%new_type, %type : !pdl.type, !pdl.type)
    pdl.apply_native_constraint "is_tensor"(%type : !pdl.type)
    pdl.apply_native_constraint "is_tensor"(%new_type : !pdl.type)

    %i64 = pdl.type : i64

    %x = pdl.operand : %type
    %y = pdl.operand : %type

    %extsi_x_op = pdl.operation "arith.extsi"(%x : !pdl.value) -> (%new_type : !pdl.type)
    %extsi_x = pdl.result 0 of %extsi_x_op

    %extsi_y_op = pdl.operation "arith.extsi"(%y : !pdl.value) -> (%new_type : !pdl.type)
    %extsi_y = pdl.result 0 of %extsi_y_op

    %and_op = pdl.operation "arith.andi"(%extsi_x, %extsi_y : !pdl.value, !pdl.value) -> (%new_type : !pdl.type)

    pdl.rewrite %and_op {
        %new_and = pdl.operation "arith.andi"(%x, %y : !pdl.value, !pdl.value) -> (%type : !pdl.type)
        %and = pdl.result 0 of %new_and

        %new_extsi = pdl.operation "arith.extsi"(%and : !pdl.value) -> (%new_type : !pdl.type)
        pdl.replace %and_op with %new_extsi
    }
}

// CHECK: PDL rewrite will not break IRDL invariants