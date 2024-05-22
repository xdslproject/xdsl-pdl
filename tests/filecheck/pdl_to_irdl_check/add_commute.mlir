// RUN: test-pdl-to-irdl-check %s | filecheck %s

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

// CHECK:       irdl_ext.check_subset {
// CHECK-NEXT:    %match_op_index = irdl.parametric @builtin::@index<>
// CHECK-NEXT:    %0 = irdl.base "#int" {"base_name" = "#int"}
// CHECK-NEXT:    %match_op_integer = irdl.parametric @builtin::@integer_type<%0>
// CHECK-NEXT:    %match_op_t = irdl.any_of(%match_op_index, %match_op_integer)
// CHECK-NEXT:    irdl_ext.yield {"name_hints" = ["match_x", "match_y", "match_op_result_0_"]} %match_op_t, %match_op_t, %match_op_t
// CHECK-NEXT:  } of {
// CHECK-NEXT:    %rewrite_new_op_index = irdl.parametric @builtin::@index<>
// CHECK-NEXT:    %1 = irdl.base "#int" {"base_name" = "#int"}
// CHECK-NEXT:    %rewrite_new_op_integer = irdl.parametric @builtin::@integer_type<%1>
// CHECK-NEXT:    %rewrite_new_op_t = irdl.any_of(%rewrite_new_op_index, %rewrite_new_op_integer)
// CHECK-NEXT:    irdl_ext.match %rewrite_new_op_t
// CHECK-NEXT:    irdl_ext.yield {"name_hints" = ["rewrite_x", "rewrite_y", "rewrite_op_result_0_"]} %rewrite_new_op_t, %rewrite_new_op_t, %rewrite_new_op_t
// CHECK-NEXT:  }




