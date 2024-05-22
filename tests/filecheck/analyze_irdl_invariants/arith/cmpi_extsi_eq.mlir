// RUN: analyze-irdl-invariants %s %S/arith.irdl | filecheck %s

// cmpi(==, a extsi iNN, b extsi iNN) -> cmpi(==, a, b)
pdl.pattern @CmpIExtSIEq : benefit(0) {
    %type = pdl.type
    %new_type = pdl.type
    %i1 = pdl.type : i1

    pdl.apply_native_constraint "is_greater_integer_type"(%new_type, %type : !pdl.type, !pdl.type)

    %a = pdl.operand : %type
    %b = pdl.operand : %type

    %eq_predicate = pdl.attribute = 0 : i64

    %extsi_a_op = pdl.operation "arith.extsi"(%a : !pdl.value) -> (%new_type : !pdl.type)
    %extsi_a = pdl.result 0 of %extsi_a_op

    %extsi_b_op = pdl.operation "arith.extsi"(%b : !pdl.value) -> (%new_type : !pdl.type)
    %extsi_b = pdl.result 0 of %extsi_b_op

    %cmpi_op = pdl.operation "arith.cmpi"(%extsi_a, %extsi_b : !pdl.value, !pdl.value) {"predicate" = %eq_predicate} -> (%i1 : !pdl.type)

    %cmpi_op_res = pdl.result 0 of %cmpi_op

    pdl.rewrite %cmpi_op {
        %new_cmpi = pdl.operation "arith.cmpi"(%a, %b : !pdl.value, !pdl.value) {"predicate" = %eq_predicate} -> (%i1 : !pdl.type)
        pdl.replace %cmpi_op with %new_cmpi
    }
}

// CHECK: PDL rewrite will not break IRDL invariants