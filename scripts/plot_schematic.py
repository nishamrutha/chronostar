from __future__ import print_function, division
"""Generate a diagram detailing model fitting approach"""

import itertools
import numpy as np
import matplotlib.pyplot as plt
import sys
sys.path.insert(0, '..')
import chronostar.synthesiser as syn
import chronostar.traceorbit as torb
import chronostar.measurer as ms
import chronostar.converter as cv
import chronostar.fitplotter as fp

pdir = "../figures/paper1/"
ERROR = 1.0

# set X to be really large to encourage significant errors
origin_pars = np.array([50., 0., -50., 0., 10., 0., 10., 0.5, 10., 100])

xyzuvw_init, origin = syn.synthesiseXYZUVW(origin_pars, sphere=True,
                                           return_group=True,
                                           internal=False)
xyzuvw_now_perf = torb.traceManyOrbitXYZUVW(xyzuvw_init,
                                            times=origin.age,
                                            single_age=True)
astr_table = ms.measureXYZUVW(xyzuvw_now_perf, ERROR)
star_pars = cv.convertMeasurementsToCartesian(astr_table)


dims = 'XYZUVW'
plt.clf()
fp.plot1DProjection(0, star_pars, [origin], np.array([origin.nstars]))
plt.savefig(pdir + "1dprojection.pdf")
plt.clf()
dim1, dim2 = 'xu'
fp.plotPane(dim1, dim2, groups=origin, star_pars=star_pars,
            group_then=True, group_now=True, group_orbit=True,
            annotate=True)
plt.savefig(pdir + "only_schematic.pdf")

plt.clf()
dim1 = 0
dim2 = 3
fp.plotPaneWithHists(dim1, dim2, groups=[origin], star_pars=star_pars,group_then=True,
                     group_now=True,group_orbit=True, annotate=True)
plt.savefig(pdir + 'flanking_plots.pdf')
#
# # For each combination, plot an annotated schematic of a single component
# for i, dim1 in enumerate(dims):
#     for dim2 in dims[i+1:]:
#         plt.clf()
#         ax = plt.subplot()
#         print(dim1, dim2)
#         ax.set_title("{} and {}".format(dim1, dim2))
#         fp.plotPane(dim1, dim2, ax=ax, groups=origin, star_pars=star_pars,
#                     group_then=True, group_now=True, group_orbit=True,
#                     annotate=True)
#         plt.savefig(pdir + "schematic-{}{}.pdf".format(dim1, dim2),
#                     bbox_inches='tight')
#
# # Just some fun... every possible pair on the one plot
# dim_pairs = list(itertools.combinations(dims, 2))
# fp.plotMultiPane(dim_pairs, star_pars, origin, save_file=pdir + 'all.pdf')
#
