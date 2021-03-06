"""
compfitter.py
Fit a single component to a set of stellar 6D phase-space data, along
with an optional membership probability array. The fitting uses a
monte carlo markov chain approach (emcee by Dan Foreman-Mackay(?))
to explore the parameter space of the model.
The default model is SphereComponent, which is a Gaussain distribution,
spherical in position and spherical in velocity. Alternative models can
be used by writing a new Component class that extends AbstractComponent,
and passing the class to the Component argument.
Main entry point is `fit_comp`.
"""
from __future__ import division, print_function

import numpy as np

# from astropy.table import Table
import emcee
import logging
import os
import multiprocessing
import scipy.optimize
import itertools

from . import likelihood
from . import tabletool
from . import component
from .component import SphereComponent
from .component import EllipComponent
#~ SphereComponent = component.SphereComponent
#~ from .component import SphereComponent


try:
    import matplotlib.pyplot as plt
    plt_avail = True
except ImportError:
    plt_avail = False


def calc_med_and_span(chain, perc=34, intern_to_extern=False,
                      Component=SphereComponent):
    """
    Given a set of aligned samples, calculate the 50th, (50-perc)th and
     (50+perc)th percentiles.
    Parameters
    ----------
    chain : [nwalkers, nsteps, npars] array -or- [nwalkers*nsteps, npars] array
        The chain of samples (in internal encoding)
    perc: integer {34}
        The percentage from the midpoint you wish to set as the error.
        The default is to take the 16th and 84th percentile.
    intern_to_extern : boolean {False}
        Set to true if chain has dx and dv provided in log form and output
        is desired to have dx and dv in linear form
    Component : Subclass of AbstractComponent
        The class used in the fitting process. This class's static methods
        are used to interpret
    Returns
    -------
    result : [npars,3] float array
        For each parameter, there is the 50th, (50+perc)th and (50-perc)th
        percentiles
    """
    npars = chain.shape[-1]  # will now also work on flatchain as input
    flat_chain = np.reshape(chain, (-1, npars))

    if intern_to_extern:
        # Externalise each sample
        for ix in range(flat_chain.shape[0]):
            flat_chain = np.copy(flat_chain)
            flat_chain[ix] = Component.externalise(flat_chain[ix])

    return np.array(list(map(lambda v: (v[1], v[2], v[0]),
                            zip(*np.percentile(flat_chain,
                                               [50-perc, 50, 50+perc],
                                               axis=0)))))


def stuck_walker(walker_lnprob, max_repeat=500):
    """
    Check if a walker is stuck by analysing its lnprob values across
    its whole walk.
    Notes
    -----
    A stuck walker is defined to be one which has not changed it's value
    after (say) 100 steps. To simplify, we don't check for contiguous blocks,
    but rather just examine the occurence of each unique lnprob in the walk
    as it is unlikely a walker will reach the identical lnprob unless it
    was stuck there.
    """
    unique_elements, counts_elements = np.unique(walker_lnprob,
                                                 return_counts=True)
    return np.max(counts_elements) > max_repeat


def no_stuck_walkers(lnprob):
    """
    Examines lnprob to see if any walkers have flatlined far from pack.
    Good walkers are True, stuck walkers are False.
    Parameters
    ----------
    lnprob: [nwalkers,nsteps] array_like
        A record of the log probability of each sample from an emcee run
    Returns
    -------
    res: boolean
        True if no walkers have flat-lined far from the pack
    stuck_walker_checks: [boolean]
        List of boolean values for all the walkers
    """

    stuck_walker_checks = []
    for walker_lnprob in lnprob:
        stuck_walker_checks.append(stuck_walker(walker_lnprob))

    res = not np.any(stuck_walker_checks)
    logging.info("No stuck walkers? {}".format(res))
    return res, [not x for x in stuck_walker_checks]


