"""
traceorbit.py

A module aimed at projecting an orbit forward or backward through time.
Operates in a co-rotating, RH cartesian coordinate system centred on the
local standard of rest.
"""

import logging
import numpy as np

from astropy.io import fits
from galpy.orbit import Orbit
from galpy.potential import MWPotential2014, MiyamotoNagaiPotential
from galpy.util import bovy_conversion

# mp = MWPotential2014
mp = MiyamotoNagaiPotential(a=0.5,b=0.0375,amp=1.,normalize=1.) # Params from the example webpage. No idea if that's good or not.

from . import coordinate


def convert_myr2bovytime(times):
    """
    Convert times provided in Myr into times in bovy internal units.

    Galpy parametrises time based on the natural initialising values
    (r_0 and v_0) such that after 1 unit of time, a particle in a
    circular orbit at r_0, with circular velocity of v_0 will travel
    1 radian, azimuthally.

    Paramters
    ---------
    times : [ntimes] float array
        Times in Myr

    Return
    ------
    bovy_times : [ntimes] float array
        Times in bovy internal units
    """
    bovy_times = times*1e-3 / bovy_conversion.time_in_Gyr(220., 8.)
    return bovy_times


def convert_galpycoords2cart(data, ts=None, ro=8., vo=220., rc=True):
    """
    Converts orbits from galpy internal coords to chronostar coords

    Data should be raw galpy data (i.e. output from o.getOrbit()).
    Chronostar coordinate frame is a corotating reference frame centred on
    the LSR as defined by the Schoenrich solar motion of
    XYZUVW = 0, 0, 25pc, 11.1 km/s, 12.24 km/s, 7.25 km/s
    Galpy coordinates are [R, vR, vT, z, vz, phi]
    By default, positions are scaled by LSR distance from galactic centre,
    ro=8kpc, and velocities scaled by the LSR circular velocity,
    vo = 220km/s. Time is scaled such that after 1 time unit has passed,
    the LSR has travelled 1 radian about the galactic centre. The values are
    returned in a [ntimes, 6]

    array:
        R : galactic radial distance /ro
        vR : galactic radial velocity /vo
        vT : circular velocity /vo
        z  : vertical distance from plane / ro
        vz : vertical velocity / vo
        phi : angle about the galaxy (anticlockwise from LSR's location at
             t=0)
    For example, the LSR at t=0.0 and t=1.0 as values:
    [1., 0., 1., 0., 0., 0.]
    [1., 0., 1., 0., 0., 1.]

    Parameters
    ----------
    data : [ntimes, 6] float array
        output from o.getOrbit. Data is encoded as:
        [R, vR, vT, z, vz, phi]
        R : galactic radial distance /ro
        vR : galactic radial velocity /vo
        vT : circular velocity /vo
        z  : vertical distance from plane / ro
        vz : vertical velocity / vo
        phi : angle about the galaxy (anticlockwise from LSR's location
              at t=0)
    ts : [ntimes] float array [galpy time units]
        times used to generate orbit. Ensure the units are in galpy time
        units
    ro : float
        a conversion factor that takes units from galpy units to
        physical units. If left as default, output will be in kpc
    vo : float
        a conversion factor that takes units form galpy units to
        physical units. If left as default, output will be in km/s
        This is also the circular velocity of a circular orbit with X,Y
        equal to that of the sun.
    rc : boolean
        whether to calculate XYZUVW in a right handed coordinate system
        (X, U positive towards galactic centre)

    Returns
    -------
    xyzuvw : [ntimes, 6] float array
        [pc, pc, pc, km/s, km/s, km/s] - traced orbit in chronostar
        coordinates
    """
    if ts is not None:
        phi_lsr = ts
    else:
        phi_lsr = 0.0
    R, vR, vT, z, vz, phi_s = data.T

    # This is the angular distance between the LSR and our star
    phi = phi_s - phi_lsr

    # Can convert to XYZUVW coordinate frame. See thesis for derivation
    # Need to scale values back into physical units with ro and vo.
    # 1. in X and V are the LSR R and vT respectively (which are unitary
    # due to the normalisation of units inside galpy
    X = 1000 * ro * (1. - R * np.cos(phi))
    Y = 1000 * ro * R * np.sin(phi)
    Z = 1000 * ro * z
    U = vo * (-vR*np.cos(phi) + vT*np.sin(phi))
    V = vo * ( vT*np.cos(phi) + vR*np.sin(phi) - 1.)
    W = vo * vz

    if not rc:
        print("BUT EVERYONE IS USING RHC!!!")
        X = -X
        U = -U

    xyzuvw = np.vstack((X,Y,Z,U,V,W)).T
    # included for compatability with single data point
    if xyzuvw.shape == (1,6):
        xyzuvw = xyzuvw[0]
    return xyzuvw

