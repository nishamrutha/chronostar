"""This program takes an initial model for a stellar association and uses an affine invariant
Monte-Carlo to fit for the group parameters.

A group fitter, called after tracing orbits back.

This group fitter will find the best fit 6D error ellipse and best fit time for
the group formation based on Bayesian analysis, which in this case involves
computing overlap integrals. 
    
TODO:
0) Once the group is found, output the probability of each star being in the group.
1) Add in multiple groups 
2) Change from a group to a cluster, which can evaporate e.g. exponentially.
3) Add in a fixed background which is the Galaxy (from Robin et al 2003).

To use MPI, try:

mpirun -np 2 python fit_group.py

Note that this *doesn't* work yet due to a "pickling" problem.
"""

from __future__ import print_function, division

import emcee
import sys
import numpy as np
import matplotlib.pyplot as plt
import pickle
import pdb
try:
    import astropy.io.fits as pyfits
except:
    import pyfits

try:
    import _overlap as overlap #&TC
except:
    print("overlap not imported, SWIG not possible. Need to make in directory...")
import time    #&TC
from emcee.utils import MPIPool
   
def compute_overlap(A,a,A_det,B,b,B_det):
    """Compute the overlap integral between a star and group mean + covariance matrix
    in six dimensions, including some temporary variables for speed and to match the 
    notes.
    
    This is the first function to be converted to a C program in order to speed up."""

    #Preliminaries - add matrices together. This might make code more readable? 
    #Or might not.
    ApB = A + B
    AapBb = np.dot(A,a) + np.dot(B,b)
    
    #Compute determinants.
    ApB_det = np.linalg.det(ApB)
    
    #Error checking (not needed in C once shown to work?) This shouldn't ever happen, as 
    #the determinants of the sum of positive definite matrices is
    #greater than the sum of their determinants    
    if (ApB_det < 0) | (B_det<0):
        pdb.set_trace()
        return -np.inf
    
    #Solve for c
    c = np.linalg.solve(ApB, AapBb)
    
    #Compute the overlap formula.
    overlap = np.exp(-0.5*(np.dot(b-c,np.dot(B,b-c)) + \
                           np.dot(a-c,np.dot(A,a-c)) )) 

    overlap *= np.sqrt(B_det*A_det/ApB_det)/(2*np.pi)**3.0
    
    return overlap
   
def read_stars(infile):
    """Read stars from a previous pickle file into a dictionary.
    
    The input is an error ellipse in 6D (X,Y,Z,U,V,W) of a list of stars, at
    a bunch of times in the past.
    
    Parameters
    ----------
    infile: string
        input pickle file
        
    Returns
    -------
    star_dictionary: dict
        stars: (nstars) high astropy table including columns as documented in the Traceback class.
        times: (ntimes) numpy array, containing times that have been traced back, in Myr
        xyzuvw (nstars,ntimes,6) numpy array, XYZ in pc and UVW in km/s
        xyzuvw_cov (nstars,ntimes,6,6) numpy array, covariance of xyzuvw
    """
    if len(infile)==0:
        print("Input a filename...")
        raise UserWarning
    
    #Stars is an astropy.Table of stars
    if infile[-3:] == 'pkl':
        with open(infile,'r') as fp:
            (stars,times,xyzuvw,xyzuvw_cov)=pickle.load(fp)
    elif (infile[-3:] == 'fit') or (infile[-4:] == 'fits'):
        stars = pyfits.getdata(infile,1)
        times = pyfits.getdata(infile,2)
        xyzuvw = pyfits.getdata(infile,3)
        xyzuvw_cov = pyfits.getdata(infile,4) 
    else:
        print("Unknown File Type!")
        raise UserWarning
    #Create the inverse covariances to save time.
    xyzuvw_icov = np.linalg.inv(xyzuvw_cov)
    xyzuvw_icov_det = np.linalg.det(xyzuvw_icov)

    return dict(stars=stars,times=times,xyzuvw=xyzuvw,xyzuvw_cov=xyzuvw_cov,xyzuvw_icov=xyzuvw_icov,xyzuvw_icov_det=xyzuvw_icov_det)


def interp_cov(target_time, star_params):
    """
    Interpolate in time to get a xyzuvw vector and covariance matrix.
    
    Note that there is a fast scipy package (in ndimage?) that might be good for this.
    """         
    times = star_params['times']
    ix = np.interp(target_time,times,np.arange(len(times)))
    ix0 = np.int(ix)
    frac = ix-ix0
    bs     = star_params['xyzuvw'][:,ix0]*(1-frac) + star_params['xyzuvw'][:,ix0+1]*frac
    cov    = star_params['xyzuvw_cov'][:,ix0]*(1-frac) + star_params['xyzuvw_cov'][:,ix0+1]*frac
    return bs, cov
   
