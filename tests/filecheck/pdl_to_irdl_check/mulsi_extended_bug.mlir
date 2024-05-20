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
// CHECK-NEXT:     %match_t = irdl.any
// CHECK-NEXT:     %match_one = irdl.any
// CHECK-NEXT:     %match_one_1 = irdl.parametric @builtin::@integer_attr<%match_one, %match_t>
// CHECK-NEXT:     %match_one_op_index = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:     %match_one_op_integer = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:     %match_one_op_t = irdl.any_of(%match_one_op_index, %match_one_op_integer)
// CHECK-NEXT:     irdl_ext.eq %match_one_op_t, %match_t
// CHECK-NEXT:     %match_root_index = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:     %match_root_integer = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:     %match_root_t = irdl.any_of(%match_root_index, %match_root_integer)
// CHECK-NEXT:     irdl_ext.eq %match_root_t, %match_t
// CHECK-NEXT:     irdl_ext.eq %match_root_t, %match_t
// CHECK-NEXT:     irdl_ext.eq %match_root_t, %match_t
// CHECK-NEXT:     irdl_ext.eq %match_root_t, %match_t
// CHECK-NEXT:     irdl_ext.yield %match_t, %match_t, %match_t, %match_t
// CHECK-NEXT:   } of {
// CHECK-NEXT:     %rewrite_t = irdl.any
// CHECK-NEXT:     %rewrite_one = irdl.any
// CHECK-NEXT:     %rewrite_one_1 = irdl.parametric @builtin::@integer_attr<%rewrite_one, %rewrite_t>
// CHECK-NEXT:     %rewrite_one_op_index = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:     %rewrite_one_op_integer = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:     %rewrite_one_op_t = irdl.any_of(%rewrite_one_op_index, %rewrite_one_op_integer)
// CHECK-NEXT:     irdl_ext.eq %rewrite_one_op_t, %rewrite_t
// CHECK-NEXT:     %rewrite_zero = irdl.any
// CHECK-NEXT:     %rewrite_zero_1 = irdl.parametric @builtin::@integer_attr<%rewrite_zero, %rewrite_t>
// CHECK-NEXT:     %rewrite_zero_op_index = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:     %rewrite_zero_op_integer = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:     %rewrite_zero_op_t = irdl.any_of(%rewrite_zero_op_index, %rewrite_zero_op_integer)
// CHECK-NEXT:     irdl_ext.eq %rewrite_zero_op_t, %rewrite_t
// CHECK-NEXT:     %rewrite_two = irdl.is 2 : i64
// CHECK-NEXT:     %rewrite_i1 = irdl.is i1
// CHECK-NEXT:     %rewrite_cmpi_op_index = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:     %rewrite_cmpi_op_integer = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:     %rewrite_cmpi_op_t = irdl.any_of(%rewrite_cmpi_op_index, %rewrite_cmpi_op_integer)
// CHECK-NEXT:     %rewrite_cmpi_op_i1 = irdl.is i1
// CHECK-NEXT:     irdl_ext.eq %rewrite_cmpi_op_t, %rewrite_t
// CHECK-NEXT:     irdl_ext.eq %rewrite_cmpi_op_t, %rewrite_t
// CHECK-NEXT:     irdl_ext.eq %rewrite_cmpi_op_i1, %rewrite_i1
// CHECK-NEXT:     %rewrite_extsi_op_integer1 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:     %rewrite_extsi_op_integer2 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:     irdl_ext.eq %rewrite_extsi_op_integer1, %rewrite_i1
// CHECK-NEXT:     irdl_ext.eq %rewrite_extsi_op_integer2, %rewrite_t
// CHECK-NEXT:     %rewrite_root_index = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:     %rewrite_root_integer = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:     %rewrite_root_t = irdl.any_of(%rewrite_root_index, %rewrite_root_integer)
// CHECK-NEXT:     irdl_ext.eq %rewrite_root_t, %rewrite_t
// CHECK-NEXT:     irdl_ext.eq %rewrite_root_t, %rewrite_t
// CHECK-NEXT:     irdl_ext.eq %rewrite_root_t, %rewrite_t
// CHECK-NEXT:     irdl_ext.eq %rewrite_root_t, %rewrite_t
// CHECK-NEXT:     irdl_ext.yield %rewrite_t, %rewrite_t, %rewrite_t, %rewrite_t
// CHECK-NEXT:   }
