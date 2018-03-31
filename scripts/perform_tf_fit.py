#! /usr/bin/env python
from __future__ import division, print_function

from distutils.dir_util import mkpath
import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import pickle
import sys

base_group_pars = [
    -80, 80, 50, 10, -20, -5, None, None, None, None,
    0.0, 0.0, 0.0, None, None
]
perf_data_file = "perf_xyzuvw"
prec_val = {'perf': 1e-5, 'half':0.5, 'gaia': 1.0, 'double': 2.0}


BURNIN_STEPS = 300
if __name__ == '__main__':

    logging.basicConfig(
        level=logging.DEBUG, filemode='w',
        filename='my_investigator_demo.log',
    )
    age, dX, dV = np.array(sys.argv[1:4], dtype=np.double)
    nstars = int(sys.argv[4])
    precs = sys.argv[5:-1]
    package_path = sys.argv[-1]

    # since this could be being executed anywhere, need to pass in package location
    sys.path.insert(0, package_path)
    try:
        import chronostar.synthesiser as syn
        import chronostar.traceback as tb
        import chronostar.tfgroupfitter as tfgf
        import chronostar.error_ellipse as ee
        import chronostar.transform as tf
        from chronostar import utils
    except ImportError:
        logging.info("Failed to import chronostar package")
        raise

    logging.info("Input arguments: {}".format(sys.argv[1:]))

    logging.info("\n"
                 "\tage:     {}\n"
                 "\tdX:      {}\n"
                 "\tdV:      {}\n"
                 "\tnstars:  {}\n"
                 "\tprecs:   {}".format(
        age, dX, dV, nstars, precs,
    ))

    group_pars_ex = list(base_group_pars)
    group_pars_ex[6:9] = [dX, dX, dX]
    group_pars_ex[9] = dV
    group_pars_ex[13] = age
    group_pars_ex[14] = nstars

    # synthesise perfect XYZUVW data
    perf_xyzuvws, _ = syn.generate_current_pos(1, group_pars_ex)
    np.save(perf_data_file, perf_xyzuvws)

    for prec in precs:
        # make new directory
        mkpath(prec)
        # change into directory
        os.chdir(prec)
        # convert XYZUVW data into astrometry
        sky_coord_now = syn.measure_stars(perf_xyzuvws)
        synth_table = syn.generate_table_with_error(
            sky_coord_now, prec_val[prec]
        )
        astr_file = "astr_data"
        pickle.dump(synth_table, open(astr_file, 'w'))
        # convert astrometry back into XYZUVW data
        tb_file = "tb_data.pkl"
        tb.traceback(synth_table, np.array([0,1]), savefile=tb_file)
        # apply traceforward fitting (with lnprob, corner plots as side effects)
        best_fit, chain, lnprob = tfgf.fit_group(
            tb_file, burnin_steps=BURNIN_STEPS, plot_it=True
        )
        # save and store result
        result_file = "result.npy"
        np.save(result_file, [best_fit, chain, lnprob])

        # plot Hex plot
        star_pars = tfgf.read_stars(tb_file=tb_file)
        xyzuvw = star_pars['xyzuvw'][:,0]
        xyzuvw_cov = star_pars['xyzuvw_cov'][:,0]

        # calculating all the relevant covariance matrices
        then_cov_true = utils.generate_cov(utils.internalise_pars(
            group_pars_ex
        ))

        dXav = (np.prod(np.linalg.eigvals(then_cov_true[:3, :3])) ** (1. / 6.))

        # This represents the target result - a simplified, spherical
        # starting point
        group_pars_tf_style = \
            np.append(
                np.append(
                    np.append(np.copy(group_pars_ex)[:6], dXav), dV
                ), age
            )
        group_pars_in = np.copy(group_pars_tf_style)
        group_pars_in[6:8] = 1 / group_pars_in[6:8]

        then_cov_true = utils.generate_cov(
            utils.internalise_pars(group_pars_ex))
        then_cov_simple = tfgf.generate_cov(group_pars_in)
        then_cov_fitted = tfgf.generate_cov(best_fit)
        now_cov_fitted = tf.transform_cov(then_cov_fitted, tb.trace_forward,
                                          best_fit[0:6], dim=6,
                                          args=(best_fit[-1],))
        now_mean_fitted = tb.trace_forward(best_fit[:6], best_fit[-1])

        plt.clf()
        plt.plot(xyzuvw[:, 0], xyzuvw[:, 1], 'b.')
        ee.plot_cov_ellipse(then_cov_simple[:2, :2], group_pars_tf_style[:2],
                            color='orange',
                            alpha=0.2, hatch='|', ls='--')
        ee.plot_cov_ellipse(then_cov_true[:2, :2], group_pars_tf_style[:2],
                            color='orange',
                            alpha=1, ls=':', fill=False)
        ee.plot_cov_ellipse(then_cov_fitted[:2, :2], best_fit[:2],
                            color='xkcd:neon purple',
                            alpha=0.2, hatch='/', ls='-.')
        ee.plot_cov_ellipse(now_cov_fitted[:2, :2], now_mean_fitted[:2],
                            color='b',
                            alpha=0.03, hatch='.')

        buffer = 30
        xmin = min(group_pars_tf_style[0], best_fit[0], now_mean_fitted[0], *xyzuvw[:,0])
        xmax = max(group_pars_tf_style[0], best_fit[0], now_mean_fitted[0], *xyzuvw[:,0])
        ymin = min(group_pars_tf_style[1], best_fit[1], now_mean_fitted[1], *xyzuvw[:,1])
        ymax = max(group_pars_tf_style[1], best_fit[1], now_mean_fitted[1], *xyzuvw[:,1])
        plt.xlim(xmax + buffer, xmin - buffer)
        plt.ylim(ymin - buffer, ymax + buffer)
        plt.savefig("hex_plot.png")

        # return to main directory
        os.chdir('..')