def lnprob_one_group(x, star_params, background_density=2e-12,use_swig=True,t_ix = 0,return_overlaps=False,\
    return_cov=False, min_axis=2.0,min_v_disp=0.5,debug=False, print_times=False):
    """Compute the log-likelihood for a fit to a group.

    The x variables are:
    xyzuvw (6), then xyz standard deviations (3), uvw_symmetrical_std (1), xyz_correlations (3)

    A 14th variable, if present, is the time at which the calculation is made. If not given, the
    calculation is made at a fixed time index t_ix.

    The probability of a model is the product of the probabilities
    overlaps of every star in the group. 

    Parameters
    ----------
    x : array-like
        The group parameters, which are...
        x[0] to x[5] : xyzuvw
        x[6] to x[8] : positional variances in x,y,z
        x[9]  : velocity dispersion (symmetrical for u,v,w)
        x[10] to x[12] :  correlations between x,y,z
        x[13] : (optional) birth time of group in Myr. 

    background_density :
        The density of a background stellar population, in
        units of pc**(-3)*(km/s)**(-3). 
    
    t_ix : int
        Time index (in the past) where we are computing the probabilities.
    
    return_overlaps : bool  
        Return the overlaps (rather than the log probability)
    
    return_cov : bool
        Return the covariance (rather than the log probability)
    
    min_axis : float
        Minimum allowable position dispersion for the cluster in parsecs
    
    min_v_disp : float
        Minimum allowable cluster velocity dispersion in km/s.
    """
    t0=time.time()
    practically_infinity = np.inf#1e20
    
    ns = len(star_params['xyzuvw'])    #Number of stars

    #See if we have a time in Myr in the input vector, in which case we have
    #to interpolate in time. Otherwise, just choose a single time snapshot given 
    #by the input index t_ix.
    if len(x)>13:
        #If the input time is outside our range of traceback times, return
        #zero likelihood.
        if ( (x[13] < min(star_params['times'])) | (x[13] > max(star_params['times']))):
            return -np.inf 
        #Linearly interpolate in time to get bs and Bs
        bs, cov = interp_cov(x[13], star_params)  
        #WARNING: The next lines are slow, and should maybe be part of the overlap package,
        #if numpy isn't fast enough. They are slow because an inverse and a determinant
        #is computed for every star. 
        Bs     = np.linalg.inv(cov)
        B_dets = np.linalg.det(Bs)
    else:
        #Extract the time that we really care about.
        #The result is a (ns,6) array for bs, and (ns,6,6) array for Bs.
        bs     = star_params['xyzuvw'][:,t_ix]
        Bs     = star_params['xyzuvw_icov'][:,t_ix]
        B_dets = star_params['xyzuvw_icov_det'][:,t_ix]

    #Sanity check inputs for out of bounds. If so, return zero likelihood.
    if (np.min(x[6:9])<=min_axis):
        if debug:
            print("Positional Variance Too Low...")
        return -practically_infinity
    if (np.min(x[9])<min_v_disp):
        if debug:
            print("Velocity Variance Too Low...")
        return -practically_infinity
    if (np.max(np.abs(x[10:13])) >= 1):
        if debug:
            print("Correlations above 1...")
        return -practically_infinity       

    #Create the group_mn and group_cov from x. This looks a little tricky 
    #because we're inputting correlations rather than elements of the covariance
    #matrix.
    #https://en.wikipedia.org/wiki/Correlation_and_dependence
    x = np.array(x)
    group_mn = x[0:6]
    group_cov = np.eye( 6 )
    #Fill in correlations
    group_cov[np.tril_indices(3,-1)] = x[10:13]
    group_cov[np.triu_indices(3,1)] = x[10:13]
    #Convert correlation to covariance for position.
    for i in range(3):
        group_cov[i,:3] *= x[6:9]
        group_cov[:3,i] *= x[6:9]
    #Convert correlation to covariance for velocity.
    for i in range(3,6):
        group_cov[i,3:] *= x[9]
        group_cov[3:,i] *= x[9]

    #Allow this covariance matrix to be returned.
    if return_cov:
        return group_cov

    #Enforce some sanity check limits on prior...
    if (np.min(np.linalg.eigvalsh(group_cov[:3,:3])) < min_axis**2):
        if debug:
            print("Minimum positional covariance too small in one direction...")
        return -practically_infinity

    #Invert the group covariance matrix and check for negative eigenvalues
    group_icov = np.linalg.inv(group_cov)
    group_icov_eig = np.linalg.eigvalsh(group_icov)
    if np.min(group_icov_eig) < 0:
        if debug:
            print("Numerical error in inverse covariance matrix!")
        return -practically_infinity
    group_icov_det = np.prod(group_icov_eig)

    #Before starting, lets set the prior probability
    #Given the way we're sampling the covariance matrix, I'm
    #really not sure this is correct! But it is pretty close...
    #it looks almost like 1/(product of standard deviations).
    #See YangBerger1998
    lnprob=np.log(np.abs(group_icov_det)**3.5)
  
    t1=time.time()  
  
    #overlaps_start = time.clock()
    #Now loop through stars, and save the overlap integral for every star.
    overlaps = np.empty(ns)
    if use_swig:
        if (True):
            overlaps = overlap.get_overlaps(group_icov, group_mn, group_icov_det,
                                            Bs, bs, B_dets, ns)
            #note 'ns' at end, see 'overlap.c' for documentation
            lnprob = lnprob + np.sum(np.log(background_density + overlaps))
        else:
            for i in range(ns):
                overlaps[i] = overlap.get_overlap(group_icov,
                                                  group_mn,
                                                  group_icov_det,
                                                  Bs[i],
                                                  bs[i],
                                                  B_dets[i]) #&TC
                lnprob += np.log(background_density + overlaps[i])
    else:
        for i in range(ns):
            overlaps[i] = compute_overlap(group_icov,group_mn,group_icov_det,Bs[i],bs[i],B_dets[i])
            lnprob += np.log(background_density + overlaps[i])
    
    #print (time.clock() - overlaps_start)
    if print_times:
	print("{0:9.6f}, {1:9.6f}".format(time.time()-t1, t1-t0))

    if return_overlaps:
        return overlaps    
    
    return lnprob

