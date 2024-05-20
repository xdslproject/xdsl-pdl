// RUN: test-check-irdl-subset %s | filecheck %s

// Check that int | vec is not a subset of int

irdl.dialect @builtin {
  irdl.attribute @integer {
    %0 = irdl.any
    irdl.parameters(%0)
  }
}

irdl_ext.check_subset {
  %1 = irdl.any
  %2 = irdl.any
  %int1 = irdl.parametric @builtin::@integer<%1>
  %int2 = irdl.parametric @builtin::@integer<%2>
  irdl_ext.yield %int1, %int2
} of {
  %0 = irdl.any
  %int = irdl.parametric @builtin::@integer<%0>
  irdl_ext.yield %int, %int
}

// CHECK: lhs is not a subset of rhs
