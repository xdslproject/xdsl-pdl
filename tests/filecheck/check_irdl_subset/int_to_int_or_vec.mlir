// RUN: test-check-irdl-subset %s | filecheck %s

// Check that int is a subset of int | vec

irdl.dialect @builtin {
  irdl.attribute @integer {
    %0 = irdl.any
    irdl.parameters(%0)
  }

  irdl.attribute @vector {
    %shape = irdl.any
    %type = irdl.any
    irdl.parameters(%shape, %type)
  }
}

irdl_ext.check_subset {
  %0 = irdl.any
  %int = irdl.parametric @builtin::@integer<%0>
  irdl_ext.yield %int
} of {
  %0 = irdl.any
  %1 = irdl.any
  %2 = irdl.any
  %int = irdl.parametric @builtin::@integer<%0>
  %vec = irdl.parametric @builtin::@vector<%1, %2>
  %res = irdl.any_of(%int, %vec)
  irdl_ext.yield %res
}

// CHECK: lhs is a subset of rhs
