__author__ = 'omniscope'

import numpy as np
import scipy.interpolate as si
import fitsio as fit
import healpy.visufunc as hpv
import healpy.pixelfunc as hpf
import healpy.sphtfunc as hps
import matplotlib.pyplot as plt
from matplotlib import cm
import sys

def pol_frac(I, Q, U, V=0):
    return (Q**2 + U**2 + V**2)**.5 / I

def pol_angle(I, Q, U, V=0):
    return np.arctan2(Q, U) / 2

def plot_dataset(data_set):

    if len(data_set) <= 5:
        nrow = len(data_set)
        ncol = 3

    elif len(data_set) <= 10:
        nrow = (len(data_set) + 1) / 2
        ncol = 6

    else:
        nrow = (len(data_set) + 2) / 3
        ncol = 9

    iplot = 0
    for f in sorted(data_set.keys()):
        d = data_set[f]
        if d.ndim == 2:
            iplot += 1
            plot_d = np.log10(d[0])
            plot_mask = ~(np.isnan(plot_d) | np.isinf(plot_d))
            hpv.mollview(plot_d, sub=(nrow, ncol, iplot), nest=True, min=np.percentile(plot_d[plot_mask], 5), max=np.percentile(plot_d[plot_mask], 95), title="%.3fGHz I, n%i"%(f, (len(plot_d)/12)**.5))

            iplot += 1
            plot_d = pol_frac(d[0], d[1], d[2])
            plot_mask = ~(np.isnan(plot_d) | np.isinf(plot_d))
            hpv.mollview(plot_d, sub=(nrow, ncol, iplot), nest=True, min=np.percentile(plot_d[plot_mask], 5), max=np.percentile(plot_d[plot_mask], 95), title="%.3fGHz Q, n%i"%(f, (len(plot_d)/12)**.5))

            iplot += 1
            hpv.mollview(pol_angle(d[0], d[1], d[2]), sub=(nrow, ncol, iplot), nest=True, cmap=cm.hsv, title="%.3fGHz U, n%i"%(f, (len(plot_d)/12)**.5))
        elif d.ndim== 1:
            iplot += 1
            plot_d = np.log10(d)
            plot_mask = ~(np.isnan(plot_d) | np.isinf(plot_d))
            hpv.mollview(plot_d, sub=(nrow, ncol, iplot), nest=True, min=np.percentile(plot_d[plot_mask], 5), max=np.percentile(plot_d[plot_mask], 95), title="%.3fGHz I, n%i"%(f, (len(plot_d)/12)**.5))
            iplot += 2
        else:
            raise ValueError("Shape problem.")
    plt.show()

def equirectangular2heapix(data, nside, data_x=None, data_y=None, nest=True):
    if data_x is None:
        delx = 2*np.pi / (data.shape[1] - 1)
        data_x = np.arange(0, 2*np.pi+delx/100., delx)
    if data_y is None:
        dely = np.pi / (data.shape[0] - 1)
        data_y = np.arange(np.pi, -dely/100., -dely)
    if data.shape != (len(data_y), len(data_x)):
        raise ValueError("Input shape mismatch between %s and (%i, %i)"%(data.shape, len(data_y), len(data_x)))
    inter_f = si.interp2d(data_x, data_y, data)

    result = np.empty(12*nside**2, dtype=data.dtype)

    heal_thetas, heal_phis = hpf.pix2ang(nside, range(12*nside**2), nest=nest)
    unique_heal_thetas = np.unique(heal_thetas)

    for heal_theta in unique_heal_thetas:
        theta_mask = heal_thetas == heal_theta

        #doing some complicated juggling bc interp function automatically sort the list input and output according to that implicitly re-arranged inuput list
        qaz_phis = heal_phis[theta_mask] % (np.pi*2)
        qaz = np.zeros_like(heal_phis[theta_mask])
        qaz[np.argsort(qaz_phis)] = inter_f(np.sort(qaz_phis), heal_theta).flatten()

        result[theta_mask] = qaz
    #     if np.abs(heal_theta - np.pi/2.) < 5*np.pi/180.:
    #         print np.isnan(qaz).all()
    # print np.isnan(data).all()
    # print data_x
    # print data_y
    return result

