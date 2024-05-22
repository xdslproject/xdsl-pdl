// RUN: analyze-irdl-invariants %s %S/arith.irdl | filecheck %s

// addi(x, muli(y, -1)) -> subi(x, y)
pdl.pattern @AddIMulNegativeOneRhs : benefit(0) {
    %type = pdl.type

    %x = pdl.operand : %type
    %y = pdl.operand : %type
    %m1_attr = pdl.attribute : %type

    pdl.apply_native_constraint "is_minus_one"(%m1_attr : !pdl.attribute)

    %m1_op = pdl.operation "arith.constant" {"value" = %m1_attr} -> (%type : !pdl.type)
    %m1 = pdl.result 0 of %m1_op

    %mul_op = pdl.operation "arith.muli"(%y, %m1 : !pdl.value, !pdl.value) -> (%type : !pdl.type)
    %mul = pdl.result 0 of %mul_op

    %add = pdl.operation "arith.addi"(%x, %mul : !pdl.value, !pdl.value) -> (%type : !pdl.type)

    pdl.rewrite %add {
        %sub = pdl.operation "arith.subi"(%x, %y : !pdl.value, !pdl.value) -> (%type : !pdl.type)
        pdl.replace %add with %sub
    }
}

// CHECK: PDL rewrite will not break IRDL invariants