def lnprob_one_cluster(x, star_params, use_swig=False, return_overlaps=False, \
    min_axis=2.0, min_v_disp=0.5, debug=False):
    """Compute the log-likelihood for a fit to a cluster. A cluster is defined as a group that decays 
    exponentially in time.

    The minimal set of x variables are:
    xyzuvw (6), the core radius (1),  
    the tidal radius now (1) [starts at 1.5 times the core radius], the initial velocity 
    dispersion (1) [decays according to density ** 0.5], 
    the birth time (1), the central density decay time (1),
    
    The probability of a model is the product of the probabilities
    overlaps of every star in the group. 

    Parameters
    ----------
    x : array-like
        The group parameters, which are...
        x[0] to x[5] : xyzuvw at the CURRENT time.
        x[6]  : Core radius (constant with time)
        x[7]  : Tidal radius at current epoch.
        x[8]  : Initial velocity dispersion
        x[9]  : Birth time
        x[10] : Central density 1/e decay time.
        x[11] : Initial central density [for now as a multiplier of the 
                background density in units of pc^{-3} km^{-3} s^3

    star_params : astropy table

    return_overlaps : bool  
        Return the overlaps (rather than the log probability)
    
    return_cov : bool
        Return the covariance (rather than the log probability)
    
    min_axis : float
        Minimum allowable position dispersion for the cluster in parsecs
    
    min_v_disp : float
        Minimum allowable cluster velocity dispersion in km/s.
    """
    practically_infinity = 1e20
    
    #Extract the key parameters in shorthand from star_params.
    xyzuvw = star_params['xyzuvw']
    xyzuvw_cov = star_params['xyzuvw_cov']
    xyzuvw_icov = star_params['xyzuvw_icov']
    xyzuvw_icov_det = star_params['xyzuvw_icov_det']
    times = star_params['times']
    ns = len(star_params['xyzuvw'])    #Number of stars
    nt = len(times)    #Number of times.

    #Sanity check inputs for out of bounds...
    if (np.min(x[6:8])<=min_axis):
        if debug:
            print("Positional Variance Too Low...")
        return -practically_infinity
    if (x[8]<min_v_disp):
        if debug:
            print("Velocity Variance Too Low...")
        return -practically_infinity

    #Trace the cluster backwards forwards in time. For every timestep, we have value of 
    #xyzuvw for the cluster. Covariances are simply formed from the radius and dispersion - 
    #they are symmetrical
    
    #!!! THIS SHOULD USE THE TRACEBACK MODULE, AND IS A JOB FOR JONAH TO TRY !!!
    
    #Now loop through stars, and save the overlap integral for every star.
    overlaps = np.empty(ns)
    for i in range(ns):
        #!!! Check if the spatial overlap is significant. If it is, find the time of 
        #overlap and the parameters of the cluster treated as two groups at this time. !!!
        spatial_overlap_is_significant = False
        if spatial_overlap:
            #!!! the "group" parameters below need to be set !!!
            if use_swig:
                overlaps[i] = overlap.get_overlap(group_icov.flatten().tolist(),
                                              group_mn.flatten().tolist(),
                                              group_icov_det,
                                              Bs[i].flatten().tolist(),
                                              bs[i].flatten().tolist(),
                                              B_dets[i]) 
            else:
                overlaps[i] = compute_overlap(group_icov,group_mn,group_icov_det,Bs[i],bs[i],B_dets[i])
        lnprob += np.log(1 + overlaps[i]*x[11])

    if return_overlaps:
        return overlaps    
    
    return lnprob

def fit_one_group(star_params, init_mod=np.array([ -6.574, 66.560, 23.436, -1.327,-11.427, -6.527, \
    10.045, 10.319, 12.334,  0.762,  0.932,  0.735,  0.846, 20.589]),\
        nwalkers=100,nchain=1000,nburn=200, return_sampler=False,pool=None,\
        init_sdev = np.array([1,1,1,1,1,1,1,1,1,.01,.01,.01,.1,1]), background_density=2e-12, use_swig=True, \
        plotit=False):
    """Fit a single group, using a affine invariant Monte-Carlo Markov chain.
    
    Parameters
    ----------
    star_params: dict
        A dictionary of star parameters from read_stars. This should of course be a
        class, but it doesn't work with MPI etc as class instances are not 
        "pickleable"
        
    init_mod : array-like
        Initial mean of models used to fit the group. See lnprob_one_group for parameter definitions.

            

    nwalkers : int
        Number of walkers to characterise the parameter covariance matrix. Has to be
        at least 2 times the number of dimensions.
    
    nchain : int
        Number of elements in the chain. For characteristing a distribution near a 
        minimum, 1000 is a rough minimum number (giving ~10% uncertainties on 
        standard deviation estimates).
        
    nburn : int
        Number of burn in steps, before saving any chain output. If the beam acceptance
        fraction is too low (e.g. significantly lower in burn in than normal, e.g. 
        less than 0.1) then this has to be increased.
    
    Returns
    -------
    best_params: array-like
        The best set of group parameters.
    sampler: emcee.EmsembleSampler
        Returned if return_sampler=True
    """
    nparams = len(init_mod)
    #Set up the MCMC...
    ndim=nparams

    #Set an initial series of models
    p0 = [init_mod + (np.random.random(size=ndim) - 0.5)*init_sdev for i in range(nwalkers)]

    #NB we can't set e.g. "threads=4" because the function isn't "pickleable"
    sampler = emcee.EnsembleSampler(nwalkers, ndim, lnprob_one_group,pool=pool,args=[star_params,background_density,use_swig])

    #Burn in...
    pos, prob, state = sampler.run_mcmc(p0, nburn)
    print("Mean burn-in acceptance fraction: {0:.3f}"
                    .format(np.mean(sampler.acceptance_fraction)))

    sampler.reset()

    #Run...
    sampler.run_mcmc(pos, nchain)
    if plotit:
        plt.figure(1)
        plt.clf()
        plt.plot(sampler.lnprobability.T)
        plt.savefig("plots/lnprobability.eps")
        plt.pause(0.001)

    #Best Model
    best_ix = np.argmax(sampler.flatlnprobability)
    print('[' + ",".join(["{0:7.3f}".format(f) for f in sampler.flatchain[best_ix]]) + ']')
    overlaps = lnprob_one_group(sampler.flatchain[best_ix], star_params,return_overlaps=True,use_swig=use_swig)
    group_cov = lnprob_one_group(sampler.flatchain[best_ix], star_params,return_cov=True,use_swig=use_swig)
    np.sqrt(np.linalg.eigvalsh(group_cov[:3,:3]))
    ww = np.where(overlaps < background_density)[0]
    print("The following {0:d} stars are more likely not group members...".format(len(ww)))
    try:
        print(star_params['stars'][ww]['Name'])
    except:
       print(star_params['stars'][ww]['Name1'])

    print("Mean acceptance fraction: {0:.3f}"
                    .format(np.mean(sampler.acceptance_fraction)))

    if plotit:
        plt.figure(2)       
        plt.clf()         
        plt.hist(sampler.chain[:,:,-1].flatten(),20)
        plt.savefig("plots/distribution_of_ages.eps")
    
    #pdb.set_trace()
    if return_sampler:
        return sampler
    else:
        return sampler.flatchain[best_ix]