def trace_cartesian_orbit(xyzuvw_start, times=None, single_age=True,
                          potential=MWPotential2014):
    """
    Given a star's XYZUVW relative to the LSR (at any time), project its
    orbit forward (or backward) to each of the times listed in *times*

    Positive times --> traceforward
    Negative times --> traceback

    TODO: Primary source of inefficiencies, 1366.2 (s)

    Parameters
    ----------
    xyzuvw : [pc,pc,pc,km/s,km/s,km/s]
    times : (float) or ([ntimes] float array)
        Myr - time of 0.0 must be present in the array. Times need not be
        spread linearly.
    single_age: (bool) {True}
        Set this flag if only providing a single age to trace to

    Returns
    -------
    xyzuvw_tf : [ntimes, 6] array
        [pc, pc, pc, km/s, km/s, km/s] - the traced orbit with positions
        and velocities

    Notes
    -----
    Profiling comments have been left in for future reference, but note
    that the profiling was done with previous versions of coordinate
    functions - ones that utilised astropy.units (and thus symbolic algebra)
    """
    # convert positions to kpc
    if single_age:
        # replace 0 with some tiny number
        if times == 0.:
            times = 1e-10
        times = np.array([0., times])
    else:
        times = np.array(times)
        # times[np.where(times == 0.)] = 1e-10

    xyzuvw_start = np.copy(xyzuvw_start)
    xyzuvw_start[:3] *= 1e-3 # pc to kpc
    # profiling:   3 (s)
    bovy_times = convert_myr2bovytime(times)

    # profiling:   9 (s)
    xyzuvw_helio = coordinate.convert_lsr2helio(xyzuvw_start, kpc=True)

    # profiling: 141 (s)
    l,b,dist = coordinate.convert_cartesian2angles(*xyzuvw_helio[:3], return_dist=True)
    vxvv = [l,b,dist,xyzuvw_helio[3],xyzuvw_helio[4],xyzuvw_helio[5]]

    # profiling:  67 (s)
    o = Orbit(vxvv=vxvv, lb=True, uvw=True, solarmotion='schoenrich')

    # profiling: 546 (s)
    o.integrate(bovy_times, potential, method='odeint')
    data_gp = o.getOrbit()
    # profiling:  32 (s)
    xyzuvw = convert_galpycoords2cart(data_gp, bovy_times)

    if single_age:
        return xyzuvw[-1]
    return xyzuvw


