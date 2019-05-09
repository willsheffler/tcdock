from time import perf_counter
import itertools as it
import numpy as np
from cppimport import import_hook
from sicdock.sampling import *
from sicdock.bvh.bvh_nd import *
import homog as hm
from scipy.spatial.distance import cdist
from sicdock.geom.rotation import angle_of_3x3
from sicdock.geom import xform_dist2_split
from sicdock.geom.xform_dist import *


def urange(*args):
    return np.arange(*args, dtype="u8")


def urandint(*args):
    return np.random.randint(*args, dtype="u8")


def test_accessors():
    xh = XformHier([0] * 3, [1] * 3, [2] * 3, 30)

    print("ori_nside      ", xh.ori_nside)
    print("ori_resl       ", xh.ori_resl)
    print("cart_lb        ", xh.cart_lb)
    print("cart_ub        ", xh.cart_ub)
    print("cart_bs        ", xh.cart_bs)
    print("cart_cell_width", xh.cart_cell_width)
    print("cart_ncell     ", xh.cart_ncell)
    print("ori_ncell      ", xh.ori_ncell)
    print("ncell          ", xh.ncell)

    assert 6 == xh.ori_nside
    assert 26.018 == xh.ori_resl
    assert np.all(0 == xh.cart_lb)
    assert np.all(1 == xh.cart_ub)
    assert np.all(2 == xh.cart_bs)
    assert np.all(0.5 == xh.cart_cell_width)
    assert 8 == xh.cart_ncell
    assert 5184 == xh.ori_ncell
    assert 41472 == xh.ncell


def test_cart_hier1():
    ch = CartHier1D([0], [1], [1])
    for resl in range(1, 10):
        i, t = ch.get_trans(resl, np.arange(ch.size(resl), dtype="u8"))
        assert len(i) == 2 ** resl == ch.size(resl)
        diff = np.diff(t, axis=0)
        assert np.min(diff) == np.max(diff)
        assert np.allclose(np.min(diff), 1 / 2 ** resl)
    for i in range(10):
        tmp = np.random.randn(2)
        lb, ub = min(tmp), max(tmp)
        bs = urandint(1, 11)
        ch2 = CartHier1D([lb], [ub], [bs])
        for resl in range(4):
            assert ch2.size(resl) == ch.size(resl) * bs


def test_xform_hierarchy_product():
    oh = OriHier(999)
    ch = CartHier3D([0] * 3, [1] * 3, [1] * 3)
    xh = XformHier([0] * 3, [1] * 3, [1] * 3, 999)
    resl = 0
    i, x = xh.get_xforms(resl, urange(xh.size(resl)))
    i, o = oh.get_ori(resl, urange(oh.size(resl)))
    i, t = ch.get_trans(resl, urange(ch.size(resl)))
    assert np.allclose(x[:, :3, :3], o)
    assert np.allclose(x[:, :3, 3], t)

    resl = 1
    i, x = xh.get_xforms(resl, urange(0, xh.size(resl), 8))
    i, o = oh.get_ori(resl, urange(oh.size(resl)))
    i, t = ch.get_trans(resl, urange(ch.size(resl)))
    assert np.allclose(x.reshape(24, -1, 4, 4)[0, :, :3, 3], t)
    assert np.allclose(
        x.reshape(24, -1, 4, 4)[:, ::8, :3, :3], o.reshape(24, -1, 3, 3)[:, ::8]
    )