def lnprob_two_groups(x,star_params,use_swig=True,t_ix = 0,return_overlaps=False,\
    return_cov=False, min_axis=2.0,min_v_disp=0.5,debug=False, print_times=False):
    """Compute the log-likelihood for a fit to a group.

    The x variables are:
    xyzuvw (6), then xyz standard deviations (3), uvw_symmetrical_std (1), xyz_correlations (3)
    for both the association and the background 

    A 26th variable, if present, is the time at which the calculation is made. If not given, the
    calculation is made at a fixed time index t_ix.

    The probability of a model is the product of the probabilities
    overlaps of every star in the group. 

    Parameters
    ----------
    x : array-like
        The group parameters, which are...
        x[0] to x[5] : xyzuvw
        x[6] to x[8] : positional variances in x,y,z
        x[9]  : velocity dispersion (symmetrical for u,v,w)
        x[10] to x[12] :  correlations between x,y,z
        x[13] to x[18] : xyzuvw of background (BG)
        x[19] to x[21] : positional variances in x,y,z of BG
        x[22]  : velocity dispersion (symmetrical for u,v,w) of BG
        x[23] to x[25] :  correlations between x,y,z of BG
        x[26] : fraction of stars (0.0 - 1.0) in association
        x[27] : (optional) birth time of group in Myr. 

    t_ix : int
        Time index (in the past) where we are computing the probabilities.
    
    return_overlaps : bool  
        Return the overlaps (rather than the log probability)
    
    return_cov : bool
        Return the covariance (rather than the log probability)
    
    """
    t0=time.time()
    practically_infinity = np.inf#1e20
    
    ns = len(star_params['xyzuvw'])    #Number of stars

    #See if we have a time in Myr in the input vector, in which case we have
    #to interpolate in time. Otherwise, just choose a single time snapshot given 
    #by the input index t_ix.
    if len(x)>27:
        #If the input time is outside our range of traceback times, return
        #zero likelihood.
        if ( (x[27] < min(star_params['times'])) | (x[27] > max(star_params['times']))):
            return -np.inf 
        #Linearly interpolate in time to get bs and Bs
        bs, cov = interp_cov(x[27], star_params)  
        #WARNING: The next lines are slow, and should maybe be part of the overlap package,
        #if numpy isn't fast enough. They are slow because an inverse and a determinant
        #is computed for every star. 
        Bs     = np.linalg.inv(cov)
        B_dets = np.linalg.det(Bs)
        #pdb.set_trace()
    else:
        #Extract the time that we really care about.
        #The result is a (ns,6) array for bs, and (ns,6,6) array for Bs.
        bs     = star_params['xyzuvw'][:,t_ix]
        Bs     = star_params['xyzuvw_icov'][:,t_ix]
        B_dets = star_params['xyzuvw_icov_det'][:,t_ix]

    #Get the stars to be fitted to the background's data at time 0
    #pdb.set_trace()
    background_bs     = star_params['xyzuvw'][:,0]
    background_Bs     = star_params['xyzuvw_icov'][:,0]
    background_B_dets = star_params['xyzuvw_icov_det'][:,0]

    xpos,  y,  z,  u,  v,  w,  dx,  dy,  dz,  duvw,  xcorr,  ycorr,  zcorr, \
    xpos2, y2, z2, u2, v2, w2, dx2, dy2, dz2, duvw2, xcorr2, ycorr2, zcorr2, weight, t \
        = x 
    if not (2.0 < dx < 200.0 and 2.0 < dy < 200.0 and 2.0 < dz < 100.0 and 0.5 < duvw \
     and -1.0 < xcorr < 1.0 and -1.0 < ycorr < 1.0 and -1.0 < zcorr < 1.0 \
     and 10.0 < dx2 and 10.0 < dy2 and 10.0 < dz2 and 0.5 < duvw2 \
     and -1.0 < xcorr2 < 1.0 and -1.0 < ycorr2 < 1.0 and -1.0 < zcorr2 < 1.0 \
     and 0.0 < weight < 1.0 and 0.0 < t < 25.0):
        return -practically_infinity 

    if (t < 0.0):
        print("Time is negative...?")

    #Sanity check inputs for out of bounds. If so, return zero likelihood.
    if (np.min(x[6:9])<=min_axis):
        if debug:
            print("Positional Variance Too Low...")
        return -practically_infinity
    if (np.min(x[9])<min_v_disp):
        if debug:
            print("Velocity Variance Too Low...")
        return -practically_infinity
    if (np.max(np.abs(x[10:13])) >= 1):
        if debug:
            print("Correlations above 1...")
        return -practically_infinity       

    #Create the group_mn and group_cov from x. This looks a little tricky 
    #because we're inputting correlations rather than elements of the covariance
    #matrix.
    #https://en.wikipedia.org/wiki/Correlation_and_dependence
    x = np.array(x)
    group_mn = x[0:6]
    group_cov = np.eye( 6 )
    #Fill in correlations
    group_cov[np.tril_indices(3,-1)] = x[10:13]
    group_cov[np.triu_indices(3,1)] = x[10:13]
    #Convert correlation to covariance for position.
    for i in range(3):
        group_cov[i,:3] *= x[6:9]
        group_cov[:3,i] *= x[6:9]
    #Convert correlation to covariance for velocity.
    for i in range(3,6):
        group_cov[i,3:] *= x[9]
        group_cov[3:,i] *= x[9]

    bg_mn = x[13:19]
    bg_cov = np.eye( 6 )
    #Fill in correlations
    bg_cov[np.tril_indices(3,-1)] = x[23:26]
    bg_cov[np.triu_indices(3,1)] = x[23:26]
    #Convert correlation to covariance for position.
    for i in range(3):
        bg_cov[i,:3] *= x[19:22]
        bg_cov[:3,i] *= x[19:22]
    #Convert correlation to covariance for velocity.
    for i in range(3,6):
        bg_cov[i,3:] *= x[22]
        bg_cov[3:,i] *= x[22]


    #Allow this covariance matrix to be returned.
    if return_cov:
        return group_cov

    #Enforce some sanity check limits on prior...
    if (np.min(np.linalg.eigvalsh(group_cov[:3,:3])) < min_axis**2):
        if debug:
            print("Minimum positional covariance too small in one direction...")
        return -practically_infinity

    #Enforce some sanity check limits on prior...
    if (np.min(np.linalg.eigvalsh(bg_cov[:3,:3])) < min_axis**2):
        if debug:
            print("Minimum positional bg covariance too small in one direction...")
        return -practically_infinity

    #Invert the group covariance matrix and check for negative eigenvalues
    group_icov = np.linalg.inv(group_cov)
    group_icov_eig = np.linalg.eigvalsh(group_icov)
    if np.min(group_icov_eig) < 0:
        if debug:
            print("Numerical error in inverse covariance matrix!")
        return -practically_infinity
    group_icov_det = np.prod(group_icov_eig)

    #Invert the background covariance matrix and check for negative eigenvalues
    bg_icov = np.linalg.inv(bg_cov)
    bg_icov_eig = np.linalg.eigvalsh(bg_icov)
    if np.min(bg_icov_eig) < 0:
        if debug:
            print("Numerical error in bg inverse covariance matrix!")
        return -practically_infinity
    bg_icov_det = np.prod(bg_icov_eig)

    #Before starting, lets set the prior probability
    #Given the way we're sampling the covariance matrix, I'm
    #really not sure this is correct! But it is pretty close...
    #it looks almost like 1/(product of standard deviations).
    #See YangBerger1998
    lnprob=np.log(np.abs(group_icov_det)**3.5)
  
    t1=time.time()  
  
    #overlaps_start = time.clock()
    #Now loop through stars, and save the overlap integral for every star.
    overlaps = np.empty(ns)
    if use_swig:
        if (True):
            #pdb.set_trace()
            overlaps = overlap.get_overlaps(group_icov, group_mn, group_icov_det,
                                            Bs, bs, B_dets, ns)
            bg_overlaps = overlap.get_overlaps(bg_icov, bg_mn, bg_icov_det,
                                            background_Bs, background_bs, 
                                            background_B_dets, ns)
            #note 'ns' at end, see 'overlap.c' for documentation
            prob = weight*overlaps + (1.0 - weight)*bg_overlaps
            #lnprob = lnprob + np.sum(np.log(background_density + overlaps))
            lnprob = lnprob + np.sum(np.log(prob))
        else:
            print("oops, no code for no swig")
            return -practically_infinity
            for i in range(ns):
                overlaps[i] = overlap.get_overlap(group_icov,
                                                  group_mn,
                                                  group_icov_det,
                                                  Bs[i],
                                                  bs[i],
                                                  B_dets[i]) #&TC
                lnprob += np.log(background_density + overlaps[i])
    else:
        print("oops, no code for no swig")
        return -practically_infinity
        for i in range(ns):
            overlaps[i] = compute_overlap(group_icov,group_mn,group_icov_det,Bs[i],bs[i],B_dets[i])
            lnprob += np.log(background_density + overlaps[i])
    
    #print (time.clock() - overlaps_start)
    if print_times:
	print("{0:9.6f}, {1:9.6f}".format(time.time()-t1, t1-t0))

    if return_overlaps:
        return (overlaps, bg_overlaps)
    
    return lnprob

