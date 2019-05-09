import _pickle
from time import perf_counter
import numpy as np
from cppimport import import_hook
from sicdock.xbin import xbin_test, Xbin_double, Xbin_float, create_Xbin_nside_double
from sicdock.geom.rotation import angle_of_3x3
from sicdock.geom import bcc
from sicdock import phmap

import homog as hm

"""
data from cpp test (commented out because pytest always prints it)
  bt24_BCC6 4.000/ 30.0 cr 3.537 dt 0.875 da  0.754 x2k: 115.394ns k2x: 108.414ns 46531.591    1521
  bt24_BCC6 2.000/ 20.0 cr 1.857 dt 0.914 da  0.887 x2k: 133.190ns k2x: 116.280ns 14615.713    2855
  bt24_BCC6 1.000/ 15.0 cr 0.907 dt 0.904 da  0.771 x2k: 115.988ns k2x: 104.792ns  4417.715    7917
  bt24_BCC6 0.500/ 10.0 cr 0.456 dt 0.905 da  0.850 x2k: 120.220ns k2x: 129.110ns  1195.048   16693
  bt24_BCC6 0.250/  5.0 cr 0.232 dt 0.897 da  0.870 x2k: 117.767ns k2x: 112.731ns  1115.061  112604
  bt24_BCC6 0.110/  3.3 cr 0.099 dt 0.863 da  0.838 x2k: 133.243ns k2x: 120.677ns   738.212 1048576

"""


def test_xbin_cpp():
    assert xbin_test.TEST_XformHash_XformHash_bt24_BCC6()


def test_create_binner():
    binner = Xbin_double(1.0, 15.0, 256.0)
    binner2 = Xbin_float(1.0, 15.0, 256.0)
    assert binner
    assert binner2


def test_key_of():
    N = 1_000_00
    xb = Xbin_double(0.3, 5.0, 256.0)
    xbf = Xbin_float(0.3, 5.0, 256.0)
    tgen = perf_counter()
    x = hm.rand_xform(N)
    xfloat = hm.rand_xform(N).astype("f4")
    tgen = perf_counter() - tgen

    t = perf_counter()
    k = xb.key_of(x)
    t = perf_counter() - t

    tf = perf_counter()

    k = xbf.key_of(xfloat)
    tf = perf_counter() - tf

    tc = perf_counter()
    c = xb.bincen_of(k)
    tc = perf_counter() - tc

    uniq = len(np.unique(k))

    print(
        f"performance keys: {int(N/t):,} kfloat: {int(N/tf):,} cens: {int(N/tc):,}",
        f"cover {N/uniq} tgen: {int(N/tgen):,}",
    )


def test_key_of_pairs():
    xb = Xbin_double(1, 20)
    N = 10_000
    N1, N2 = 100, 1000
    x1 = hm.rand_xform(N1)
    x2 = hm.rand_xform(N2)
    i1 = np.random.randint(0, N1, N)
    i2 = np.random.randint(0, N2, N)
    p = np.stack([i1, i2], axis=1)
    k1 = xb.key_of_pairs(p, x1, x2)

    px1 = x1[p[:, 0]]
    px2 = x2[p[:, 1]]
    k2 = xb.key_of(np.linalg.inv(px1) @ px2)
    assert np.all(k1 == k2)

    k3 = xb.key_of_selected_pairs(i1, i2, x1, x2)
    assert np.all(k1 == k3)


def test_xbin_covrad(niter=20, nsamp=5000):
    ori_tight, cart_tight = False, False
    for i in range(niter):
        cart_resl = np.random.rand() * 10 + 0.125
        ori_resl = np.random.rand() * 50 + 2.6
        xforms = hm.rand_xform(nsamp)
        xb = Xbin_double(cart_resl, ori_resl, 512)
        ori_resl = xb.ori_resl
        idx = xb.key_of(xforms)
        cen = xb.bincen_of(idx)
        cart_dist = np.linalg.norm(xforms[..., :3, 3] - cen[..., :3, 3], axis=-1)
        ori_dist = angle_of_3x3(cen[:, :3, :3].swapaxes(-1, -2) @ xforms[:, :3, :3])
        # if not np.all(cart_dist < cart_resl):
        # print('ori_resl', ori_resl, 'nside:', xb.ori_nside,
        # 'max(cart_dist):', np.max(cart_dist), cart_resl)
        # if not np.all(cart_dist < cart_resl):
        # print('ori_resl', ori_resl, 'nside:', xb.ori_nside,
        # 'max(ori_dist):', np.max(ori_dist))
        assert np.all(cart_dist < cart_resl)
        assert np.all(ori_dist < 1.05 * ori_resl / 180 * np.pi)
        cart_tight |= np.max(cart_dist) > cart_resl * 0.85
        ori_tight |= np.max(ori_dist) > ori_resl * 0.8 / 180 * np.pi
    assert cart_tight
    assert ori_tight