def test_xform_hierarchy_product_zorder():
    for ang in [999, 30, 20, 10, 5]:
        ho = OriHier(ang)
        hx = XformHier([0] * 3, [1] * 3, [1] * 3, ang)
        assert hx.ori_nside == ho.ori_nside
        Nmax = 1_000
        for resl in range(8):
            n0 = ho.size(resl)
            idx0 = urange(n0) if n0 < Nmax else urandint(0, n0, Nmax)
            io, mo = ho.get_ori(resl, idx0)
            z6 = np.zeros((np.sum(io), 7), dtype="u8")
            z6[:, :4] = zorder3coeffs(idx0[io], resl)
            ix = coeffs6zorder(z6, resl)
            wx, xx = hx.get_xforms(resl, ix)
            assert len(wx) == len(ix)
            assert np.allclose(xx[:, :3, :3], mo)

    for i in range(10):
        tmp = np.random.randn(2, 3)
        lb = np.minimum(*tmp)
        ub = np.maximum(*tmp)
        bs = urandint(1, 10, 3)
        hc = CartHier3D(lb, ub, bs)
        hx = XformHier(lb, ub, bs, 999)
        Nmax = 10_000
        for resl in range(8):
            n0 = ho.size(resl)
            idx0 = urange(n0) if n0 < Nmax else urandint(0, n0, Nmax)
            io, to = hc.get_trans(resl, idx0)
            z6 = np.zeros((np.sum(io), 7), dtype="u8")
            z3 = zorder3coeffs(idx0[io], resl)
            z6[:, 0] = 24 * z3[:, 0]
            z6[:, 4:] = z3[:, 1:]
            ix = coeffs6zorder(z6, resl)
            wx, xx = hx.get_xforms(resl, ix)
            # assert len(wx) == len(ix)
            assert np.allclose(xx[:, :3, 3], to[wx])


def test_xform_hierarchy_ctor():
    xh = XformHier(lb=[0, 0, 0], ub=[2, 2, 2], bs=[2, 2, 2], ori_resl=999.0)


def test_xform_hierarchy_get_xforms():
    for a, b, c in it.product([1, 2], [1, 2], [1, 2]):
        xh = XformHier(lb=[0, 0, 0], ub=[a, b, c], bs=[1, 1, 1], ori_resl=999.0)
        idx, xform = xh.get_xforms(0, np.arange(10, dtype="u8"))
        assert np.allclose(xform[:, :3, 3], [a * 0.5, b * 0.5, c * 0.5])

        idx, xform = xh.get_xforms(1, urange(64))
        assert np.all(idx)
        t = xform[:, :3, 3]
        assert np.all(
            np.unique(t, axis=0)
            == [
                [a * 0.25, b * 0.25, c * 0.25],
                [a * 0.25, b * 0.25, c * 0.75],
                [a * 0.25, b * 0.75, c * 0.25],
                [a * 0.25, b * 0.75, c * 0.75],
                [a * 0.75, b * 0.25, c * 0.25],
                [a * 0.75, b * 0.25, c * 0.75],
                [a * 0.75, b * 0.75, c * 0.25],
                [a * 0.75, b * 0.75, c * 0.75],
            ]
        )
    xh = XformHier(lb=[-1, -1, -1], ub=[0, 0, 0], bs=[1, 1, 1], ori_resl=999.0)
    idx, xform = xh.get_xforms(2, np.arange(64, dtype="u8"))
    t = np.unique(xform[:, :3, 3], axis=0)
    assert np.all(
        t
        == [
            [-0.875, -0.875, -0.875],
            [-0.875, -0.875, -0.625],
            [-0.875, -0.625, -0.875],
            [-0.875, -0.625, -0.625],
            [-0.625, -0.875, -0.875],
            [-0.625, -0.875, -0.625],
            [-0.625, -0.625, -0.875],
            [-0.625, -0.625, -0.625],
        ]
    )