def fit_two_groups(star_params, init_mod,\
        nwalkers=100,nchain=1000,nburn=200, return_sampler=False,pool=None,\
        init_sdev = np.array([1,1,1,1,1,1,1,1,1,.01,.01,.01,.1,1]), use_swig=True, \
        plotit=False):
    """Fit two group, using a affine invariant Monte-Carlo Markov chain.
    
    Parameters
    ----------
    star_params: dict
        A dictionary of star parameters from read_stars. This should of course be a
        class, but it doesn't work with MPI etc as class instances are not 
        "pickleable"
        
    init_mod : array-like
        Initial mean of models used to fit the group. See lnprob_two_groups for parameter definitions.

    nwalkers : int
        Number of walkers to characterise the parameter covariance matrix. Has to be
        at least 2 times the number of dimensions.
    
    nchain : int
        Number of elements in the chain. For characteristing a distribution near a 
        minimum, 1000 is a rough minimum number (giving ~10% uncertainties on 
        standard deviation estimates).
        
    nburn : int
        Number of burn in steps, before saving any chain output. If the beam acceptance
        fraction is too low (e.g. significantly lower in burn in than normal, e.g. 
        less than 0.1) then this has to be increased.
    
    Returns
    -------
    best_params: array-like
        The best set of group parameters.
    sampler: emcee.EmsembleSampler
        Returned if return_sampler=True
    """
    nparams = len(init_mod)
    #Set up the MCMC...
    ndim=nparams

    #Set an initial series of models
    p0 = [init_mod + (np.random.random(size=ndim) - 0.5)*init_sdev for i in range(nwalkers)]

    #NB we can't set e.g. "threads=4" because the function isn't "pickleable"
    sampler = emcee.EnsembleSampler(nwalkers, ndim, lnprob_two_groups,pool=pool,args=[star_params,use_swig])

    #Burn in...
    pos, prob, state = sampler.run_mcmc(p0, nburn)
    print("Mean burn-in acceptance fraction: {0:.3f}"
                    .format(np.mean(sampler.acceptance_fraction)))

    sampler.reset()

    #Run...
    sampler.run_mcmc(pos, nchain)
    if plotit:
        plt.figure(1)
        plt.clf()
        plt.plot(sampler.lnprobability.T)
        plt.savefig("plots/lnprobability.eps")
        plt.pause(0.001)

    #Best Model
    best_ix = np.argmax(sampler.flatlnprobability)
    print('[' + ",".join(["{0:7.3f}".format(f) for f in sampler.flatchain[best_ix]]) + ']')