def burnin_convergence(lnprob, tol=0.25, slice_size=100, cutoff=0, debug=False):
    """Checks early lnprob vals with final lnprob vals for convergence
    Takes the first `slice_size` and the final `slice_size` lnprob values.
    Chain is deemed converged if the mean of these two slices are within
    0.25 sigma of each other, where sigma is the standard deviation
    of the final slice.
    Parameters
    ----------
    lnprob : [nwalkers, nsteps] array
    tol : float
        The number of standard deviations the final mean lnprob should be
        within of the initial mean lnprob
    slice_size : int
        Number of steps at each end to use for mean lnprob calcultions
    Returns
    -------
    res: bool
        True iff mean of walkers varies a negligible amount and no walkers
        have flatlined
    """
    # take a chunk the smaller of 100 or half the chain
    if lnprob.shape[1] < 2*slice_size:
        logging.info("Burnin length {} too small for reliable convergence"
                     "checking".\
                     format(lnprob.shape[1]))
        slice_size = int(round(0.5*lnprob.shape[1]))

    start_lnprob_mn = np.mean(lnprob[:,:slice_size])
    #start_lnprob_std = np.std(lnprob[:,:slice_size])

    end_lnprob_mn = np.mean(lnprob[:, -slice_size:])
    end_lnprob_std = np.std(lnprob[:, -slice_size:])

    stable = np.isclose(start_lnprob_mn, end_lnprob_mn,
                        rtol=1e-10,                     # only care about atol
                        atol=tol*end_lnprob_std)
    logging.info("Stable? {}".format(stable))
    if debug:
        import pdb; pdb.set_trace()

    return stable


def get_init_emcee_pos(data, memb_probs=None, nwalkers=None,
                       init_pars=None, Component=SphereComponent):
    """
    Get the initial position of emcee walkers
    This can use an initial sample (`init_pars`) around which to scatter
    walkers, or can infer a sensible initial fit based on the data, and
    initialise walkers around the best corresponding parameter list.
    Parameters
    ----------
    data: dict
        See fit_comp
    memb_probs: [nstars] float array_like {None}
        See fit_comp
        If none, treated as np.ones(nstars)
    nwalkers: int {None}
        Number of walkers to be used by emcee
    init_pars: [npars] array_like {None}
        An initial model around which to initialise walkers
    Component:
        See fit_comp
    Returns
    -------
    init_pos: [nwalkers, npars] array_like
        The starting positions of emcee walkers
    """
    if init_pars is None:
        rough_mean_now, rough_cov_now = \
            Component.approx_currentday_distribution(data=data,
                                           membership_probs=memb_probs)
        # Exploit the component logic to generate closest set of pars
        dummy_comp = Component(attributes={'mean':rough_mean_now,
                                           'covmatrix':rough_cov_now,})
        init_pars = dummy_comp.get_emcee_pars()

    init_std = Component.get_sensible_walker_spread()

    # Generate initial positions of all walkers by adding some random
    # offset to `init_pars`
    if nwalkers is None:
        npars = len(init_pars)
        nwalkers = 2 * npars
    init_pos = emcee.utils.sample_ball(init_pars, init_std,
                                       size=nwalkers)
    # force ages to be positive
    init_pos[:, -1] = abs(init_pos[:, -1])

    # In the case of Neelesh ellipcompnent, force dx > dy and du > dv
    if Component == EllipComponent \
            or (Component.COMPONENT_NAME == 'EllipticalComponent'):
        import pdb; pdb.set_trace()
        for emcee_pars in init_pos:
            ext_pars = Component.externalise(emcee_pars)
            if ext_pars[7] > ext_pars[6]:
                ext_pars[6], ext_pars[7] = ext_pars[7], ext_pars[6]
            if ext_pars[9] > ext_pars[8]:
                ext_pars[8], ext_pars[9] = ext_pars[9], ext_pars[8]
            emcee_pars[:] = Component.internalise(ext_pars)

    return init_pos


