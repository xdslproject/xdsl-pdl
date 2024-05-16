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
