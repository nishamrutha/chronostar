from __future__ import print_function, division
"""
A suite of useful functions for partitioning the gaia data
TODO: write tests especially for cov construction
"""

from astropy.io import fits
import numpy as np
import logging
import sys
sys.path.insert(0, '..')

import chronostar.converter as cv
import chronostar.coordinate as cc


def gauss(x, mu, sig):
    """
    Evaluates a 1D gaussian at `x` given mean `mu` and std `sig`
    """
    return 1./(sig*np.sqrt(2*np.pi)) * np.exp(-(x - mu)**2 / (2.*sig**2))


def loadGroups(groups_file):
    """A simple utility function to standardise loading of group savefiles

    :param groups_file:
    :return:
    """
    groups = np.load(groups_file)
    if len(groups.shape) == 0:
        groups = np.array([groups.item()])
    return groups


def loadXYZUVW(xyzuvw_file):
    """Load mean and covariances of stars in XYZUVW space from fits file

    Parameters
    ----------
    xyzuvw_file : (String)
        Ideally *.fits, the file name of the fits file with and hdulist:
            [1] : xyzuvw
            [2] : xyzuvw covariances

    Returns
    -------
    xyzuvw_dict : (dictionary)
        xyzuvw : ([nstars, 6] float array)
            the means of the stars
        xyzuvw_cov : ([nstars, 6, 6] float array)
            the covariance matrices of the stars
    """
    if (xyzuvw_file[-3:] != 'fit') and (xyzuvw_file[-4:] != 'fits'):
        xyzuvw_file = xyzuvw_file + ".fits"
    # TODO Ask Mike re storing fits files as float64 (instead of '>f8')
    xyzuvw_now = fits.getdata(xyzuvw_file, 1).\
        astype('float64') #hdulist[1].data
    xyzuvw_cov_now = fits.getdata(xyzuvw_file, 2)\
        .astype('float64') #hdulist[2].data
    xyzuvw_dict = {'xyzuvw':xyzuvw_now, 'xyzuvw_cov':xyzuvw_cov_now}
    try:
        times = fits.getdata(xyzuvw_file, 3)
        xyzuvw_dict['times'] = times
    except:
        logging.info("No times in fits file")
    try:
        stars_table = fits.getdata(xyzuvw_file, 3)
        xyzuvw_dict['table'] = stars_table
    except:
        logging.info("No table in fits file")
    logging.info("Floats stored in format {}".\
                 format(xyzuvw_dict['xyzuvw'].dtype))
    return xyzuvw_dict

def createSubFitsFile(mask, filename):
    """
    Provide a mask (constructed based on Gaia DR2 fits) to build new one

    Parameters
    ----------
    mask : [nstars] int array in tuple
        The output of np.where applying some filter to gaia data
        e.g.
            np.where(hdul[1].data[:,1] > 0)
        produces a mask to grab all stars with positive DEC
    filename : string
        name of destination fits file
    """
    if filename[-4:] != "fits":
        filename += ".fits"
    gaia_file = "../data/all_rvs_w_ok_plx.fits"
    with fits.open(gaia_file) as hdul:
        primary_hdu = fits.PrimaryHDU(header=hdul[1].header)
        hdu = fits.BinTableHDU(data=hdul[1].data[mask])
        new_hdul = fits.HDUList([primary_hdu, hdu])
        new_hdul.writeto(filename, overwrite=True)


# def tempCreateSubFitsFile(data, filename):
#     """
#     Provide a mask (constructed based on Gaia DR2 fits) to build new one
#
#     Parameters
#     ----------
#     mask : [nstars] int array in tuple
#         The output of np.where applying some filter to gaia data
#         e.g.
#             np.where(hdul[1].data[:,1] > 0)
#         produces a mask to grab all stars with positive DEC
#     filename : string
#         name of destination fits file
#     """
#     if filename[-4:] != "fits":
#         filename += ".fits"
#     gaia_file = "../data/all_rvs_w_ok_plx.fits"
#     with fits.open(gaia_file) as hdul:
#         primary_hdu = fits.PrimaryHDU(header=hdul[1].header)
#         hdu = fits.BinTableHDU(data=hdul[1].data[mask])
#         new_hdul = fits.HDUList([primary_hdu, hdu])
#         new_hdul.writeto(filename, overwrite=True)