def test_xform_hierarchy_get_xforms_bs():
    xh = XformHier(lb=[0, 0, 0], ub=[4, 4, 4], bs=[2, 2, 2], ori_resl=999.0)
    idx, xform = xh.get_xforms(0, np.arange(xh.size(0), dtype="u8"))
    t = xform[:, :3, 3]
    u = np.unique(t, axis=0)
    assert np.all(
        u
        == [
            [1.0, 1.0, 1.0],
            [1.0, 1.0, 3.0],
            [1.0, 3.0, 1.0],
            [1.0, 3.0, 3.0],
            [3.0, 1.0, 1.0],
            [3.0, 1.0, 3.0],
            [3.0, 3.0, 1.0],
            [3.0, 3.0, 3.0],
        ]
    )
    for a, b, c in it.product([1, 2], [1, 2], [1, 2]):
        xh = XformHier(lb=[0, 0, 0], ub=[a, b, c], bs=[a, b, c], ori_resl=999.0)
        idx, xform = xh.get_xforms(0, np.arange(xh.size(0), dtype="u8"))
        t = xform[:, :3, 3]
        u = np.unique(t, axis=0)
        print(u)
        print(np.sum(u[:, 0] == 0.5), a, b, c)
        # assert np.sum(u[:, 0] == 0.5) == b * c


def test_xform_hierarchy_expand_top_N():
    xh = XformHier(lb=[0, 0, 0], ub=[2, 2, 2], bs=[2, 2, 2], ori_resl=30.0)
    scoreindex = np.empty(10, dtype=[("score", "f8"), ("index", "u8")])
    scoreindex["index"] = np.arange(10)
    scoreindex["score"] = np.arange(10)
    idx1, xform1 = xh.expand_top_N(3, 0, scoreindex, null_val=-123456789)

    score = np.arange(10).astype("f8")
    index = np.arange(10).astype("u8")
    idx2, xform2 = xh.expand_top_N(3, 0, score, index, null_val=-123456789)

    assert np.all(idx1 == idx2)
    assert np.allclose(xform1, xform2)

    idx1.sort()
    assert np.all(idx1 == np.arange(7 * 64, 10 * 64))
    idx2, xform2 = xh.expand_top_N(3, 0, -score, index, null_val=-123456789)
    idx2.sort()
    assert np.all(idx2 == np.arange(3 * 64))

    idx0 = np.array([10829082304220, 2934384902], dtype="u8")
    mask, x0 = xh.get_xforms(5, idx0)
    print(x0)
    scores = np.array([100, 0])
    idx1, x1 = xh.expand_top_N(1, 5, scores, idx0, null_val=-123456789)
    da, _ = xform_dist2_split(x0[0], x1, 1)
    db, _ = xform_dist2_split(x0[1], x1, 1)
    assert np.max(da) < np.min(db)


def test_xform_hierarchy_expand_top_N_nullval():
    xh = XformHier(lb=[0, 0, 0], ub=[2, 2, 2], bs=[2, 2, 2], ori_resl=30.0)
    scoreindex = np.empty(10, dtype=[("score", "f8"), ("index", "u8")])
    scoreindex["index"] = np.arange(10)
    scoreindex["score"] = np.zeros(10)
    idx1, xform1 = xh.expand_top_N(3, 0, scoreindex)
    assert len(idx1) == 0
    scoreindex["score"][7] = 1
    idx1, xform1 = xh.expand_top_N(3, 0, scoreindex)
    assert len(idx1) == 64
    assert np.all(np.right_shift(idx1, 6) == 7)


def test_zorder():
    idx = urange(1e5)
    for resl in range(5):
        coef = zorder6coeffs(idx, resl)
        assert np.all(coeffs6zorder(coef, resl) == idx)

    for resl in range(10):
        n = min(1_000_000, 100 * 2 ** resl)
        coef = urandint(0, 2 ** resl, (n, 7))
        coef[:, 0] = urandint(0, 1024, n)
        idx = coeffs6zorder(coef, resl)
        coef2 = zorder6coeffs(idx, resl)
        # print(idx[:3])
        # print(coef[:3])
        assert np.all(coef2 == coef)