#    overlaps = lnprob_one_group(sampler.flatchain[best_ix], star_params,return_overlaps=True,use_swig=use_swig)
#    group_cov = lnprob_one_group(sampler.flatchain[best_ix], star_params,return_cov=True,use_swig=use_swig)
#    np.sqrt(np.linalg.eigvalsh(group_cov[:3,:3]))
#    ww = np.where(overlaps < background_density)[0]
#    print("The following {0:d} stars are more likely not group members...".format(len(ww)))
#    try:
#        print(star_params['stars'][ww]['Name'])
#    except:
#       print(star_params['stars'][ww]['Name1'])
#
    print("Mean acceptance fraction: {0:.3f}"
                    .format(np.mean(sampler.acceptance_fraction)))

    if plotit:
        plt.figure(2)       
        plt.clf()         
        plt.hist(sampler.chain[:,:,-1].flatten(),20)
        plt.savefig("plots/distribution_of_ages.eps")
    
    #pdb.set_trace()
    if return_sampler:
        return sampler
    else:
        return sampler.flatchain[best_ix]

def lnprob_three_groups(x,star_params,use_swig=True,return_overlaps=False,\
    return_cov=False, min_axis=2.0,min_v_disp=0.5,debug=False, print_times=False):
    """Compute the log-likelihood for a fit to a group.

    The x variables are:
    xyzuvw (6), then xyz standard deviations (3), uvw_symmetrical_std (1), xyz_correlations (3)
    for two groups and the background 

    A 43rd variable, if present, is the time at which the calculation is made. If not given, the
    calculation is made at a fixed time index t_ix.

    The probability of a model is the product of the probabilities
    overlaps of every star in the group. 
    
    &FLAG

    Parameters
    ----------
    x : array-like
        The group parameters, which are...
        GROUP 1:
        x[0] to x[5] : xyzuvw
        x[6] to x[8] : positional variances in x,y,z
        x[9]  : velocity dispersion (symmetrical for u,v,w)
        x[10] to x[12] :  correlations between x,y,z
        x[13] : birth time of group in Myr
        x[14] : fraction of stars in group 1
        GROUP 2:
        x[15] to x[20] : xyzuvw
        x[21] to x[23] : positional variances in x,y,z
        x[24]  : velocity dispersion (symmetrical for u,v,w)
        x[25] to x[27] :  correlations between x,y,z
        x[28] : birth time of group in Myr
        x[29] : fraction of stars in group 2
        BACKGROUND:
        x[30] to x[35] : xyzuvw of background (BG)
        x[36] to x[38] : positional variances in x,y,z of BG
        x[39]  : velocity dispersion (symmetrical for u,v,w) of BG
        x[40] to x[42] :  correlations between x,y,z of BG

    return_overlaps : bool  
        Return the overlaps (rather than the log probability)
    
    return_cov : bool
        Return the covariance (rather than the log probability)
    
    """
    t0=time.time()
    practically_infinity = np.inf#1e20
    
    ns = len(star_params['xyzuvw'])    #Number of stars

    # Interpolate for the each birth time of the groups
    #If the input time is outside our range of traceback times, return
    #zero likelihood.
    # GROUP 1:
    if ( (x[13] < min(star_params['times'])) | (x[13] > max(star_params['times']))):
        return -np.inf 
    #Linearly interpolate in time to get bs and Bs
    b1s, cov1 = interp_cov(x[13], star_params)  
    #WARNING: The next lines are slow, and should maybe be part of the overlap package,
    #if numpy isn't fast enough. They are slow because an inverse and a determinant
    #is computed for every star. 
    B1s     = np.linalg.inv(cov1)
    B1_dets = np.linalg.det(B1s)
    #pdb.set_trace()

    # GROUP 2:
    if ( (x[28] < min(star_params['times'])) | (x[28] > max(star_params['times']))):
        return -np.inf 
    #Linearly interpolate in time to get bs and Bs
    b2s, cov2 = interp_cov(x[28], star_params)  
    #WARNING: The next lines are slow, and should maybe be part of the overlap package,
    #if numpy isn't fast enough. They are slow because an inverse and a determinant
    #is computed for every star. 
    B2s     = np.linalg.inv(cov2)
    B2_dets = np.linalg.det(B2s)

    #Get the stars to be fitted to the background's data at time 0
    background_bs     = star_params['xyzuvw'][:,0]
    background_Bs     = star_params['xyzuvw_icov'][:,0]
    background_B_dets = star_params['xyzuvw_icov_det'][:,0]

    xpos,  y,  z,  u,  v,  w,  dx,  dy,  dz,  duvw,  xcorr,  ycorr,  zcorr, age1, weight1,\
    xpos2, y2, z2, u2, v2, w2, dx2, dy2, dz2, duvw2, xcorr2, ycorr2, zcorr2,age2, weight2,\
    xposBG, yBG, zBG, uBG, vBG, wBG, dxBG, dyBG, dzBG, duvwBG, xcorrBG, ycorrBG, zcorrBG\
         = x 

    #&FLAG
    if not (2.0 < dx < 200.0 and 2.0 < dy < 200.0 and 2.0 < dz < 100.0 and 0.5 < duvw \
     and -1.0 < xcorr < 1.0 and -1.0 < ycorr < 1.0 and -1.0 < zcorr < 1.0 \
     and 0.0 < age1 < 25.0 and 0.05 < weight1 < 0.9 \
     and 2.0 < dx2 < 200.0 and 2.0 < dy2 < 200.0 and 2.0 < dz2 < 200.0 and 0.5 < duvw2 \
     and -1.0 < xcorr2 < 1.0 and -1.0 < ycorr2 < 1.0 and -1.0 < zcorr2 < 1.0 \
     and age1 + 1.0 < age2 < 25.0 and 0.05 < weight2 < 0.9 \
     and 10.0 < dxBG and 10.0 < dyBG and 10.0 < dzBG and 0.5 < duvwBG \
     and -1.0 < xcorrBG < 1.0 and -1.0 < ycorrBG < 1.0 and -1.0 < zcorrBG < 1.0 \
     and weight1 + weight2 < 0.9):
        return -practically_infinity 

    #Create the group_mn and group_cov from x. This looks a little tricky 
    #because we're inputting correlations rather than elements of the covariance
    #matrix.
    #https://en.wikipedia.org/wiki/Correlation_and_dependence
    x = np.array(x)
    group1_mn = x[0:6]
    group1_cov = np.eye( 6 )
    #Fill in correlations
    group1_cov[np.tril_indices(3,-1)] = x[10:13]
    group1_cov[np.triu_indices(3,1)] = x[10:13]
    #Convert correlation to covariance for position.
    for i in range(3):
        group1_cov[i,:3] *= x[6:9]
        group1_cov[:3,i] *= x[6:9]
    #Convert correlation to covariance for velocity.
    for i in range(3,6):
        group1_cov[i,3:] *= x[9]
        group1_cov[3:,i] *= x[9]

    group2_mn = x[15:21]
    group2_cov = np.eye( 6 )
    #Fill in correlations
    group2_cov[np.tril_indices(3,-1)] = x[25:28]
    group2_cov[np.triu_indices(3,1)] = x[25:28]
    #Convert correlation to covariance for position.
    for i in range(3):
        group2_cov[i,:3] *= x[21:24]
        group2_cov[:3,i] *= x[21:24]
    #Convert correlation to covariance for velocity.
    for i in range(3,6):
        group2_cov[i,3:] *= x[24]
        group2_cov[3:,i] *= x[24]

    bg_mn = x[30:35]
    bg_cov = np.eye( 6 )
    #Fill in correlations
    bg_cov[np.tril_indices(3,-1)] = x[40:43]
    bg_cov[np.triu_indices(3,1)] = x[40:43]
    #Convert correlation to covariance for position.
    for i in range(3):
        bg_cov[i,:3] *= x[36:39]
        bg_cov[:3,i] *= x[36:39]
    #Convert correlation to covariance for velocity.
    for i in range(3,6):
        bg_cov[i,3:] *= x[39]
        bg_cov[3:,i] *= x[39]

    #Allow this covariance matrix to be returned.
    if return_cov:
        return group1_cov, group2_cov, bg_cov

    #Invert the group covariance matrix and check for negative eigenvalues
    group1_icov = np.linalg.inv(group2_cov)
    group1_icov_eig = np.linalg.eigvalsh(group1_icov)
    if np.min(group1_icov_eig) < 0:
        if debug:
            print("Numerical error in inverse covariance matrix!")
        return -practically_infinity
    group1_icov_det = np.prod(group1_icov_eig)

    group2_icov = np.linalg.inv(group2_cov)
    group2_icov_eig = np.linalg.eigvalsh(group2_icov)
    if np.min(group2_icov_eig) < 0:
        if debug:
            print("Numerical error in inverse covariance matrix!")
        return -practically_infinity
    group2_icov_det = np.prod(group2_icov_eig)

    #Invert the background covariance matrix and check for negative eigenvalues
    bg_icov = np.linalg.inv(bg_cov)
    bg_icov_eig = np.linalg.eigvalsh(bg_icov)
    if np.min(bg_icov_eig) < 0:
        if debug:
            print("Numerical error in bg inverse covariance matrix!")
        return -practically_infinity
    bg_icov_det = np.prod(bg_icov_eig)

    #Before starting, lets set the prior probability
    #Given the way we're sampling the covariance matrix, I'm
    #really not sure this is correct! But it is pretty close...
    #it looks almost like 1/(product of standard deviations).
    #See YangBerger1998
    lnprob=np.log(np.abs(group1_icov_det)**3.5) + np.log(np.abs(group2_icov_det)**3.5)
  
    t1=time.time()  
  
    #overlaps_start = time.clock()
    #Now loop through stars, and save the overlap integral for every star.
    #overlaps = np.empty(ns) #not needed I beleive...
    if use_swig:
        if (True):
            #&FLAG
            #pdb.set_trace()
            g1_overlaps = overlap.get_overlaps(group1_icov, group1_mn, group1_icov_det,
                                            B1s, b1s, B1_dets, ns)
            g2_overlaps = overlap.get_overlaps(group2_icov, group2_mn, group2_icov_det,
                                            B2s, b2s, B2_dets, ns)
            bg_overlaps = overlap.get_overlaps(bg_icov, bg_mn, bg_icov_det,
                                            background_Bs, background_bs, 
                                            background_B_dets, ns)
            #note 'ns' at end, see 'overlap.c' for documentation
            prob = weight1*g1_overlaps + weight2*g2_overlaps +\
                    (1.0 - weight1 - weight2)*bg_overlaps
            #lnprob = lnprob + np.sum(np.log(background_density + overlaps))
            lnprob = lnprob + np.sum(np.log(prob))
        else:
            print("oops, no code for no swig")
            return -practically_infinity
            for i in range(ns):
                overlaps[i] = overlap.get_overlap(group_icov,
                                                  group_mn,
                                                  group_icov_det,
                                                  Bs[i],
                                                  bs[i],
                                                  B_dets[i]) #&TC
                lnprob += np.log(background_density + overlaps[i])
    else:
        print("oops, no code for no swig")
        return -practically_infinity
        for i in range(ns):
            overlaps[i] = compute_overlap(group_icov,group_mn,group_icov_det,Bs[i],bs[i],B_dets[i])
            lnprob += np.log(background_density + overlaps[i])
    
    #print (time.clock() - overlaps_start)
    if print_times:
	print("{0:9.6f}, {1:9.6f}".format(time.time()-t1, t1-t0))

    if return_overlaps:
        return (g1_overlaps, g2_overlaps, bg_overlaps)
    
    return lnprob