def convertRecToArray(sr):
    """UNTESTED"""
    ra = sr['ra']
    e_ra = sr['ra_error'] / 3600. / 1000.
    dec = sr['dec']
    e_dec = sr['dec_error'] / 3600. / 1000.
    plx = sr['parallax']
    e_plx = sr['parallax_error']
    pmra = sr['pmra']
    e_pmra = sr['pmra_error']
    pmdec = sr['pmdec']
    e_pmdec = sr['pmdec_error']
    rv = sr['radial_velocity']
    e_rv = sr['radial_velocity_error']
    c_ra_dec = sr['ra_dec_corr']
    c_ra_plx = sr['ra_parallax_corr']
    c_ra_pmra = sr['ra_pmra_corr']
    c_ra_pmdec = sr['ra_pmdec_corr']
    c_dec_plx = sr['dec_parallax_corr']
    c_dec_pmra = sr['dec_pmra_corr']
    c_dec_pmdec = sr['dec_pmdec_corr']
    c_plx_pmra = sr['parallax_pmra_corr']
    c_plx_pmdec = sr['parallax_pmdec_corr']
    c_pmra_pmdec = sr['pmra_pmdec_corr']

    mean = np.array((ra, dec, plx, pmra, pmdec, rv))
    cov  = np.array([
        [e_ra**2, c_ra_dec*e_ra*e_dec, c_ra_plx*e_ra*e_plx,
            c_ra_pmra*e_ra*e_pmra, c_ra_pmdec*e_ra*e_pmdec, 0.],
        [c_ra_dec*e_ra*e_dec, e_dec**2, c_dec_plx*e_dec*e_plx,
            c_dec_pmra*e_dec*e_pmra, c_dec_pmdec*e_dec*e_pmdec, 0.],
        [c_ra_plx*e_ra*e_plx, c_dec_plx*e_dec*e_plx, e_plx**2,
            c_plx_pmra*e_plx*e_pmra, c_plx_pmdec*e_plx*e_pmdec, 0.],
        [c_ra_pmra*e_ra*e_pmra, c_dec_pmra*e_dec*e_pmra,
                                                c_plx_pmra*e_plx*e_pmra,
             e_pmra**2, c_pmra_pmdec*e_pmra*e_pmdec, 0.],
        [c_ra_pmdec*e_ra*e_pmdec, c_dec_pmdec*e_dec*e_pmdec,
                                                c_plx_pmdec*e_plx*e_pmdec,
             c_pmra_pmdec*e_pmra*e_pmdec, e_pmdec**2, 0.],
        [0., 0., 0., 0., 0., e_rv**2]
    ])
    return mean, cov