def test_ori_hier_all2():
    minrange = np.array([(89.9, 90.1), (41.0, 41.1), (20, 23)])
    corner = [(0, 0), (0, 0), (0.125, 0.2)]
    ohier = OriHier(9e9)
    for resl in range(2):
        w, o = ohier.get_ori(resl, urange(ohier.size(resl)))
        assert np.allclose(np.linalg.det(o), 1)
        rel = o.swapaxes(1, 2)[:, None] @ o
        amat = angle_of_3x3(rel)
        assert np.allclose(amat.diagonal(), 0)
        np.fill_diagonal(amat, 9e9)
        mn = amat.min(axis=0)
        cfrac, cang = corner[resl]
        # print(np.unique(mn), cang, cfrac)
        # print("foo", np.sum(mn < cang) / len(mn))
        assert np.sum(mn < cang) / len(mn) == cfrac
        mn = mn[mn > cang]
        # print(resl, len(mn), np.unique(mn) * 180 / np.pi)
        lb, ub = minrange[resl] / 180 * np.pi

        assert np.all(lb < mn)
        assert np.all(mn < ub)


def test_ori_hier_1cell():
    minrange = np.array([(0, 0), (44.9, 45), (20.9, 22.5)])
    ohier = OriHier(9e9)
    for resl in range(1, 3):
        w, o = ohier.get_ori(resl, urange(ohier.size(resl) / 24))
        assert np.allclose(np.linalg.det(o), 1)
        rel = o.swapaxes(1, 2)[:, None] @ o
        amat = angle_of_3x3(rel)
        assert np.allclose(amat.diagonal(), 0)
        np.fill_diagonal(amat, 9e9)
        mn = amat.min(axis=0)
        # print(resl, len(mn), np.unique(mn) * 180 / np.pi)
        lb, ub = minrange[resl] / 180 * np.pi
        print(
            "foo",
            resl,
            np.min(mn) * 180 / np.pi,
            np.max(mn) * 180 / np.pi,
            minrange[resl],
        )
        assert np.all(lb < mn)
        assert np.all(mn < ub)


def analyze_ori_hier(nside, resl, nsamp):
    ohier = create_OriHier_nside(nside)
    w, hori = ohier.get_ori(resl, urange(ohier.size(resl)))
    assert np.allclose(np.linalg.det(hori), 1)
    hquat = hm.quat.rot_to_quat(hori)
    hquat += np.random.randn(*hquat.shape) * 0.000000000001
    bvh_ohier = create_bvh_quat(hquat)
    assert np.allclose(bvh_ohier.com(), 0)
    samp = hm.rand_xform(nsamp)[:, :3, :3]
    quat = hm.quat.rot_to_quat(samp)

    t = perf_counter()
    mindis, wmin = bvh_mindist4d(bvh_ohier, quat.copy())
    tbvh = perf_counter() - t
    t = perf_counter()
    mindis2, wmin2 = bvh_mindist4d_naive(bvh_ohier, quat.copy())
    tnai = perf_counter() - t
    assert np.allclose(mindis, mindis2)

    imax = np.argmax(mindis)
    hclose = hquat[wmin[imax]]
    sclose = quat[imax]
    d = np.linalg.norm(hclose - sclose)
    if d > mindis[imax] * 1.1:
        hclose = -hclose
    d = np.linalg.norm(hclose - sclose)
    assert np.allclose(d, mindis[imax])
    a = hm.quat.quat_to_rot(sclose)
    b = hm.quat.quat_to_rot(hclose)
    angle = angle_of_3x3(a.T @ b) * 180 / np.pi

    maxmindis = np.max(mindis)
    sphcellvol = 4 / 3 * np.pi * maxmindis ** 3
    totgridvol = len(hquat) * sphcellvol
    totquatvol = np.pi ** 2
    overcover = totgridvol / totquatvol

    return len(hquat), maxmindis, angle, overcover, tbvh