def get_best_component(chain, lnprob, Component=SphereComponent):
    """
    Simple tool to extract the sample that yielded the highest log prob
    and return the corresponding Component object
    Parameters
    ----------
    chain: [nwalkers, nsteps, npars] float array --or-- file name
        The chain of walkers from which the best component parameters
        will be extracted
    lnprob:  [nwalkers, nsteps] float array --or-- file name
        The log probabilities of each walker at each step.
    Component: Component Class {SphereComponent}
        An implmentation of chronostar.component.AbstractComponent
    Returns
    -------
    component: Component object
        The component object corresponding to the highest lnprob score
    """
    if type(chain) is str:
        chain = np.load(chain)
    if type(lnprob) is str:
        lnprob = np.load(lnprob)

    # Identify the best component
    final_best_ix = np.argmax(lnprob)

    # If chain hasn't been flattened, then flatten, preserving only the
    # last dimension
    if len(chain.shape) == 3:
        chain = chain.reshape(-1, chain.shape[-1])

    best_sample = chain[final_best_ix]
    best_component = Component(emcee_pars=best_sample)
    return best_component


def fit_comp(data, memb_probs=None, init_pos=None, init_pars=None,
             burnin_steps=1000, Component=SphereComponent, plot_it=False,
             pool=None, convergence_tol=0.25, plot_dir='', save_dir='',
             sampling_steps=None, max_iter=None, trace_orbit_func=None,
             store_burnin_chains=False, nthreads=1,
             optimisation_method='emcee', nprocess_ncomp=False):
    """Fits a single 6D gaussian to a weighted set (by membership
    probabilities) of stellar phase-space positions.
    Stores the final sampling chain and lnprob in `save_dir`, but also
    returns the best fit (walker step corresponding to maximum lnprob),
    sampling chain and lnprob.
    If neither init_pos nor init_pars are provided, then the weighted
    mean and covariance of the provided data set are calculated, then
    used to generate a sample parameter list (using Component). Walkers
    are then initialised around this parameter list.
    Parameters
    ----------
    data: dict -or- astropy.table.Table -or- path to astrop.table.Table
        if dict, should have following structure:
            'means': [nstars,6] float array_like
                the central estimates of star phase-space properties
            'covs': [nstars,6,6] float array_like
                the phase-space covariance matrices of stars
            'bg_lnols': [nstars] float array_like (opt.)
                the log overlaps of stars with whatever pdf describes
                the background distribution of stars.
        if table, see tabletool.build_data_dict_from_table to see
        table requirements.
    memb_probs: [nstars] float array_like
        Membership probability (from 0.0 to 1.0) for each star to the
        component being fitted.
    init_pos: [ngroups, npars] array
        The precise locations at which to initiate the walkers. Generally
        the saved locations from a previous, yet similar run.
    init_pars: [npars] array
        the position in parameter space about which walkers should be
        initialised. The standard deviation about each parameter is
        hardcoded as INIT_SDEV
    burnin_steps: int {1000}
        Number of steps per each burnin iteration
    Component: Class implementation of component.AbstractComponent {Sphere Component}
        A class that can read in `pars`, and generate the three key
        attributes for the modelled origin point:
        mean, covariance matrix, age
        As well as get_current_day_projection()
        See AbstractComponent to see which methods must be implemented
        for a new model.
    plot_it: bool {False}
        Whether to generate plots of the lnprob in 'plot_dir'
    pool: MPIPool object {None}
        pool of threads to execute walker steps concurrently
    convergence_tol: float {0.25}
        How many standard deviations an lnprob chain is allowed to vary
        from its mean over the course of a burnin stage and still be
        considered "converged". Default value allows the median of the
        final 20 steps to differ by 0.25 of its standard deviations from
        the median of the first 20 steps.
    plot_dir: str {''}
        The directory in which to store plots
    save_dir: str {''}
        The directory in which to store results and/or byproducts of fit
    sampling_steps: int {None}
        If this is set, after convergence, a sampling stage will be
        entered. Only do this if a very fine map of the parameter
        distributions is required, since the burnin stage already
        characterises a converged solution for "burnin_steps".
    max_iter: int {None}
        The maximum iterations permitted to run. (Useful for expectation
        maximisation implementation triggering an abandonment of rubbish
        components). If left as None, then run will continue until
        convergence.
    trace_orbit_func: function {None}
        A function to trace cartesian oribts through the Galactic potential.
        If left as None, will use traceorbit.trace_cartesian_orbit (base
        signature of any alternate function on this ones)
    optimisation_method: str {'emcee'}
        Optimisation method to be used in the maximisation step to fit
        the model. Default: emcee. Available: scipy.optimise.minimize with
        the Nelder-Mead method. Note that in case of the gradient descent,
        no chain is returned and meds and spans cannot be determined.
    nprocess_ncomp: bool {False}
        Compute maximisation in parallel? This is relevant only in case
        Nelder-Mead method is used: This method computes optimisation
        many times with different initial positions. The result is the
        one with the best likelihood. These optimisations are computed
        in parallel if nprocess_ncomp equals True.

    Returns
    -------
    best_component
        The component model which yielded the highest posterior probability
    chain
        [nwalkers, nsteps, npars] array of all samples
    probability
        [nwalkers, nsteps] array of probabilities for each sample
    """
    # TIDYING INPUT
    if not isinstance(data, dict):
        data = tabletool.build_data_dict_from_table(data)
    if memb_probs is None:
        memb_probs = np.ones(len(data['means']))
    # Ensure plot_dir has a single trailing '/'
    if plot_dir != '':
        plot_dir = plot_dir.rstrip('/') + '/'
    if plot_it and plot_dir != '':
        if not os.path.exists(plot_dir):
            os.mkdir(plot_dir)
    npars = len(Component.PARAMETER_FORMAT)
    nwalkers = 2*npars

    #########################################
    ### OPTIMISE WITH EMCEE #################
    if optimisation_method=='emcee':

        # Initialise the emcee sampler
        if init_pos is None:
            init_pos = get_init_emcee_pos(data=data, memb_probs=memb_probs,
                                          init_pars=init_pars, Component=Component,
                                          nwalkers=nwalkers)

        # MZ: What does this line do?
        # TC: hacky (probs broken) way of forcing spawned threads to not be
        # stuck on the same cpu. TC faced some issues when trying to do multithreading
        # on mash. Maybe MZ will have better luck :P
        # os.system("taskset -p 0xff %d >> /dev/null" % os.getpid())

        sampler = emcee.EnsembleSampler(
                nwalkers, npars, likelihood.lnprob_func,
                args=[data, memb_probs, trace_orbit_func, optimisation_method, Component],
                pool=pool,
                threads=nthreads,
        )

        # PERFORM BURN IN
        state = None
        converged = False
        cnt = 0
        logging.info("Beginning burnin loop")
        burnin_lnprob_res = np.zeros((nwalkers,0))

        # burn in until converged or the (optional) max_iter is reached
        while (not converged) and cnt != max_iter:
            logging.info("Burning in cnt: {}".format(cnt))
            sampler.reset()
            init_pos, lnprob, state = sampler.run_mcmc(init_pos, burnin_steps)
            np.save(plot_dir+'lnprob_last.npy', sampler.lnprobability)
            stable = burnin_convergence(sampler.lnprobability, tol=convergence_tol)
            no_stuck, stuck_walker_checks = no_stuck_walkers(sampler.lnprobability)

            # For debugging cases where walkers have stabilised but apparently some are stuck
            if (stable and not no_stuck) or store_burnin_chains:
                np.save(plot_dir+'burnin_lnprob{:02}.npy'.format(cnt), sampler.lnprobability)
                np.save(plot_dir+'burnin_chain{:02}.npy'.format(cnt), sampler.chain)
                logging.info('Lnprob and chain saved')
            print("Not stuck and stable")
            print(no_stuck)
            print(stable)
            converged = stable and no_stuck
            logging.info("Burnin status: {}".format(converged))

            if plot_it and plt_avail:
                plt.clf()
                plt.plot(sampler.lnprobability.T)
                plt.savefig(plot_dir+"burnin_lnprobT{:02}.png".format(cnt))

            # If about to burnin again, help out the struggling walkers by shifting
            # them to the best walker's position
            if not converged:
                lnprob_not_stuck = lnprob[stuck_walker_checks]
                best_ix = np.argmax(lnprob_not_stuck)

                # Walkers with poor lnprob
                poor_ixs = np.where(lnprob_not_stuck < np.percentile(lnprob_not_stuck, 33))
                poor_ixs = list(poor_ixs)

                # Add stuck walkers
                ixs = np.where(~np.array(stuck_walker_checks))
                ixs = list(ixs)
                poor_ixs.extend(ixs)

                # Add walkers with NaNs
                #poor_ixs.extend(np.argwhere(np.isnan(     AAAAAA      )).flatten())

                poor_ixs = list(itertools.chain(*poor_ixs))
                print(poor_ixs)

                for ix in set(poor_ixs):
                    init_pos[ix] = init_pos[best_ix]

            burnin_lnprob_res = np.hstack((
                burnin_lnprob_res, sampler.lnprobability
            ))
            cnt += 1

        logging.info("Burnt in, with convergence: {}".format(converged))
        if plot_it and plt_avail:
            plt.clf()
            plt.plot(burnin_lnprob_res.T)
            plt.savefig(plot_dir+"burnin_lnprobT.png")

        # SAMPLING STAGE
        if not sampling_steps:
            logging.info("Taking final burnin segment as sampling stage"\
                         .format(converged))
        else:
            logging.info("Entering sampling stage for {} steps".format(
                sampling_steps
            ))
            sampler.reset()
            # Don't need to keep track of any outputs
            #~ sampler.run_mcmc(init_pos, sampling_steps, state)
            sampler.run_mcmc(init_pos, sampling_steps)
            logging.info("Sampling done")

        # save the chain for later inspection
        np.save(save_dir+"final_chain.npy", sampler.chain)
        np.save(save_dir+"final_lnprob.npy", sampler.lnprobability)

        if plot_it and plt_avail:
            logging.info("Plotting final lnprob")
            plt.clf()
            plt.plot(sampler.lnprobability.T)
            plt.savefig(plot_dir+"lnprobT.png")
            logging.info("Plotting done")

        # Identify the best component
        best_component = get_best_component(sampler.chain, sampler.lnprobability, Component=Component)

        # Determining the median and span of each parameter
        med_and_span = calc_med_and_span(sampler.chain, Component=Component)
        logging.info("Results:\n{}".format(med_and_span))

        return best_component, sampler.chain, sampler.lnprobability


    #########################################
    ### OPTIMISE WITH GRADIENT DESCENT ######
    elif optimisation_method=='Nelder-Mead':
        """
        Run optimisation multiple times and select result with the
        best lnprob value as the best. Reason is that Nelder-Mead method
        turned out not to be robust enough so we need to run optimisation
        with a few different starting points. 
        
        scipy.optimize.minimize is using -likelihood.lnprob_func because
        it is minimizing rather than optimizing.
        """
        # Initialise the initial positions (use emcee because
        # this works in this case just well).
        init_pos = get_init_emcee_pos(data=data, memb_probs=memb_probs,
                                          init_pars=init_pars, Component=Component,
                                          nwalkers=nwalkers)

        if nprocess_ncomp:
            """
            This is done in parallel with the nwalker processes.
            """

            manager = multiprocessing.Manager()
            return_dict = manager.dict()

            def worker(pos, return_dict):
                result = scipy.optimize.minimize(likelihood.lnprob_func, pos, args=[data, memb_probs, trace_orbit_func, optimisation_method], tol=0.01, method=optimisation_method)
                return_dict[result.fun] = result
            #TODO: tol: is this value optimal?


            jobs = []
            for i in range(nwalkers):
                process = multiprocessing.Process(target=worker, args=(init_pos[i], return_dict))
                jobs.append(process)

            # Start the processes
            for j in jobs:
                j.start()

            # Ensure all of the processes have finished
            for j in jobs:
                j.join()

        else:
            """
            Compute optimisations in a for loop. This is slow.
            """
            return_dict=dict()
            for pos in init_pos:
                result = scipy.optimize.minimize(likelihood.lnprob_func, pos, args=[data, memb_probs, trace_orbit_func, optimisation_method, Component], tol=0.01, method=optimisation_method)
                return_dict[result.fun] = result


        # Select the best result. Keys are lnprob values.
        keys = return_dict.keys()
        key = np.nanmin(keys)
        best_result = return_dict[key]

        # Identify and create the best component (with best lnprob)
        best_component = Component(emcee_pars=best_result.x)

        return best_component, best_result.x, -best_result.fun