def convertManyRecToArray(data):
    """
    Convert many Fits Records in astrometry into mean and covs (astro)

    Note: ra_error and dec_error are in 'mas' while ra and dec
    are given in degrees. Everything else is standard:
    plx [mas], pm [mas/yr], rv [km/s]

    Parameters
    ----------
    data: [nstars] array of Recs
        'source_id', 'ra', 'ra_error', 'dec', 'dec_error', 'parallax',
        'parallax_error', 'pmra', 'pmra_error', 'pmdec', 'pmdec_error',
        'ra_dec_corr', 'ra_parallax_corr', 'ra_pmra_corr',
        'ra_pmdec_corr', 'dec_parallax_corr', 'dec_pmra_corr',
        'dec_pmdec_corr', 'parallax_pmra_corr', 'parallax_pmdec_corr',
        'pmra_pmdec_corr', 'astrometric_primary_flag', 'phot_g_mean_mag',
        'radial_velocity', 'radial_velocity_error', 'teff_val'

    Returns
    -------
        means: [nstars, 6] array
        covs: [nstars, 6] array
    """
    logging.info("In convertManyRecToArray")
    nstars = data.shape[0]
    print("nstars: {}".format(nstars))
    logging.info("nstars: {}".format(nstars))
    means = np.zeros((nstars,6))

    means[:,0] = data['ra']
    means[:,1] = data['dec']
    means[:,2] = data['parallax']
    means[:,3] = data['pmra']
    means[:,4] = data['pmdec']
    means[:,5] = data['radial_velocity']

    # Array of dictionary keys to aid construction of cov matrices
    cls = np.array([
        ['ra_error',         'ra_dec_corr',           'ra_parallax_corr',
                'ra_pmra_corr',       'ra_pmdec_corr',       None],
        ['ra_dec_corr',      'dec_error',             'dec_parallax_corr',
                'dec_pmra_corr',      'dec_pmdec_corr',      None],
        ['ra_parallax_corr', 'dec_parallax_corr',     'parallax_error',
                'parallax_pmra_corr', 'parallax_pmdec_corr', None],
        ['ra_pmra_corr',     'dec_pmra_corr',         'parallax_pmra_corr',
                 'pmra_error',        'pmra_pmdec_corr',     None],
        ['ra_pmdec_corr',    'dec_pmdec_corr',        'parallax_pmdec_corr',
                 'pmra_pmdec_corr',   'pmdec_error',         None],
        [None,               None,                     None,
                 None,                 None, 'radial_velocity_error']
    ])

    # Construct an [nstars,6,6] array of identity matrices
    covs = np.zeros((nstars,6,6))
    idx = np.arange(6)
    covs[:, idx, idx] = 1.0

    # Insert correlations into off diagonals
    for i in range(0,5):
        for j in range(i+1,5):
            covs[:,i,j] = covs[:,j,i] = data[cls[i,j]]

    # multiply each row and each column by appropriate error
    for i in range(6):
        covs[:,i,:] *= np.tile(data[cls[i,i]], (6,1)).T
        covs[:,:,i] *= np.tile(data[cls[i,i]], (6,1)).T

    # Might need to introduce some artificial uncertainty in
    # ra and dec so as to avoid indefinite matrices (too narrow)

    # RA and DEC errors are actually quoted in mas, so we convert cov
    # entries into degrees
    covs[:,:,:2] /= 3600000.
    covs[:,:2,:] /= 3600000.

    return means, covs

def convertGaiaToXYZUVWDict(astr_file="../data/gaia_dr2_ok_plx.fits",
                            server=False,
                            return_dict=False):
    """
    Supposed to generate XYZYVW dictionary for input to GroupFitter

    Doesn't work on whole Gaia catalogue... too much memory I think

    TODO: Sort out a more consistent way to handle file names...
    """
    if server:
        rdir = '/data/mash/tcrun/'
    else:
        rdir = '../data/'

    logging.info("Converting: {}".format(astr_file))
    hdul = fits.open(astr_file)#, memmap=True)
    logging.info("Loaded hdul")
    means, covs = convertManyRecToArray(hdul[1].data)
    logging.info("Converted many recs")
    astr_dict = {'astr_mns': means, 'astr_covs': covs}
    cart_dict = cv.convertMeasurementsToCartesian(
        astr_dict=astr_dict, savefile=rdir+astr_file[:-5]+"_xyzuvw.fits")
    logging.info("Converted and saved dictionary")
    if return_dict:
        return cart_dict