def test_ori_hier_angresl():
    assert OriHier(93).ori_nside == 1
    assert OriHier(92).ori_nside == 2
    assert OriHier(66).ori_nside == 3
    assert OriHier(47).ori_nside == 4
    assert OriHier(37).ori_nside == 5
    assert OriHier(30).ori_nside == 6
    assert OriHier(26).ori_nside == 7
    assert OriHier(22).ori_nside == 8
    assert OriHier(19).ori_nside == 9
    assert OriHier(17).ori_nside == 10
    assert OriHier(15).ori_nside == 11
    assert OriHier(14).ori_nside == 12
    assert OriHier(13).ori_nside == 13
    assert OriHier(12).ori_nside == 14
    assert OriHier(11).ori_nside == 15
    assert OriHier(10).ori_nside == 16


def test_ori_hier_rand_nside():
    N = 1_000
    covang = [
        None,
        92.609,  # 1
        66.065,  # 2
        47.017,  # 3
        37.702,  # 4
        30.643,  # 5
        26.018,  # 6
        22.466,  # 7
        19.543,  # 8
        17.607,  # 9
        15.928,  # 10
        14.282,  # 11
        13.149,  # 12
        12.238,  # 13
        11.405,  # 14
        10.589,  # 15
    ]
    for nside in range(1, 8):
        nhier, maxmindis, angle, overcover, tbvh = analyze_ori_hier(nside, 0, N)
        assert angle < covang[nside] * 1.01
        print(
            f"{nside:2} {nhier:9,} bvh: {int(N / tbvh):9,} ",
            f"oc: {overcover:5.2f} ang: {angle:7.3f} dis: {maxmindis:7.4f}",
        )


def test_ori_hier_rand():
    # import matplotlib.pyplot as plt
    # plt.scatter(qdist, adist)
    # plt.show()
    maxang = np.array([92.521, 66.050, 37.285, 19.475, 9.891, 4.879, 2.517]) * 1.1
    N = 10_000
    for resl in range(4):
        nhier, maxmindis, angle, overcover, tbvh = analyze_ori_hier(1, resl, N)
        assert angle < maxang[resl]
        print(
            f"{resl} {nhier:7,} bvhrate: {int(N / tbvh):9,} ",
            f"oc: {overcover:5.2f} ang: {angle:7.3f} dis: {maxmindis:7.4f}",
        )


def slow_test_ori_hier_rand_nside4():
    # import matplotlib.pyplot as plt
    # plt.scatter(qdist, adist)
    # plt.show()
    maxang = np.array([20, 10, 5, 2.5, 1.25])
    N = 10_000
    for resl in range(4):
        nhier, maxmindis, angle, overcover, tbvh = analyze_ori_hier(4, resl, N)
        print(
            f"{resl} {nhier:7,} bvhrate: {int(N / tbvh):9,} ",
            f"oc: {overcover:5.2f} ang: {angle:7.3f} dis: {maxmindis:7.4f}",
        )
        assert maxang[resl] * 0.8 < angle < maxang[resl]


def test_avg_dist():
    from sicdock.bvh import bvh

    N = 1000
    ch = CartHier3D([-1, -1, -1], [2, 2, 2], [1, 1, 1])
    for resl in range(1, 4):
        i, grid = ch.get_trans(resl, urange(ch.size(3)))
        gridbvh = bvh.bvh_create(grid)
        dis = np.empty(N)
        samp = np.random.rand(N, 3)
        for j in range(N):
            dis[j] = bvh.bvh_min_dist_one(gridbvh, samp[j])[0]
        mx = 3.0 * np.max(dis) * 180 / np.pi
        me = 3.0 * np.mean(dis) * 180 / np.pi
        print(f"{resl} {len(gridbvh):6,} {mx} {me} {mx / me}")
        assert mx / me < 3