def ud_grade(m, nside, nest=True):
    if nside != hpf.npix2nside(len(m)):
        if nest:
            order_in = 'NESTED'
        else:
            order_in = 'RING'

        bad_mask = (np.isnan(m) | np.isinf(m) | (m == 0))
        bad_mask = hpf.ud_grade(bad_mask.astype('float'), nside, order_in=order_in, pess=True) > 0

        result = hpf.ud_grade(m, nside, order_in=order_in, pess=True)
        result[bad_mask] = np.nan
        return result
    return m

def smoothing(m, fwhm, nest=True):
    if fwhm <= 0:
        return m
    nside = hpf.npix2nside(len(m))
    if nest:
        return hps.smoothing(m[hpf.ring2nest(nside, np.arange(hpf.nside2npix(nside)))], fwhm=fwhm)[hpf.nest2ring(nside, np.arange(hpf.nside2npix(nside)))]
    else:
        return hps.smoothing(m, fwhm=fwhm)

def preprocess(m, final_nside, nest=True, fwhm=0, edge_width=0, smooth_thresh=1e-2):
    #fwhm and edge_witdh are both in radians
    #smooth_thresh decides what relative error is accepted when smoothing smears 0s into edge data points

    nside = hpf.npix2nside(len(m))
    result = np.copy(m)

    #create initial mask
    bad_mask = np.isnan(result) | (result == 0) | np.isinf(result)

    #expand mask to push out edge by edge_width
    smooth_bad_mask = smoothing(bad_mask, fwhm=edge_width, nest=nest) > .25
    bad_mask = bad_mask | smooth_bad_mask

    #smooth
    result[bad_mask] = 0
    result = smoothing(result, fwhm=fwhm, nest=nest)
    smooth_bad_mask = smoothing(bad_mask, fwhm=fwhm, nest=nest) > smooth_thresh
    bad_mask = bad_mask | smooth_bad_mask
    result[bad_mask] = np.nan

    #regrid
    result = ud_grade(result, final_nside, nest=nest)
    return result

def merge_map(maps, nside=None, nest=True, verbose=False, renormalize=False):
    if nside is None:
        nside = 4096
        for m in maps:
            nside = min(nside, hpf.npix2nside(len(m)))



    filled_mask = np.zeros(hpf.nside2npix(nside), dtype=bool)
    result = np.zeros(hpf.nside2npix(nside), dtype=maps[0].dtype)

    for m in maps:
        m = ud_grade(m, nside, nest=nest)
        #valid in m
        valid_mask = ~(np.isnan(m)|np.isinf(m))

        #pixels to be taken from m, earlier m takes priority and will not be over-written
        fill_mask = valid_mask&(~filled_mask)
        if verbose:
            print "%.1f%% valid"%(100. * np.sum(valid_mask) / len(valid_mask)),
            print "%.1f%% to be filled"%(100. * np.sum(fill_mask) / len(fill_mask))

        if renormalize:
            overlap_mask = valid_mask&filled_mask
            if overlap_mask.any():
                factor = m[overlap_mask].dot(result[overlap_mask]) / m[overlap_mask].dot(m[overlap_mask])
                if verbose:
                    print "renormalizing by ", factor
                m *= factor

        #fill pixel and mask
        result[fill_mask] = m[fill_mask]
        filled_mask[fill_mask] = True
    result[~filled_mask] = np.nan

    return result


plot_individual = False


###########################
###########################
###OVER ALL PARAMETERS
###########################
###########################
mother_nside = 512
smoothing_fwhm = 3. * np.pi / 180.
edge_width = 1. * np.pi / 180.
remove_cmb = True


###########################
###parkes 85 and 150mhz
#########################