def convertGaiaMeansToXYZUVW(astr_file="all_rvs_w_ok_plx", server=False):
    """
    Generate mean XYZUVW for eac star in provided fits file (Gaia format)
    """
    if server:
        rdir = '/data/mash/tcrun/'
    else:
        rdir = '../data/'
    #gaia_astr_file = rdir+'all_rvs_w_ok_plx.fits'
    gaia_astr_file = rdir+astr_file+".fits"
    hdul = fits.open(gaia_astr_file)#, memmap=True)
    nstars = hdul[1].data.shape[0]
    means = np.zeros((nstars,6))
    means[:,0] = hdul[1].data['ra']
    means[:,1] = hdul[1].data['dec']
    means[:,2] = hdul[1].data['parallax']
    means[:,3] = hdul[1].data['pmra']
    means[:,4] = hdul[1].data['pmdec']
    means[:,5] = hdul[1].data['radial_velocity']

    xyzuvw_mns = cc.convertManyAstrometryToLSRXYZUVW(means, mas=True)
    np.save(rdir + astr_file + "mean_xyzuvw.npy", xyzuvw_mns)


def calcHistogramDensity(x, bin_heights, bin_edges):
    """
    Calculates the density of a pdf characterised by a histogram at point x
    """
    # Check if handling 1D histogram
    if len(bin_heights.shape) == 1:
        raise UserWarning
    dims = len(bin_heights.shape)
    bin_widths = [bins[1] - bins[0] for bins in bin_edges]
    bin_area = np.prod(bin_widths)

    x_ix = tuple([np.digitize(x[dim], bin_edges[dim]) - 1
                  for dim in range(dims)])
    return bin_heights[x_ix] / bin_area


def collapseHistogram(bin_heights, dim):
    """
    Collapse a multi dimensional histogram into a single dimension

    Say you have a 6D histogram, but want the 1D projection onto
    the X axis, simply call this function with `dim=0`
    Uses string trickery and einstein sum notation to pick the
    dimension to retain


    Parameters
    ----------
    bin_heights: `dims`*[nbins] array
        an array of length `dims` with shape (nbins, nbins, ..., nbins)
        first output of np.histogramdd
    dim: integer
        the dimension which to collapse onto
    """
    dims = len(bin_heights.shape)

    # generates `dims` length string 'ijkl...'
    indices = ''.join([chr(105+i) for i in range(dims)])

    # reduce-sum each axis except the `dim`th axis
    summed_heights = np.einsum('{}->{}'.format(indices, indices[dim]),
                               bin_heights)
    return summed_heights


def sampleHistogram(bin_heights, bin_edges, lower_bound, upper_bound,
                    npoints=10):
    """
    Hard coded to return 1D projection to x
    """
    # x_vals = np.linspace(lower_bound[0], upper_bound[0], npoints, endpoint=False)
    # step_sizes = (upper_bound - lower_bound)/(npoints-1)
    # # y = lower_bound[1]
    # heights = []
    densities = []
    pts = []
    # TODO: Consider step size not accurate, need npoitns + 1 or something
    # TODO: still not right.. make sure not counting "empty" bins...
    for x in np.linspace(lower_bound[0], upper_bound[0], npoints, endpoint=False):
        print('x: ', x)
        for y in np.linspace(lower_bound[1], upper_bound[1], npoints, endpoint=False):
            print('y: ', y)
            for z in np.linspace(lower_bound[2], upper_bound[2], npoints, endpoint=False):
                for u in np.linspace(lower_bound[3], upper_bound[3], npoints, endpoint=False):
                    for v in np.linspace(lower_bound[4], upper_bound[4], npoints, endpoint=False):
                        for w in np.linspace(lower_bound[5], upper_bound[5], npoints, endpoint=False):
                            pt = [x,y,z,u,v,w]
                            pts.append(pt)
                            density = calcHistogramDensity(pt,
                                                           bin_heights,
                                                           bin_edges)
                            densities.append(density)
                            # only product by area of remaining dimensions
                            # height += density * np.prod(step_sizes[1:])
        # heights.append(height)

    return np.array(pts), np.array(densities)

