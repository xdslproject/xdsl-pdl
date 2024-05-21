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

    irdl.operation @mulsi_extended {
        %index = irdl.base @builtin::@index
        %integer = irdl.base @builtin::@integer_type
        %t = irdl.any_of(%index, %integer)
        irdl.operands(%t, %t)
        irdl.results(%t, %t)
    }

    irdl.operation @cmpi {
        %index = irdl.base @builtin::@index
        %integer = irdl.base @builtin::@integer_type
        %t = irdl.any_of(%index, %integer)
        %i1 = irdl.is i1
        irdl.operands(%t, %t)
        // irdl.attributes { "predicate" = ... }
        irdl.results(%i1)
    }

    irdl.operation @extsi {
        %integer1 = irdl.base @builtin::@integer_type
        %integer2 = irdl.base @builtin::@integer_type
        irdl.operands(%integer1)
        irdl.results(%integer2)
    }
}

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

// CHECK:        irdl_ext.check_subset {
// CHECK-NEXT:     %match_one_op_index = irdl.parametric @builtin::@index<>
// CHECK-NEXT:     %0 = irdl.base "#int" {"base_name" = "#int"}
// CHECK-NEXT:     %match_one_op_integer = irdl.parametric @builtin::@integer_type<%0>
// CHECK-NEXT:     %match_one_op_t = irdl.any_of(%match_one_op_index, %match_one_op_integer)
// CHECK-NEXT:     %match_root_index = irdl.parametric @builtin::@index<>
// CHECK-NEXT:     %1 = irdl.base "#int" {"base_name" = "#int"}
// CHECK-NEXT:     %match_root_integer = irdl.parametric @builtin::@integer_type<%1>
// CHECK-NEXT:     %match_root_t = irdl.any_of(%match_root_index, %match_root_integer)
// CHECK-NEXT:     %2 = irdl.all_of(%match_root_t, %match_one_op_t)
// CHECK-NEXT:     irdl_ext.yield %2, %2, %2, %2
// CHECK-NEXT:   } of {
// CHECK-NEXT:     %rewrite_one_op_index = irdl.parametric @builtin::@index<>
// CHECK-NEXT:     %3 = irdl.base "#int" {"base_name" = "#int"}
// CHECK-NEXT:     %rewrite_one_op_integer = irdl.parametric @builtin::@integer_type<%3>
// CHECK-NEXT:     %rewrite_one_op_t = irdl.any_of(%rewrite_one_op_index, %rewrite_one_op_integer)
// CHECK-NEXT:     %rewrite_zero_op_index = irdl.parametric @builtin::@index<>
// CHECK-NEXT:     %4 = irdl.base "#int" {"base_name" = "#int"}
// CHECK-NEXT:     %rewrite_zero_op_integer = irdl.parametric @builtin::@integer_type<%4>
// CHECK-NEXT:     %rewrite_zero_op_t = irdl.any_of(%rewrite_zero_op_index, %rewrite_zero_op_integer)
// CHECK-NEXT:     %rewrite_cmpi_op_index = irdl.parametric @builtin::@index<>
// CHECK-NEXT:     %5 = irdl.base "#int" {"base_name" = "#int"}
// CHECK-NEXT:     %rewrite_cmpi_op_integer = irdl.parametric @builtin::@integer_type<%5>
// CHECK-NEXT:     %rewrite_cmpi_op_t = irdl.any_of(%rewrite_cmpi_op_index, %rewrite_cmpi_op_integer)
// CHECK-NEXT:     %6 = irdl.base "#int" {"base_name" = "#int"}
// CHECK-NEXT:     %rewrite_extsi_op_integer2 = irdl.parametric @builtin::@integer_type<%6>
// CHECK-NEXT:     %rewrite_root_index = irdl.parametric @builtin::@index<>
// CHECK-NEXT:     %7 = irdl.base "#int" {"base_name" = "#int"}
// CHECK-NEXT:     %rewrite_root_integer = irdl.parametric @builtin::@integer_type<%7>
// CHECK-NEXT:     %rewrite_root_t = irdl.any_of(%rewrite_root_index, %rewrite_root_integer)
// CHECK-NEXT:     %8 = irdl.all_of(%rewrite_root_t, %rewrite_extsi_op_integer2, %rewrite_cmpi_op_t, %rewrite_zero_op_t, %rewrite_one_op_t)
// CHECK-NEXT:     irdl_ext.yield %8, %8, %8, %8
// CHECK-NEXT:   }