parkes_85 = fit.read("/home/omniscope/data/polarized foregrounds/parkes_85mhz.bin")[0]
parkes_85[:, :-1] = np.roll(parkes_85[:, :-1], 180, axis=1)[:, ::-1]
parkes_85[:, -1] = parkes_85[:, 0]
parkes_85[parkes_85 > 1.4e4] = -1e-9
parkes_85[parkes_85 <= 0] = -1e-9
parkes_85 = equirectangular2heapix(parkes_85, mother_nside)
parkes_85[parkes_85 <= 0] = np.nan

parkes_150 = fit.read("/home/omniscope/data/polarized foregrounds/parkes_150mhz.bin")[0]
parkes_150[:, :-1] = np.roll(parkes_150[:, :-1], 180, axis=1)[:, ::-1]
parkes_150[:, -1] = parkes_150[:, 0]
parkes_150[parkes_150 > 7.e3] = -1e-9
parkes_150[parkes_150 <= 0] = -1e-9
parkes_150 = equirectangular2heapix(parkes_150, mother_nside)
parkes_150[parkes_150 <= 0] = np.nan

parkes = {.085: parkes_85,
          .15: parkes_150,
          }
if plot_individual:
    plot_dataset(parkes)
###########################
###1.4G: DRAO+villa Elisa+CHIPASS+LAB
###########################

drao_elisa_iqu_syn = {}

chipass = fit.read("/home/omniscope/data/polarized foregrounds/lambda_chipass_healpix_r10.fits")['TEMPERATURE']
chipass[chipass <= 0] = np.nan
# lab = fit.read("/home/omniscope/data/polarized foregrounds/LAB_fullvel.fits")['TEMPERATURE'].flatten()
# lab = lab[hpf.nest2ring(int((len(lab)/12)**.5), range(len(lab)))]

stockert = fit.read("/home/omniscope/data/polarized foregrounds/stocker_villa_elisa.bin")[0]
stockert[:, :-1] = np.roll(stockert[:, :-1], 720, axis=1)[:, ::-1]
stockert[:, -1] = stockert[:, 0]
stockert = equirectangular2heapix(stockert, mother_nside)

elisa = np.array([equirectangular2heapix(fit.read("/home/omniscope/data/polarized foregrounds/Elisa_POL_%s.bin"%key)[0], mother_nside) for key in ['I', 'Q', 'U']])
elisa[elisa > 1000] = np.nan

drao = np.array([equirectangular2heapix(fit.read("/home/omniscope/data/polarized foregrounds/DRAO_POL_%s.bin"%key)[0], mother_nside) for key in ['I', 'Q', 'U']])
drao[drao > 1000] = np.nan

reich_q = equirectangular2heapix(fit.read("/home/omniscope/data/polarized foregrounds/allsky.q.lb.fits")[0], mother_nside)
reich_u = equirectangular2heapix(fit.read("/home/omniscope/data/polarized foregrounds/allsky.u.lb.fits")[0], mother_nside)

drao_elisa_iqu_syn[1.3945] = chipass
drao_elisa_iqu_syn[1.435] = elisa
drao_elisa_iqu_syn[1.41] = drao
drao_elisa_iqu_syn[1.42] = stockert
# drao_elisa_iqu_syn[1.4276] = lab

if plot_individual:
    plot_dataset(drao_elisa_iqu_syn)

all_1400 = {1.41: np.array([
    stockert, #merge_map([chipass, stockert], verbose=True, renormalize=True),
    reich_q, #merge_map([drao[1], elisa[1]]),
    reich_u, #merge_map([drao[2], elisa[2]]),
]) / 1.e3}

if plot_individual:
    plot_dataset(all_1400)

###########################
###CMB######
###############
T_CMB = 2.725 * (1 - remove_cmb) #if remove cmb, dont add cmb temp into wmap/planck
dipole_correction = {'I_Stokes': T_CMB, 'Q_Stokes': 0, 'U_Stokes': 0, 'I_STOKES': T_CMB, 'Q_STOKES': 0, 'U_STOKES': 0, 'TEMPERATURE': T_CMB, 'Q_POLARISATION': 0, 'U_POLARISATION': 0}