def integrateHistogram2(bin_heights, bin_edges, lower_bound, upper_bound,
                       dim):
    """
    Hard coded to return 1D projection to x
    """
    npoints = 10
    dims = len(lower_bound)
    pts, densities = sampleHistogram(bin_heights, bin_edges, lower_bound,
                                     upper_bound, npoints=npoints)
    new_bin_edges = np.linspace(lower_bound[dim], upper_bound[dim], npoints,
                                endpoint=False)
    step_sizes = (upper_bound - lower_bound) / (npoints)

    new_bin_heights = []
    for ledge in new_bin_edges:
        height = np.sum(densities[np.where(pts[:,dim] == ledge)])
        new_bin_heights.append(height * np.prod(step_sizes) / step_sizes[dim])

    return np.array(new_bin_heights), np.array(new_bin_edges)

    #
    # xs, ys, zs, us, vs, ws =\
    #     np.meshgrid(np.arange(lower_bound[0], upper_bound[0], npoints),
    #                 np.arange(lower_bound[1], upper_bound[1], npoints),
    #                 np.arange(lower_bound[2], upper_bound[2], npoints),
    #                 np.arange(lower_bound[3], upper_bound[3], npoints),
    #                 np.arange(lower_bound[4], upper_bound[4], npoints),
    #                 np.arange(lower_bound[5], upper_bound[5], npoints),
    #                 )
    # np.mgrid[lower_bound[0]:upper_bound[0]:10j,
    #         lower_bound[1]:upper_bound[1]:10j,
    #         lower_bound[2]:upper_bound[2]:10j,
    #         lower_bound[3]:upper_bound[3]:10j,
    #         lower_bound[4]:upper_bound[4]:10j,
    #         lower_bound[5]:upper_bound[5]:10j]
    #
    #
    # x_vals = np.linspace(lower_bound[0], upper_bound[0], npoints)
    # step_sizes = (upper_bound - lower_bound)/(npoints-1)
    # y = lower_bound[1]
    # heights = []
    # # TODO: Consider step size not accurate, need npoitns + 1 or something
    # # TODO: still not right.. make sure not counting "empty" bins...
    # for x in x_vals:
    #     height = 0
    #     for y in np.linspace(lower_bound[1], upper_bound[1], npoints):
    #         for z in np.linspace(lower_bound[2], upper_bound[2], npoints):
    #             for u in np.linspace(lower_bound[3], upper_bound[3], npoints):
    #                 for v in np.linspace(lower_bound[4], upper_bound[4], npoints):
    #                     for w in np.linspace(lower_bound[5], upper_bound[5], npoints):
    #                         density = calcHistogramDensity([x,y,z,u,v,w],
    #                                                        bin_heights,
    #                                                        bin_edges)
    #                         # only product by area of remaining dimensions
    #                         height += density * np.prod(step_sizes[1:])
    #     heights.append(height)
    # return x_vals, heights


def samplePoints(bin_heights, bin_edges, lower_bound, upper_bound):
    """
    Montecarlo sample points within range of bounds,
    :param bin_heights:
    :param bin_edges:
    :param lower_bound:
    :param upper_bound:
    :return:
    """


def sampleAndBuild1DHist(bin_heights, bin_edges, lower_bound, upper_bound,
                         dim):
    """
    Monte carlo sample master histogram within bounds, then project to 1D

    :param bin_heights:
    :param bin_edges:
    :param lower_bound:
    :param upper_bound:
    :param dim:
    :return:
    new_bin_heights
    new_bin_edges
    """
    ndims = len(bin_heights.shape)
    nsamples = 10**6
    samples = samplePoints(bin_heights, bin_edges, lower_bound, upper_bound)
    sample_hist = np.histogramdd(samples)

    #TODO: normalise by nsamples_survived, and renormalise by star count
    return collapseHistogram(sample_hist[0], dim), sample_hist[1][dim]