def trace_many_cartesian_orbit(xyzuvw_starts, times=None, single_age=True,
                               savefile=''):
    """
    (This function is not used by Chronostar (yet). It is currently here
    purely for testing reasons.)

    Given a star's XYZUVW relative to the LSR (at any time), project its
    orbit forward (or backward) to each of the times listed in *times*

    Positive times --> traceforward
    Negative times --> traceback

    Parameters
    ----------
    xyzuvw_starts : [nstars, 6] array (pc,pc,pc,km/s,km/s,km/s)
    times : [ntimes] float array
        Myr - time of 0.0 must be present in the array. Times need not be
        spread linearly.
    single_age : (Boolean {False})
        If set to true, times must be given a single non-zero float

    Returns
    -------
    xyzuvw_to : [nstars, ntimes, 6] array
        [pc, pc, pc, km/s, km/s, km/s] - the traced orbit with positions
        and velocities
        If single_age is set, output is [nstars, 6] array
    """
    if single_age:
        ntimes = 1
    else:
        times = np.array(times)
        ntimes = times.shape[0]

    nstars = xyzuvw_starts.shape[0]
    logging.debug("Nstars: {}".format(nstars))

    if single_age:
        xyzuvw_to = np.zeros((nstars, 6))
    else:
        xyzuvw_to = np.zeros((nstars, ntimes, 6))
    for st_ix in range(nstars):
        xyzuvw_to[st_ix] = trace_cartesian_orbit(xyzuvw_starts[st_ix], times,
                                                 single_age=single_age)
    #TODO: test this
    if savefile:
        np.save(savefile, xyzuvw_to)
    return xyzuvw_to


def trace_orbit_builder(potential):
    """
    Build a replica of trace_cartesian_orbit but with custom
    potential. e.g. MiyamotoNagaiPotential
    With parameters (from website):
    MiyamotoNagaiPotential(a=0.5,b=0.0375,amp=1.,normalize=1.)
    """
    def f_(xyzuvw_start, times=None, single_age=True):
        return trace_cartesian_orbit(xyzuvw_start=xyzuvw_start, times=times,
                                     single_age=single_age,
                                     potential=potential)
    return f_


# def generateTracebackFile(star_pars_now, times, savefile=''):
#     """
#     Take XYZUVW of the stars at the current time and trace back for
#     timesteps
#
#     Parameters
#     ----------
#     star_pars_now: dict
#         'xyzuvw': [nstars, 6] numpy array
#             the mean XYZUVW for each star at t=0
#         'xyzuvw_cov': [nstars, 6, 6] numpy array
#             the covariance for each star at t=0
#     times: [ntimes] array
#         the times at which to be traced back to
#     """
#     times = np.array(times)
#     ntimes = times.shape[0]
#     nstars = star_pars_now['xyzuvw'].shape[0]
#     logging.debug("Attempting traced means")
#     means = traceManyOrbitXYZUVW(star_pars_now['xyzuvw'], times,
#                                  single_age=False)
#     logging.debug("Successfully traced means")
#
#     covs = np.zeros((nstars, ntimes, 6, 6))
#     for star_ix in range(nstars):
#         for time_ix in range(ntimes):
#             if times[time_ix] == 0.0:
#                 covs[star_ix, time_ix] = star_pars_now['xyzuvw_cov'][star_ix]
#             else:
#                 covs[star_ix, time_ix] =\
#                     tf.transformCovMat(cov=star_pars_now['xyzuvw_cov'][star_ix],
#                                        trans_func=traceOrbitXYZUVW,
#                                        loc=star_pars_now['xyzuvw'][star_ix],
#                                        args=(times[time_ix],)
#                                        )
#     logging.debug("Successfully traced covs")
#     star_pars_all = {'xyzuvw':means,
#                      'xyzuvw_cov':covs,
#                      'times':times}
#     if savefile:
#         if (savefile[-3:] != 'fit') and (savefile[-4:] != 'fits'):
#             savefile = savefile + ".fits"
#         hl = fits.HDUList()
#         hl.append(fits.PrimaryHDU())
#         hl.append(fits.ImageHDU(star_pars_all['xyzuvw']))
#         hl.append(fits.ImageHDU(star_pars_all['xyzuvw_cov']))
#         hl.append(fits.ImageHDU(star_pars_all['times']))
#         hl.writeto(savefile, overwrite=True)
#
#     return star_pars_all
#
#