####planck
planck_iqu = {}
planck_iqu[30.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/LFI_SkyMap_030_1024_R2.01_full.fits")[key] + dipole_correction[key] for key in ['I_Stokes', 'Q_Stokes', 'U_Stokes']])
planck_iqu[44.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/LFI_SkyMap_044_1024_R2.01_full.fits")[key] + dipole_correction[key] for key in ['I_Stokes', 'Q_Stokes', 'U_Stokes']])
planck_iqu[70.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/LFI_SkyMap_070_1024_R2.01_full.fits")[key] + dipole_correction[key] for key in ['I_Stokes', 'Q_Stokes', 'U_Stokes']])
planck_iqu[100.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/HFI_SkyMap_100_2048_R2.02_full.fits")[key] + dipole_correction[key] for key in ['I_STOKES', 'Q_STOKES', 'U_STOKES']])
planck_iqu[143.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/HFI_SkyMap_143_2048_R2.02_full.fits")[key] + dipole_correction[key] for key in ['I_STOKES', 'Q_STOKES', 'U_STOKES']])
planck_iqu[217.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/HFI_SkyMap_217_2048_R2.02_full.fits")[key] + dipole_correction[key] for key in ['I_STOKES', 'Q_STOKES', 'U_STOKES']])
planck_iqu[353.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/HFI_SkyMap_353_2048_R2.02_full.fits")[key] + dipole_correction[key] for key in ['I_STOKES', 'Q_STOKES', 'U_STOKES']])
planck_iqu[545.0] = fit.read("/home/omniscope/data/polarized foregrounds/HFI_SkyMap_545_2048_R2.02_full.fits")['I_STOKES']
planck_iqu[857.0] = fit.read("/home/omniscope/data/polarized foregrounds/HFI_SkyMap_857_2048_R2.02_full.fits")['I_STOKES']
if plot_individual:
    plot_dataset(planck_iqu)

#####wmap
wmap_iqu = {}
wmap_iqu[22.8] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/wmap_band_iqumap_r9_9yr_K_v5.fits")[key] + dipole_correction[key] for key in ['TEMPERATURE', 'Q_POLARISATION', 'U_POLARISATION']])
wmap_iqu[30.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/wmap_band_iqumap_r9_9yr_Ka_v5.fits")[key] + dipole_correction[key] for key in ['TEMPERATURE', 'Q_POLARISATION', 'U_POLARISATION']])
wmap_iqu[40.7] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/wmap_band_iqumap_r9_9yr_Q_v5.fits")[key] + dipole_correction[key] for key in ['TEMPERATURE', 'Q_POLARISATION', 'U_POLARISATION']])
wmap_iqu[60.8] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/wmap_band_iqumap_r9_9yr_V_v5.fits")[key] + dipole_correction[key] for key in ['TEMPERATURE', 'Q_POLARISATION', 'U_POLARISATION']])
wmap_iqu[93.5] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/wmap_band_iqumap_r9_9yr_W_v5.fits")[key] + dipole_correction[key] for key in ['TEMPERATURE', 'Q_POLARISATION', 'U_POLARISATION']])
if plot_individual:
    plot_dataset(wmap_iqu)

# ###WMAP POL 22G
# cmb_iqu_syn = {}
# cmb_iqu_syn[22.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/wmap_mcmc_base_k_synch_%s_9yr_v5.fits"%key)['BESTFIT'] for key in ['temp', 'stk_q', 'stk_u']])
#
# ###PLANCK POL 30G
# cmb_iqu_syn[30.0] = np.array([fit.read("/home/omniscope/data/polarized foregrounds/COM_CompMap_Synchrotron-commander_0256_R2.00.fits")['I_ML']]
#                                 + [fit.read("/home/omniscope/data/polarized foregrounds/COM_CompMap_SynchrotronPol-commander_0256_R2.00.fits")[key] for key in ['Q_ML_FULL', 'U_ML_FULL']])
# plot_dataset(cmb_iqu_syn)

#########################
###mother file#########################
#########################
# motherfile = {}
# motherfile_data = np.fromfile("/home/omniscope/data/polarized foregrounds/motherfile_3145728_16_float64.bin", dtype='float64').reshape((3145728, 16))[hpf.nest2ring(512, range(3145728))]
# for i in range(motherfile_data.shape[1]):
#     motherfile[i] = motherfile_data[:, i]
# plot_dataset(motherfile)

motherfile = {}
motherfile_data = np.fromfile("/home/omniscope/data/polarized foregrounds/motherfile_3145728_16_float64.bin", dtype='float64').reshape((3145728, 16))[hpf.nest2ring(512, range(3145728))]
motherfile[.045] = motherfile_data[:, -9]
motherfile[2.33] = motherfile_data[:, -1]
# motherfile[.0345] = motherfile_data[:, -11]
# motherfile[.408] = motherfile_data[:, -3]
motherfile[.022] = motherfile_data[:, -13]
motherfile[.82] = motherfile_data[:, -2]
motherfile[.010] = motherfile_data[:, -16]
if plot_individual:
    plot_dataset(motherfile)

###########################
###iras high freq
#########################
iras = {}
for freq in [3, 5]:#, 12]:
    d = np.zeros((5401, 10801)) - 1e9
    d[(5401-3)/2:(5401-3)/2+301] = fit.read("/home/omniscope/data/polarized foregrounds/iras_%ithz.bin"%freq)[0]
    d[:, :-1] = np.roll(d[:, :-1], 5400, axis=1)[:, ::-1]
    d[:, -1] = d[:, 0]
    d[d > np.nanmax(d) * .8] = -1e9
    d[d <= 0] = -1e9
    d = equirectangular2heapix(d, mother_nside)
    d[d <= 0] = np.nan
    iras[freq * 1.e3] = d


if plot_individual:
    plot_dataset(iras)

#########################
###Haslam#########################
#########################
haslam = fit.read("/home/omniscope/data/polarized foregrounds/haslam408_dsds_Remazeilles2014.fits")['TEMPERATURE'].flatten()
haslam = {.408: haslam[hpf.nest2ring(int((len(haslam)/12)**.5), range(len(haslam)))]}
if plot_individual:
    plot_dataset(haslam)


####PNM+87GB
#plt.imshow(np.log10(fit.read("/home/omniscope/data/polarized foregrounds/PMN+87GB.fits")[0,0]));plt.show()


new_mother = {}

mother_npix = hpf.nside2npix(mother_nside)
for dict in [
    motherfile,
    all_1400,
    haslam,
    wmap_iqu,
    planck_iqu,
    #parkes,
    #iras,
    ]:
    for f, data in dict.iteritems():
        print f
        sys.stdout.flush()

        if data.ndim == 2:
            # new_mother[f] = np.array([ud_grade(smoothing(d, smoothing_fwhm), mother_nside, nside_edge=nside_edge) for d in data])
            new_mother[f] = np.array([preprocess(d, mother_nside, fwhm=smoothing_fwhm, edge_width=edge_width) for d in data])
        else:
            # new_mother[f] = np.array(ud_grade(smoothing(data, smoothing_fwhm), mother_nside, nside_edge=nside_edge))
            new_mother[f] = preprocess(data, mother_nside, fwhm=smoothing_fwhm, edge_width=edge_width)
plot_dataset(new_mother)


##############################################
##############################################
##############################################
##############################################
##############################################
##############################################
##############################################
##############################################
##############################################
##############################################

freqs = np.array(sorted(new_mother.keys()))
idata = np.zeros((len(freqs), mother_npix))
qdata = np.zeros((len(freqs), mother_npix))
udata = np.zeros((len(freqs), mother_npix))
for f, freq in enumerate(freqs):
    data = new_mother[freq]
    if data.ndim == 2:
        idata[f] = data[0]
        qdata[f] = data[1]
        udata[f] = data[2]
    else:
        idata[f] = data
        qdata[f] += np.nan
        udata[f] += np.nan


##############################################
##############################################
####start I data processing
##############################################
##############################################

####seperate regions##
incomplete_fs = np.arange(len(freqs))[np.isnan(np.sum(idata, axis=1))]
complete_fs = np.arange(len(freqs))[~np.isnan(np.sum(idata, axis=1))]
n_incomplete = np.sum(np.isnan(np.sum(idata, axis=1)))#number of incomplete maps
max_n_region = 2**n_incomplete #maximum number of possible regions
region_mask_list = []
region_indices_list = []
for n_reg in range(max_n_region):
    fill_mask = np.array([bool(int(c)) for c in bin(n_reg)[2:].zfill(n_incomplete)])
    matching_mask = np.ones(mother_npix, dtype=bool)
    for i, f in enumerate(incomplete_fs):
        matching_mask = matching_mask & ((~np.isnan(idata[f])) == fill_mask[i])
    if np.sum(matching_mask) != 0:
        region_mask_list.append(matching_mask)
        region_indices_list.append(sorted(np.concatenate((incomplete_fs[fill_mask], complete_fs))))

region_illustration = np.empty(mother_npix)
for i, mask in enumerate(region_mask_list):
    region_illustration[mask] = i
hpv.mollview(region_illustration, nest=True)
plt.show()

####get eigen systems##
evs = []#np.zeros((len(region_mask_list), len(freqs)))
ecs = []#np.zeros((len(region_mask_list), len(freqs), len(freqs)))
normalizations = []
pix_normalization = np.zeros(mother_npix)
for i, (mask, fs) in enumerate(zip(region_mask_list, region_indices_list)):

    normalization = np.linalg.norm(idata[fs][:, mask], axis=1)
    normalized_data = idata[fs][:, mask] / normalization[:, None]

    pix_normalization[mask] = np.linalg.norm(normalized_data, axis=0) / len(normalized_data)**.5

    i_cov = np.einsum('ik,jk->ij', normalized_data, normalized_data) / len(fs)
    ev, ec = np.linalg.eig(i_cov)
    ec *= np.sign(ec[-1])

    evs.append(ev)
    ecs.append(ec)
    normalizations.append(normalization)

[plt.plot(ev) for ev in evs]; plt.show()
for i in range(4):
    plt.subplot(4, 1, i+1)
    for fs, ec in zip(region_indices_list, ecs):
        plt.plot(fs, ec[:, i])
        plt.ylim([-1, 1])
plt.show()

###get principal maps
n_principal = 5
principal_matrix = ecs[-1][:, :n_principal]
principal_maps = np.zeros((n_principal, mother_npix))
for i, (mask, fs) in enumerate(zip(region_mask_list, region_indices_list)):
    A = principal_matrix[fs]
    Ninv = np.linalg.inv(i_cov[fs][:, fs])
    principal_maps[:, mask] = np.linalg.inv(A.transpose().dot(Ninv.dot(A))).dot(A.transpose().dot(Ninv.dot(idata[fs][:, mask] / normalizations[-1][fs, None])))
principal_fits = principal_matrix.dot(principal_maps)

for i in range(n_principal):
    hpv.mollview(principal_maps[i], nest=True, sub=(2, n_principal, i + 1), min=np.percentile(principal_maps[i], 3), max=np.percentile(principal_maps[i], 97))
    plt.subplot(2, n_principal, i + 1 + n_principal)
    plt.plot(np.log10(freqs), principal_matrix[:, i])
    plt.ylim([-1, 1])
plt.show()

for i, data in enumerate(idata / normalizations[-1][:, None]):
    hpv.mollview(np.abs(principal_fits[i] - data) / data, nest=True, title='%.3fGHz'%freqs[i], sub=(4, (len(freqs) - 1) / 4. + 1, i + 1), max=1, min=0)
plt.show()