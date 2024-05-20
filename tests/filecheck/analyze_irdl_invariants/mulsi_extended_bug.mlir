// RUN: analyze-irdl-invariants %s %S/mulsi_example.irdl | filecheck %s

pdl.pattern @MulSIExtendedRHSOne : benefit(0) {
    %t = pdl.type
    %x = pdl.operand : %t
    %one = pdl.attribute : %t
    pdl.apply_native_constraint "is_one"(%one : !pdl.attribute)
    %one_op = pdl.operation "arith.constant" {"value" = %one} -> (%t : !pdl.type)
    %one_val = pdl.result 0 of %one_op

    %root = pdl.operation "arith.mulsi_extended"(%x, %one_val : !pdl.value, !pdl.value) -> (%t, %t : !pdl.type, !pdl.type)
    pdl.rewrite %root {
        %zero = pdl.apply_native_rewrite "get_zero"(%t : !pdl.type) : !pdl.attribute
        %zero_op = pdl.operation "arith.constant" {"value" = %zero} -> (%t : !pdl.type)
        %zero_val = pdl.result 0 of %zero_op

        %two = pdl.attribute = 2 : i64
        %i1 = pdl.type : i1
        %cmpi_op = pdl.operation "arith.cmpi"(%x, %zero_val : !pdl.value, !pdl.value) {"predicate" = %two} -> (%i1 : !pdl.type)
        %cmpi_val = pdl.result 0 of %cmpi_op

        %extsi_op = pdl.operation "arith.extsi"(%cmpi_val : !pdl.value) -> (%t : !pdl.type)
        %extsi_val = pdl.result 0 of %extsi_op

        pdl.replace %root with (%x, %extsi_val : !pdl.value, !pdl.value)
    }
}

// CHECK: PDL rewrite may break IRDL invariants