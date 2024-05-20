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


// CHECK:      irdl_ext.check_subset {
// CHECK-NEXT:   %0 = irdl.any
// CHECK-NEXT:   %1 = irdl.any
// CHECK-NEXT:   %2 = irdl.parametric @builtin::@integer_attr<%1, %0>
// CHECK-NEXT:   %3 = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:   %4 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:   %5 = irdl.any_of(%3, %4)
// CHECK-NEXT:   irdl_ext.eq %5, %0
// CHECK-NEXT:   %6 = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:   %7 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:   %8 = irdl.any_of(%6, %7)
// CHECK-NEXT:   irdl_ext.eq %8, %0
// CHECK-NEXT:   irdl_ext.eq %8, %0
// CHECK-NEXT:   irdl_ext.eq %8, %0
// CHECK-NEXT:   irdl_ext.eq %8, %0
// CHECK-NEXT:   irdl_ext.yield %0, %0, %0, %0
// CHECK-NEXT: } of {
// CHECK-NEXT:   %9 = irdl.any
// CHECK-NEXT:   %10 = irdl.any
// CHECK-NEXT:   %11 = irdl.parametric @builtin::@integer_attr<%10, %9>
// CHECK-NEXT:   %12 = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:   %13 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:   %14 = irdl.any_of(%12, %13)
// CHECK-NEXT:   irdl_ext.eq %14, %9
// CHECK-NEXT:   %15 = irdl.any
// CHECK-NEXT:   %16 = irdl.parametric @builtin::@integer_attr<%15, %9>
// CHECK-NEXT:   %17 = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:   %18 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:   %19 = irdl.any_of(%17, %18)
// CHECK-NEXT:   irdl_ext.eq %19, %9
// CHECK-NEXT:   %20 = irdl.is 2 : i64
// CHECK-NEXT:   %21 = irdl.is i1
// CHECK-NEXT:   %22 = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:   %23 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:   %24 = irdl.any_of(%22, %23)
// CHECK-NEXT:   %25 = irdl.is i1
// CHECK-NEXT:   irdl_ext.eq %24, %9
// CHECK-NEXT:   irdl_ext.eq %24, %9
// CHECK-NEXT:   irdl_ext.eq %25, %21
// CHECK-NEXT:   %26 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:   %27 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:   irdl_ext.eq %26, %21
// CHECK-NEXT:   irdl_ext.eq %27, %9
// CHECK-NEXT:   %28 = irdl.base @builtin::@index {"base_ref" = @builtin::@index}
// CHECK-NEXT:   %29 = irdl.base @builtin::@integer_type {"base_ref" = @builtin::@integer_type}
// CHECK-NEXT:   %30 = irdl.any_of(%28, %29)
// CHECK-NEXT:   irdl_ext.eq %30, %9
// CHECK-NEXT:   irdl_ext.eq %30, %9
// CHECK-NEXT:   irdl_ext.eq %30, %9
// CHECK-NEXT:   irdl_ext.eq %30, %9
// CHECK-NEXT:   irdl_ext.yield %9, %9, %9, %9
// CHECK-NEXT: }
