/*cppimport
<%
cfg['include_dirs'] = ['../..', '../extern']
cfg['compiler_args'] = ['-std=c++17', '-w', '-Ofast']
cfg['dependencies'] = ['../util/dilated_int.hpp', '../util/numeric.hpp',
'xform_hierarchy.hpp']

setup_pybind11(cfg)
%>
*/

#include "sicdock/sampling/xform_hierarchy.hpp"
#include <pybind11/eigen.h>
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <algorithm>
#include <iostream>

namespace py = pybind11;
using namespace py::literals;

namespace sicdock {
namespace sampling {

using namespace util;
using namespace Eigen;

using std::cout;
using std::endl;

template <int N, typename F, typename I>
py::tuple get_trans(CartHier<N, F, I> ch, int resl,
                    Ref<Matrix<I, Dynamic, 1>> idx) {
  std::vector<size_t> xshape{idx.size(), N};
  py::array_t<bool> iout(idx.size());
  py::array_t<F> xout(xshape);
  bool* iptr = (bool*)iout.request().ptr;
  Matrix<F, N, 1>* tptr = (Matrix<F, N, 1>*)xout.request().ptr;
  size_t nout = 0;
  for (size_t i = 0; i < idx.size(); ++i) {
    iptr[i] = ch.get_value(resl, idx[i], tptr[nout]);
    if (iptr[i]) ++nout;
  }
  py::tuple out(2);
  out[0] = iout;
  out[1] = xout[py::slice(0, nout, 1)];
  return out;
}
template <typename F, typename I>
py::tuple get_ori(OriHier<F, I> oh, int resl, Ref<Matrix<I, Dynamic, 1>> idx) {
  std::vector<size_t> orishape{idx.size(), 3, 3};
  py::array_t<bool> iout(idx.size());
  py::array_t<F> oriout(orishape);
  bool* iptr = (bool*)iout.request().ptr;
  M3<F>* oriptr = (M3<F>*)oriout.request().ptr;
  size_t nout = 0;
  for (size_t i = 0; i < idx.size(); ++i) {
    iptr[i] = oh.get_value(resl, idx[i], oriptr[nout]);
    if (iptr[i]) ++nout;
  }
  py::tuple out(2);
  out[0] = iout;
  out[1] = oriout[py::slice(0, nout, 1)];
  return out;
}

template <typename F, typename I>
py::tuple get_xforms(XformHier<F, I> xh, int resl,
                     Ref<Matrix<I, Dynamic, 1>> idx) {
  std::vector<size_t> xshape{idx.size(), 4, 4};
  py::array_t<bool> iout(idx.size());
  py::array_t<F> xout(xshape);
  bool* iptr = (bool*)iout.request().ptr;
  X3<F>* xptr = (X3<F>*)xout.request().ptr;
  size_t nout = 0;
  py::gil_scoped_release release;
  for (size_t i = 0; i < idx.size(); ++i) {
    iptr[i] = xh.get_value(resl, idx[i], xptr[nout]);
    if (iptr[i]) ++nout;
  }
  py::gil_scoped_acquire acquire;
  return py::make_tuple(iout, xout[py::slice(0, nout, 1)]);
}

struct ScoreIndex {
  double score;
  uint64_t index;
};

template <typename F, typename I>
py::tuple expand_top_N_impl(XformHier<F, I> xh, int N, int resl,
                            std::vector<std::pair<double, I>> si) {
  N = std::min<int>(si.size(), N);
  std::vector<size_t> xshape{N * 64, 4, 4};
  py::array_t<F> xout(xshape);
  X3<F>* xptr = (X3<F>*)xout.request().ptr;
  py::array_t<I> iout(N * 64);
  I* iptr = (I*)iout.request().ptr;

  py::gil_scoped_release release;

  std::nth_element(si.begin(), si.begin() + N, si.end(),
                   std::greater<std::pair<double, I>>());
  size_t nout = 0;
  for (size_t i = 0; i < N; ++i) {
    I parent = si[i].second;
    I beg = xh.child_of_begin(parent);
    I end = xh.child_of_end(parent);
    for (I idx = beg; idx < end; ++idx) {
      iptr[nout] = idx;
      bool valid = xh.get_value(resl + 1, iptr[nout], xptr[nout]);
      if (valid) ++nout;
    }
  }
  py::gil_scoped_acquire acquire;
  return py::make_tuple(iout[py::slice(0, nout, 1)],
                        xout[py::slice(0, nout, 1)]);
}

template <typename F, typename I>
py::tuple expand_top_N_pairs(XformHier<F, I> xh, int N, int resl,
                             py::array_t<ScoreIndex> score_idx,
                             double null_val) {
  py::gil_scoped_release release;
  // sketchy
  std::pair<double, I>* siptr = (std::pair<double, I>*)score_idx.request().ptr;
  std::vector<std::pair<double, I>> si;
  for (size_t i = 0; i < score_idx.shape()[0]; ++i)
    if (siptr[i].first != null_val) si.push_back(siptr[i]);
  py::gil_scoped_acquire acquire;
  return expand_top_N_impl(xh, N, resl, si);
}

template <typename F, typename I>
py::tuple expand_top_N_separate(XformHier<F, I> xh, int N, int resl,
                                VectorX<double> score, VectorX<I> index,
                                double null_val) {
  py::gil_scoped_release release;
  std::vector<std::pair<double, I>> si;
  for (size_t i = 0; i < score.size(); ++i)
    if (score[i] != null_val) si.push_back(std::make_pair(score[i], index[i]));
  std::pair<double, I>* siptr = &si[0];
  py::gil_scoped_acquire acquire;
  return expand_top_N_impl(xh, N, resl, si);
}

template <int N, typename F, typename I>
void bind_CartHier(auto m, std::string name) {
  using Fn = Matrix<F, N, 1>;
  using In = Matrix<I, N, 1>;
  py::class_<CartHier<N, F, I>>(m, name.c_str())
      .def(py::init<Fn, Fn, In>(), "lb"_a, "ub"_a, "bs"_a)
      .def("size", &CartHier<N, F, I>::size)
      .def("get_trans", &get_trans<N, F, I>)
      /**/;
}
template <typename F, typename I>
void bind_OriHier(auto m, std::string name) {
  py::class_<OriHier<F, I>>(m, name.c_str())
      .def(py::init<F>(), "ori_resl"_a)
      .def("size", &OriHier<F, I>::size)
      .def_readonly("ori_nside", &OriHier<F, I>::onside_)
      .def("get_ori", &get_ori<F, I>)
      /**/;
}

template <typename F, typename I>
OriHier<F, I> OriHier_nside(int nside) {
  return OriHier<F, I>(nside);
}

template <typename F, typename I>
XformHier<F, I> XformHier_nside(V3<F> lb, V3<F> ub, V3<I> ncart, int nside) {
  return XformHier<F, I>(lb, ub, ncart, nside);
}

template <typename F, typename I>
void bind_XformHier(auto m, std::string name) {
  py::class_<XformHier<F, I>>(m, name.c_str())
      .def(py::init<V3<F>, V3<F>, V3<I>, F>(), "lb"_a, "ub"_a, "bs"_a,
           "ori_resl"_a)
      .def("size", &XformHier<F, I>::size)
      .def_readonly("ori_nside", &XformHier<F, I>::onside_)
      .def_readonly("ori_resl", &XformHier<F, I>::ori_resl_)
      .def_readonly("cart_lb", &XformHier<F, I>::cart_lb_)
      .def_readonly("cart_ub", &XformHier<F, I>::cart_ub_)
      .def_readonly("cart_bs", &XformHier<F, I>::cart_bs_)
      .def_readonly("cart_cell_width", &XformHier<F, I>::cart_cell_width_)
      .def_readonly("cart_ncell", &XformHier<F, I>::cart_ncell_)
      .def_readonly("ori_ncell", &XformHier<F, I>::ori_ncell_)
      .def_readonly("ncell", &XformHier<F, I>::ncell_)
      .def("cell_index_of", py::vectorize(&XformHier<F, I>::cell_index_of))
      .def("hier_index_of", py::vectorize(&XformHier<F, I>::hier_index_of))
      .def("parent_of", py::vectorize(&XformHier<F, I>::parent_of))
      .def("child_of_begin", py::vectorize(&XformHier<F, I>::child_of_begin))
      .def("child_of_end", py::vectorize(&XformHier<F, I>::child_of_end))
      .def("get_xforms", &get_xforms<F, I>)
      .def("expand_top_N", expand_top_N_pairs<F, I>, "nkeep"_a, "resl"_a,
           "score_idx"_a, "null_val"_a = 0)
      .def("expand_top_N", expand_top_N_separate<F, I>, "nkeep"_a, "resl"_a,
           "score"_a, "index"_a, "null_val"_a = 0)
      /**/;
}

template <typename I, int DIM>
Matrix<I, Dynamic, DIM + 1, RowMajor> zorder2coeffs(
    Ref<Matrix<I, Dynamic, 1>> idx, I resl) {
  Matrix<I, Dynamic, DIM + 1, RowMajor> out(idx.size(), DIM + 1);
  for (size_t i = 0; i < idx.size(); ++i) {
    out(i, 0) = idx[i] >> (DIM * resl);
    I hier_index = idx[i] & (((I)1 << (DIM * resl)) - 1);
    for (size_t j = 0; j < DIM; ++j) {
      out(i, j + 1) = util::undilate<DIM>(hier_index >> j);
    }
  }
  return out;
}
template <typename I, int DIM>
Matrix<I, Dynamic, 1> coeffs2zorder(
    Ref<Matrix<I, Dynamic, DIM + 1, RowMajor>> idx, I resl) {
  Matrix<I, Dynamic, 1> out(idx.rows());
  for (size_t i = 0; i < idx.rows(); ++i) {
    I cell_index = idx(i, 0);
    I index = 0;
    for (size_t j = 0; j < DIM; ++j)
      index |= util::dilate<DIM>(idx(i, j + 1)) << j;
    index = index | (cell_index << (DIM * resl));
    out[i] = index;
  }
  return out;
}

PYBIND11_MODULE(xform_hierarchy, m) {
  bind_CartHier<1, double, uint64_t>(m, "CartHier1D");
  bind_CartHier<2, double, uint64_t>(m, "CartHier2D");
  bind_CartHier<3, double, uint64_t>(m, "CartHier3D");
  bind_CartHier<4, double, uint64_t>(m, "CartHier4D");
  bind_CartHier<5, double, uint64_t>(m, "CartHier5D");
  bind_CartHier<6, double, uint64_t>(m, "CartHier6D");

  bind_OriHier<double, uint64_t>(m, "OriHier");
  m.def("create_OriHier_nside", &OriHier_nside<double, uint64_t>, "nside"_a);

  bind_XformHier<double, uint64_t>(m, "XformHier");
  m.def("create_XformHier_nside", &XformHier_nside<double, uint64_t>, "lb"_a,
        "ub"_a, "bs"_a, "nside"_a);
  bind_XformHier<float, uint64_t>(m, "XformHier_f4");
  m.def("create_XformHier_4f_nside", &XformHier_nside<float, uint64_t>, "lb"_a,
        "ub"_a, "bs"_a, "nside"_a);

  m.def("zorder3coeffs", &zorder2coeffs<uint64_t, 3>);
  m.def("coeffs3zorder", &coeffs2zorder<uint64_t, 3>);
  m.def("zorder6coeffs", &zorder2coeffs<uint64_t, 6>);
  m.def("coeffs6zorder", &coeffs2zorder<uint64_t, 6>);

  PYBIND11_NUMPY_DTYPE(ScoreIndex, score, index);
}

}  // namespace sampling
}  // namespace sicdock