irdl.dialect @builtin {
    irdl.type @index

    irdl.type @integer_type {
        %bitwidth = irdl.base "#int"
        irdl.parameters(%bitwidth)
    }

    irdl.attribute @integer_attr {
        %index = irdl.base @index
        %integer = irdl.base @integer_type
        %t = irdl.any_of(%index, %integer)
        %value = irdl.any
        irdl.parameters(%value, %t)
    }
}

irdl.dialect @arith {
    irdl.operation @constant {
        // %value = irdl.base @builtin::@integer_attr
        // irdl.attributes { "value" = %value}
        %index = irdl.base @builtin::@index
        %integer = irdl.base @builtin::@integer_type
        %t = irdl.any_of(%index, %integer)
        irdl.results(%t)
    }

    irdl.operation @addi {
        %index = irdl.base @builtin::@index
        %integer = irdl.base @builtin::@integer_type
        %t = irdl.any_of(%index, %integer)
        irdl.operands(%t, %t)
        irdl.results(%t)
    }
}

pdl.pattern @AddCommute : benefit(0) {
    %t = pdl.type
    %x = pdl.operand : %t
    %y = pdl.operand : %t
    %op = pdl.operation "arith.addi"(%x, %y : !pdl.value, !pdl.value) -> (%t : !pdl.type)
    pdl.rewrite %op {
        %new_op = pdl.operation "arith.addi"(%y, %x : !pdl.value, !pdl.value) -> (%t : !pdl.type)
        pdl.replace %op with %new_op
    }
}