def test_xbin_covrad_ori():
    nsamp = 10_000
    for ori_nside in range(1, 20):
        cart_resl = 1
        xb = create_Xbin_nside_double(cart_resl, ori_nside, 512)
        ori_resl = xb.ori_resl
        assert ori_nside == xb.ori_nside
        xforms = hm.rand_xform(nsamp)
        idx = xb.key_of(xforms)
        cen = xb.bincen_of(idx)
        cart_dist = np.linalg.norm(xforms[..., :3, 3] - cen[..., :3, 3], axis=-1)
        ori_dist = angle_of_3x3(cen[:, :3, :3].swapaxes(-1, -2) @ xforms[:, :3, :3])
        maxhole = np.max(ori_dist) * 180 / np.pi
        print(f"nside: {ori_nside:2} resl: {ori_resl:7.2f}", f"actual: {maxhole}")
        if maxhole > ori_resl:
            print("NEW", ori_nside, maxhole)
        assert maxhole <= ori_resl * 1.1
        assert ori_resl * 0.8 < maxhole


def test_sskey_of_selected_pairs():
    xb = Xbin_float()
    N = 10_000
    N1, N2 = 100, 1000
    x1 = hm.rand_xform(N1).astype("f4")
    x2 = hm.rand_xform(N2).astype("f4")
    ss1 = np.random.randint(0, 3, N1)
    ss2 = np.random.randint(0, 3, N2)
    i1 = np.random.randint(0, N1, N)
    i2 = np.random.randint(0, N2, N)
    # p = np.stack([i1, i2], axis=1)
    k1 = xb.key_of_selected_pairs(i1, i2, x1, x2)

    kss = xb.sskey_of_selected_pairs(i1, i2, ss1, ss2, x1, x2)
    assert np.all(k1 == np.right_shift(np.left_shift(kss, 4), 4))
    assert np.all(ss1[i1] == np.right_shift(np.left_shift(kss, 0), 62))
    assert np.all(ss2[i2] == np.right_shift(np.left_shift(kss, 2), 62))

    idx = np.stack([i1, i2], axis=1)
    kss2 = xb.sskey_of_selected_pairs(idx, ss1, ss2, x1, x2)
    assert np.all(kss == kss2)


def test_ssmap_of_selected_pairs():
    phm = phmap.PHMap_u8f8()
    xb = Xbin_float()
    N = 10_000
    N1, N2 = 100, 1000
    x1 = hm.rand_xform(N1).astype("f4")
    x2 = hm.rand_xform(N2).astype("f4")
    ss1 = np.random.randint(0, 3, N1)
    ss2 = np.random.randint(0, 3, N2)
    i1 = np.random.randint(0, N1, N)
    i2 = np.random.randint(0, N2, N)
    idx = np.stack([i1, i2], axis=1)

    keys = xb.sskey_of_selected_pairs(idx, ss1, ss2, x1, x2)

    vals = xb.ssmap_of_selected_pairs(phm, idx, ss1, ss2, x1, x2, 0)
    assert np.all(vals == 0)

    vals = xb.ssmap_of_selected_pairs(phm, idx, ss1, ss2, x1, x2, 7)
    assert np.all(vals == 7)

    vals0 = np.random.rand(len(keys))
    phm[keys] = vals0
    vals = xb.ssmap_of_selected_pairs(phm, idx, ss1, ss2, x1, x2, 0)
    assert np.all(vals == phm[keys])


def test_map_of_selected_pairs():
    phm = phmap.PHMap_u8f8()
    xb = Xbin_float()
    N = 10_000
    N1, N2 = 100, 1000
    x1 = hm.rand_xform(N1).astype("f4")
    x2 = hm.rand_xform(N2).astype("f4")
    i1 = np.random.randint(0, N1, N)
    i2 = np.random.randint(0, N2, N)
    idx = np.stack([i1, i2], axis=1)

    vals = xb.map_of_selected_pairs(phm, idx, x1, x2, 0)
    assert np.all(vals == 0)

    vals = xb.map_of_selected_pairs(phm, idx, x1, x2, 7)
    assert np.all(vals == 7)

    keys = xb.key_of_selected_pairs(idx, x1, x2)
    vals0 = np.random.rand(len(keys))
    phm[keys] = vals0
    vals = xb.map_of_selected_pairs(phm, idx, x1, x2, 0)
    assert np.all(vals == phm[keys])


def test_pickle(tmpdir):
    xb = Xbin_double(1, 2, 3)
    with open(tmpdir + "/foo", "wb") as out:
        _pickle.dump(xb, out)

    with open(tmpdir + "/foo", "rb") as inp:
        xb2 = _pickle.load(inp)

    assert xb.cart_resl == xb2.cart_resl
    assert xb.ori_nside == xb2.ori_nside
    assert xb.max_cart == xb2.max_cart
    x = hm.rand_xform(1000, cart_sd=10)
    assert np.all(xb[x] == xb2[x])


if __name__ == "__main__":
    test_xbin_cpp()
    test_create_binner()
    test_key_of()
    test_key_of_pairs()
    test_xbin_covrad()
    test_xbin_covrad_ori()
    test_sskey_of_selected_pairs()
    test_ssmap_of_selected_pairs()
    test_map_of_selected_pairs()

    import tempfile

    test_pickle(tempfile.mkdtemp())