def crappy_xform_hierarchy_resl_sanity_check():
    base_sample_resl = np.sqrt(2) / 2
    base_cart_resl = 0.5
    base_ori_resl = 5.0
    xbin_max_cart = 128.0
    hierarchy_depth = 5
    sampling_lever = 25
    xhier_cart_fudge_factor = 1.5
    xhier_ori_fudge_factor = 2.5

    # xh.size 0 0.098304 M
    # max min xform dis 15.758281
    # max min cart dis  11.499426
    # max min ori dis   12.107783
    # mean xform dis 9.940624
    # mean cart dis  6.931336
    # mean ori dis   7.125488

    hresl, (cart_resl, ori_resl), n100 = xform_hier_guess_sampling_covrads(**vars())
    print(hresl[0], cart_resl, ori_resl)
    cart_side = cart_resl * 2.0 / np.sqrt(3)
    Ncell = 2
    ub = np.ones(3) * Ncell * cart_side
    lb = -ub
    ns = [2 * Ncell] * 3
    assert np.allclose((ub[0] - lb[0]) / cart_side, ns[0])

    xh = sic.sampling.XformHier_f4(lb, ub, ns, ori_resl)

    print("xh.size 0", xh.size(0) / 1e6, "M")
    x0 = xh.get_xforms(0, np.arange(xh.size(0), dtype="u8"))[1]
    N = 100
    xs = hm.rand_xform(N)
    xs[:, :3, 3] = 2 * (Ncell - 1) * cart_side * (np.random.rand(N, 3) - 0.5)

    d2cart, d2ori = xform_dist2_split(x0, xs, sampling_lever)
    d2ori = d2ori / sampling_lever * 180 / np.pi

    mind2cart = np.min(d2cart, axis=0)
    mind2ori = np.min(d2ori, axis=0)
    mind2 = np.min(d2cart + d2ori, axis=0)
    print("max min xform dis", np.sqrt(np.max(mind2)))
    print("max min cart dis ", np.sqrt(np.max(mind2cart)))
    print("max min ori dis  ", np.sqrt(np.max(mind2ori)))
    print("mean xform dis", np.sqrt(np.mean(mind2)))
    print("mean cart dis ", np.sqrt(np.mean(mind2cart)))
    print("mean ori dis  ", np.sqrt(np.mean(mind2ori)))


def test_xform_hierarchy_plug_bug():
    xh = XformHier_f4([-18, -18, -6], [18, 18, 6.0], [3, 3, 1], 30.643)
    x0 = xh.get_xforms(0, np.array([26561], dtype="u8"))[1]
    x1 = xh.get_xforms(1, np.array([1699904], dtype="u8"))[1]
    print(x0)
    print(x1)


#     [[ 1.         -0.          0.         12.        ]
#  [ 0.         -0.32251728  0.9465637  12.        ]
#  [-0.         -0.9465637  -0.32251728  0.        ]
#  [ 0.          0.          0.          1.        ]]
# [[  0.89194673   0.3375754    0.30078876 -16.5       ]
#  [ -0.44858906   0.74392855   0.4953163  -16.5       ]
#  [ -0.05655876  -0.5767263    0.8149772   -4.5       ]
#  [  0.           0.           0.           1.        ]]

if __name__ == "__main__":
    # test_zorder()
    # test_cart_hier1()
    # test_xform_hierarchy_product()
    # test_xform_hierarchy_product_zorder()
    # test_xform_hierarchy_ctor()
    # test_xform_hierarchy_get_xforms()
    # test_xform_hierarchy_get_xforms_bs()
    # test_xform_hierarchy_expand_top_N()
    # test_xform_hierarchy_expand_top_N_nullval()
    # test_ori_hier_all2()
    # test_ori_hier_1cell()
    # test_ori_hier_rand()
    # slow_test_ori_hier_rand_nside4()
    # test_ori_hier_rand_nside()
    # test_avg_dist()
    # test_ori_hier_angresl()
    # crappy_xform_hierarchy_resl_sanity_check()
    # test_xform_hierarchy_product_zorder()
    # test_ori_hier_angresl()
    # test_accessors()
    test_xform_hierarchy_plug_bug()