# a dummy prior function required to suit syntax of PTSampler init
def logp(dummy):
    return 0

def fit_three_groups(star_params, init_mod,\
        nwalkers=100,nchain=1000,nburn=200, return_sampler=False,pool=None,\
        init_sdev=[], use_swig=True, \
        plotit=False):
    """Fit three groups, using a affine invariant Monte-Carlo Markov chain.
    
    Parameters
    ----------
    star_params: dict
        A dictionary of star parameters from read_stars. This should of course be a
        class, but it doesn't work with MPI etc as class instances are not 
        "pickleable"
        
    init_mod : array-like
        Initial mean of models used to fit the group. See lnprob_one_group for parameter definitions.

    nwalkers : int
        Number of walkers to characterise the parameter covariance matrix. Has to be
        at least 2 times the number of dimensions.
    
    nchain : int
        Number of elements in the chain. For characteristing a distribution near a 
        minimum, 1000 is a rough minimum number (giving ~10% uncertainties on 
        standard deviation estimates).
        
    nburn : int
        Number of burn in steps, before saving any chain output. If the beam acceptance
        fraction is too low (e.g. significantly lower in burn in than normal, e.g. 
        less than 0.1) then this has to be increased.
    
    Returns
    -------
    best_params: array-like
        The best set of group parameters.
    sampler: emcee.EmsembleSampler
        Returned if return_sampler=True
    """
    nparams = len(init_mod)
    #Set up the MCMC...
    ndim=nparams
    ntemps = 20

    #Set an initial series of models
    #p0 = [init_mod + (np.random.random(size=ndim) - 0.5)*init_sdev for i in range(nwalkers)]
    p0 = [[init_mod + (np.random.random(size=ndim) - 0.5)*init_sdev for i in range(nwalkers)] for j in range(ntemps)]

    #&FLAG 
    #NB we can't set e.g. "threads=4" because the function isn't "pickleable"
    #sampler = emcee.EnsembleSampler(nwalkers, ndim, lnprob_three_groups,pool=pool,args=[star_params,use_swig])
    sampler = emcee.PTSampler(ntemps, nwalkers, ndim, lnprob_three_groups, logp, pool=pool,loglargs=[star_params,use_swig])

    #Burn in...
    pos, prob, state = sampler.run_mcmc(p0, nburn)
    print("Mean burn-in acceptance fraction: {0:.3f}"
                    .format(np.mean(sampler.acceptance_fraction)))

    sampler.reset()

    #Run...
    sampler.run_mcmc(pos, nchain)

    assert sampler.chain.shape == (ntemps, nwalkers, nchain, ndim)
    #pdb.set_trace()
    if plotit:
        plt.figure(1)
        plt.clf()
        plt.plot(sampler.lnprobability.T)
        plt.savefig("plots/lnprobability.eps")
        plt.pause(0.001)

    #Best Model
    #best_ix = np.argmax(sampler.flatlnprobability)
    #print('[' + ",".join(["{0:7.3f}".format(f) for f in sampler.flatchain[best_ix]]) + ']')
    print("Mean acceptance fraction: {0:.3f}"
                    .format(np.mean(sampler.acceptance_fraction)))

    if plotit:
        plt.figure(2)       
        plt.clf()         
        plt.hist(sampler.chain[:,:,-1].flatten(),20)
        plt.savefig("plots/distribution_of_ages.eps")
    
    #pdb.set_trace()
    return sampler

    #skipping this for now
    if return_sampler:
        return sampler
    else:
        return sampler.flatchain[best_ix]
 

 #Some test calculations applicable to the ARC DP17 proposal.
if __name__ == "__main__":
    star_params = read_stars("traceback_save.pkl")
    
    using_mpi = True
    try:
        # Initialize the MPI-based pool used for parallelization.
        pool = MPIPool()
    except:
        print("MPI doesn't seem to be installed... maybe install it?")
        using_mpi = False
        pool=None
    
    if using_mpi:
        if not pool.is_master():
            # Wait for instructions from the master process.
            pool.wait()
            sys.exit(0)
        else:
            print("MPI available! - call this with e.g. mpirun -np 4 python fit_group.py")
    
    beta_pic_group = np.array([-6.574, 66.560, 23.436, -1.327,-11.427, -6.527,\
        10.045, 10.319, 12.334,  0.762,  0.932,  0.735,  0.846, 20.589])
    plei_group = np.array([116.0,27.6, -27.6, 4.7, -23.1, -13.2, 20, 20, 20,\
                        3, 0, 0, 0, 70])

    dummy = lnprob_one_group(beta_pic_group, star_params, use_swig=True)
#    dummy = lnprob_one_group(plei_group, star_params, background_density=1e-10, use_swig=False)
        
    fitted_params = fit_one_group(star_params, pool=pool, use_swig=True)
    
    if using_mpi:
        # Close the processes.
        pool.close()
