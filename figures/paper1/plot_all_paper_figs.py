from __future__ import print_function, division

"""
A script which gathers all plotting of all relevant figures into
one spot to facilitate quick and simple replotting as needed.

TODO: Maybe do again, but with the range buffer lowered to 0.1 (from 0.2)
"""

import matplotlib.pyplot as plt
import numpy as np
import sys
sys.path.insert(0, '../..')

import chronostar.datatool as dt
import chronostar.synthesiser as syn
import chronostar.fitplotter as fp
import chronostar.traceorbit as torb

debugging_circles=False

# PLOTTING FLAGS
# PLOT_FED_STARS = False
PLOT_FED_STARS = True
PLOT_MUTLI_SYNTH = False
# PLOT_MUTLI_SYNTH = True
PLOT_BPMG_REAL = False
# PLOT_BPMG_REAL = True
PLOT_FAILURE = False

DEFAULT_DIMS = ((0,1), (0,3), (1,4), (2,5))
COLOR_LABELS = ['Fitted {}'.format(ch) for ch in 'ABCDEF']

acronyms = {
    'beta Pictoris':r'$\beta$PMG',
    'Tucana-Horologium':'Tuc-Hor',
    # 'Columba':'Columba',
    # 'Carina':'CAR',
    # 'TW Hya':'TWA',
    'Upper Centaurus Lupus':'UCL',
}

def calcRanges(star_pars, sep_axes=False, scale=True):
    """Simple function to calculate span in each dimension of stars with
    10% buffer"""
    ranges = {}
    for dim in range(star_pars['xyzuvw'].shape[1]):
        ranges[dim] = [
            np.min(star_pars['xyzuvw'][:, dim]),
            np.max(star_pars['xyzuvw'][:, dim]),
        ]
        buffer = 0.05 * (ranges[dim][1] - ranges[dim][0])
        ranges[dim][0] -= buffer
        ranges[dim][1] += buffer

    # adjust ranges so the span is consistent across pos axes and vel axes

    for dim in (3,4,5):
        print(ranges[dim][1] - ranges[dim][0])

    if sep_axes:
        xranges = {}
        yranges = {}
        for key in ranges.keys():
            xranges[key] = ranges[key][:]
            yranges[key] = ranges[key][:]
        if scale:
            scaleRanges(xranges, dims=(0,1,2))
            scaleRanges(xranges, dims=(3,4,5))
        return xranges, yranges
    else:
        if scale:
            scaleRanges(ranges, dims=(0,1,2))
            scaleRanges(ranges, dims=(3,4,5))

        return ranges


def scaleRanges(ranges, dims=(0,1,2)):
    """
    Rescale elements (inplace) in range such that span is equivalent
    """
    max_pos_span = np.max([ranges[dim][1] - ranges[dim][0] for dim in
                           dims])
    for k in ranges:
        ranges[k] = list(ranges[k])

    for dim in dims:
        midpoint = 0.5 * (ranges[dim][1] + ranges[dim][0])
        # import pdb; pdb.set_trace()
        ranges[dim][1] = midpoint + 0.5 * max_pos_span
        ranges[dim][0] = midpoint - 0.5 * max_pos_span

LABELS = 'xyzuvw'

if PLOT_BPMG_REAL:
    for iteration in ['5B']: #, '6C']:
        star_pars_file = '../../data/beta_Pictoris_with_gaia_small_xyzuvw.fits'
        star_pars = dt.loadXYZUVW(star_pars_file)
        fit_name = 'bpmg_and_nearby'
        rdir = '../../results/em_fit/beta_Pictoris_wgs_inv2_{}_res/'.format(iteration)

        memb_file = rdir + 'final_membership.npy'
        groups_file = rdir + 'final_groups.npy'

        z = np.load(memb_file)
        groups = dt.loadGroups(groups_file)

        # Assign markers based on BANYAN membership
        gt_sp = dt.loadDictFromTable('../../data/banyan_with_gaia_near_bpmg_xyzuvw.fits')
        banyan_membership = len(star_pars['xyzuvw']) * ['N/A']
        for i in range(len(star_pars['xyzuvw'])):
            master_table_ix = np.where(gt_sp['table']['source_id']==star_pars['gaia_ids'][i])
            banyan_membership[i] = gt_sp['table']['Moving group'][master_table_ix[0][0]]

        # assign markers based on present moving groups, keep track of
        # assoc -> marker relationship incase a legend is called for
        banyan_membership=np.array(banyan_membership)
        banyan_markers = np.array(len(banyan_membership) * ['.'])

        banyan_memb_set = set(banyan_membership)
        for bassoc in set(gt_sp['table']['Moving group']):
            if bassoc not in acronyms.keys():
                acronyms[bassoc] = bassoc
        banyan_markers[np.where(banyan_membership=='beta Pictoris')] = 'v'
        marker_label = []
        banyan_memb_set.remove('beta Pictoris')
        marker_label.append(acronyms['beta Pictoris'])
        marker_style = []
        marker_style.append('v')
        banyan_markers[np.where(banyan_membership=='Tucana-Horologium')] = '*'
        banyan_memb_set.remove('Tucana-Horologium')
        marker_label.append(acronyms['Tucana-Horologium'])
        marker_style.append('*')

        banyan_memb_set.remove('N/A')
        for banyan_assoc, marker in zip(banyan_memb_set, ('s', 'p', 'D', 'X', 'H', 'D')): #''''''^', '<', '>', '8', 's', 'p', 'h', 'H', 'D', 'd', 'P', 'X')):
            banyan_markers[np.where(banyan_membership==banyan_assoc)] = marker
            marker_label.append(acronyms[banyan_assoc])
            marker_style.append(marker)

        # First do all, then just do possible membs of BPMG
        if True:
        # if False:
            x_nearby_ranges, y_nearby_ranges =\
                calcRanges(star_pars, sep_axes=True, scale=False)
            nearby_star_pars = {}
            for key in ['xyzuvw', 'xyzuvw_cov']:
                nearby_star_pars[key] = np.copy(star_pars[key])

            # Replace cov matrices with None for bg stars
            nearby_star_pars['xyzuvw_cov'][
                np.where(z.argmax(axis=1)==z.shape[1]-1)
            ] = None
            # import pdb; pdb.set_trace()

            for dim1, dim2 in DEFAULT_DIMS: #[(0,1), (0,3), (1,4), (2,5)]: #, 'yv', 'zw']:
                # # force the XY plot to have same scales
                # if dim1==0 and dim2==1 and debugging_circles:
                #     temp_range = nearby_range[1]
                #     nearby_range[1] = [-120,80]

                x_nearby_ranges[dim1], y_nearby_ranges[dim2] = fp.plotPane(
                    dim1,
                    dim2,
                    groups=groups,
                    star_pars=nearby_star_pars,
                    group_now=True,
                    membership=z,
                    # true_memb=true_memb,
                    savefile='{}_{}_{}{}.pdf'.format(fit_name, iteration,
                                                     LABELS[dim1], LABELS[dim2]),
                    with_bg=True,
                    range_1=x_nearby_ranges[dim1], #range_1,
                    range_2=y_nearby_ranges[dim2], #range_2,
                    markers=banyan_markers,
                    marker_style=marker_style,
                    marker_labels=marker_label if dim1 == 2 else None,
                    color_labels=COLOR_LABELS[:len(groups)] if
                                   dim1 == 2 else None,
                    isotropic=(int(dim1/3) == int(dim2/3)),
                )
                # # undo forced change
                # if dim1 == 0 and dim2 == 1 and debugging_circles:
                #     nearby_range[1] = temp_range
                scaleRanges(x_nearby_ranges, (0,1,2))
                scaleRanges(x_nearby_ranges, (3,4,5))
                scaleRanges(y_nearby_ranges, (0,1,2))
                scaleRanges(y_nearby_ranges, (3,4,5))

        # Only include stars that, if they weren't bg, they'd most likely be BPMG
        if iteration == '5B':
            fit_name = 'bpmg_candidates'
            # extract_group_ix = [0,2]
            extract_group_ixs_by_iteration = {
                '5B':[0],
                '6C':[0,2],
            }
            extract_group_ix = extract_group_ixs_by_iteration[iteration]
            # bpmg_mask = np.where(z[:,extract_group_ix]>0.1)
            bpmg_star_pars = {}
            # bpmg_mask = np.where(np.isin(np.argmax(z[:,:-1], axis=1), extract_group_ix))# == extract_group_ix)
            bpmg_mask = np.where(np.isin(np.argmax(z, axis=1), extract_group_ix))# == extract_group_ix)
            bg_mask = np.where(np.logical_not(
                np.isin(np.argmax(z, axis=1), extract_group_ix)
            ))
            bpmg_star_pars['xyzuvw'] = star_pars['xyzuvw'] #[bpmg_mask]
            bpmg_star_pars['xyzuvw_cov'] = np.copy(star_pars['xyzuvw_cov']) #[bpmg_mask]
            bpmg_star_pars['xyzuvw_cov'][bg_mask] = None
            bpmg_star_pars['indices'] = np.array(star_pars['indices']) #[bpmg_mask]

            # z = z[bpmg_mask]#, (0,-1),]
            z = z[:,(extract_group_ix+[-1]),]

            # bpmg_range = calcRanges(bpmg_star_pars)

            for dim1, dim2 in DEFAULT_DIMS: #[(0,1), (0,3), (1,4)]: #, (2,5)]: #, 'yv', 'zw']:
                # force the XY plot to have same scales
                # if dim1==0 and dim2==1 and debugging_circles:
                #     temp_range = bpmg_range[1]
                #     bpmg_range[1] = [-120,80]

                fp.plotPane(
                    dim1,
                    dim2,
                    groups=groups[extract_group_ix],
                    star_pars=bpmg_star_pars,
                    group_now=True,
                    membership=z,
                    savefile='{}_{}_{}{}.pdf'.format(fit_name,
                                                     iteration,
                                                     LABELS[dim1],
                                                     LABELS[dim2]),
                    with_bg=True,
                    # range_1=bpmg_range[dim1],
                    range_1=x_nearby_ranges[dim1],
                    # range_2=bpmg_range[dim2],
                    range_2=y_nearby_ranges[dim2],
                    # residual=True,
                    markers=banyan_markers,
                    marker_style=marker_style,
                    marker_labels=marker_label if dim1==2 else None,
                    color_labels=[r'Fitted $\beta$PMG'] if dim1==2 else None,
                    isotropic=(int(dim1/3) == int(dim2/3))
                )
                # # undo forced change
                # if dim1 == 0 and dim2 == 1 and debugging_circles:
                #     bpmg_range[1] = temp_range

        # To ensure consistency, we now plot the BANYAN bpmg stars only,
        # and use the ragnes from previous plot
        fit_name = 'banyan_bpmg'
        rdir = '../../results/em_fit/beta_Pictoris/'

        memb_file = rdir + 'final_membership.npy'
        groups_file = rdir + 'final_best_groups.npy'
        star_pars_file = '../../data/beta_Pictoris_with_gaia_small_xyzuvw.fits'

        z = np.load(memb_file)
        groups = dt.loadGroups(groups_file)
        star_pars = dt.loadDictFromTable(star_pars_file, 'beta Pictoris')
        nstars = len(star_pars['xyzuvw'])

        # First do all, then just do possible membs of BPMG
        for dim1, dim2 in DEFAULT_DIMS: #[(0,1), (0, 3), (1, 4), (2,5)]: #, (2, 5)]:  # , 'yv', 'zw']:
            # if dim1 == 0 and dim2 == 1 and debugging_circles:
            #     temp_range = bpmg_range[1]
            #     bpmg_range[1] = [-120, 80]
            # import pdb; pdb.set_trace()
            fp.plotPane(
                dim1,
                dim2,
                groups=groups,
                star_pars=star_pars,
                group_now=True,
                membership=z,
                # true_memb=true_memb,
                savefile='{}_{}{}.pdf'.format(fit_name, LABELS[dim1],
                                              LABELS[dim2]),
                with_bg=True,
                range_1=x_nearby_ranges[dim1],
                range_2=y_nearby_ranges[dim2],
                markers=nstars*['v'],
                marker_labels=[r'BANYAN $\beta$PMG'] if dim1==2 else None,
                color_labels=[r'Chronostar $\beta$PMG'] if dim1==2 else None,
                isotropic=(int(dim1/3) == int(dim2/3)),
            )
            # undo forced change
            # if dim1 == 0 and dim2 == 1 and debugging_circles:
            #     bpmg_range[1] = temp_range


# plotting federrath stars
if PLOT_FED_STARS:
    print("Plotting fed stars)")
    synth_fit = 'fed_stars'
    # rdir = '../../results/fed_fits/30/gaia/'
    rdir = '../../results/fed_fits/20/gaia/'
    origins_file = rdir + 'origins.npy'
    chain_file = rdir + 'final_chain.npy'
    lnprob_file = rdir + 'final_lnprob.npy'
    star_pars_file = rdir + 'xyzuvw_now.fits'
    # init_xyzuvw_file = '../../data/sink_init_xyzuvw.npy'
    init_xyzuvw_file = rdir + '../xyzuvw_init_offset.npy'
    # perf_xyzuvw_file = rdir + '../perf_xyzuvw.npy'
    # star_pars_file = '../../data/fed_stars_20_xyzuvw.fits'

    chain = np.load(chain_file).reshape(-1,9)
    lnprobs = np.load(lnprob_file)
    # best_fit_pars = np.load(chain_file)[np.unravel_index(np.argmax(lnprobs), lnprobs.shape)]
    best_fit_pars = chain[np.argmax(lnprobs)]
    groups = [syn.Group(best_fit_pars, internal=True, starcount=False)]
    origins = dt.loadGroups(origins_file)
    raw_init_xyzuvw = np.load(init_xyzuvw_file)
    # perf_xyzuvw = np.load(perf_xyzuvw_file)
    # init_xyzuvw = torb.traceManyOrbitXYZUVW(perf_xyzuvw, -origins[0].age,
    #                                         single_age=True)
    init_xyzuvw = np.load(init_xyzuvw_file)

    star_pars = dt.loadXYZUVW(star_pars_file)
    fed_xranges, fed_yranges = calcRanges(
        {'xyzuvw':np.vstack((star_pars['xyzuvw'],init_xyzuvw))},
        sep_axes=True,
    )
    # import pdb; pdb.set_trace()

    for dim1, dim2 in DEFAULT_DIMS: #[(0,1), (0,3), (1,4), (2,5)]:
        # plt.clf()
        fed_xranges[dim1], fed_yranges[dim2] = fp.plotPane(
            dim1,
            dim2,
            groups=groups,
            star_pars=star_pars_file,
            origin_star_pars={'xyzuvw':init_xyzuvw},
            group_then=True,
            group_now=True,
            star_orbits=True,
            savefile='{}_both_{}{}.pdf'.format(synth_fit,
                                               LABELS[dim1],
                                               LABELS[dim2]),
            marker_legend={'current-day':'.', 'origin':'s'} if dim1==2 else None,
            color_legend={'current-day':'xkcd:blue', 'origin':'xkcd:blue'} if dim1==2 else None,
            star_pars_label='current-day',
            origin_star_pars_label='origin',
            isotropic=(int(dim1/3) == int(dim2/3)),
            range_1=fed_xranges[dim1],
            range_2=fed_yranges[dim2],
        )
        scaleRanges(fed_xranges, (0, 1, 2))
        scaleRanges(fed_xranges, (3, 4, 5))
        scaleRanges(fed_yranges, (0, 1, 2))
        scaleRanges(fed_yranges, (3, 4, 5))
        # scaleRanges(fed_xranges, (0,1,2))
        # scaleRanges(fed_xranges, (3,4,5))

# plotting Multi-component synth fits
if PLOT_MUTLI_SYNTH:
    print("Plotting synth plots")
    synth_fits = [
        'synth_bpmg',
        'four_assocs',
        'assoc_in_field',
        'same_centroid',
    ]

    rdir_suffix = {
        'synth_bpmg':'',
        'four_assocs':'_res',
        'assoc_in_field':'_res',
        'same_centroid':'_res',
    }

    planes = {
        'synth_bpmg':['xu', 'zw'], #['xu', 'zw', 'xy']#, 'yz'],
        'four_assocs':['xu', 'zw'], #['xy', 'yv'],
        'assoc_in_field':['xu', 'zw'], #['uv', 'xu'],
        'same_centroid':['xu', 'zw'], #['xu', 'yv'],
    }

    with_bg = {
        'synth_bpmg':True,
        'four_assocs':False,
        'assoc_in_field':False,
        'same_centroid':False,
    }

    ordering = {
        'synth_bpmg':[1, 0],
        'assoc_in_field':[1, 0],
        'four_assocs':[3, 2, 0, 1],
        'same_centroid':[1, 0],
    }

    MARKER_LABELS = np.array(['True {}'.format(ch) for ch in 'ABCD'])

    for synth_fit in synth_fits:
        print(" - plotting {}".format(synth_fit))
        rdir = '../../results/em_fit/{}{}/'.format(synth_fit,
                                                   rdir_suffix[synth_fit])
        groups_file = rdir + 'final_best_groups.npy'
        # star_pars_file = rdir + '{}_xyzuvw.fits'.format(synth_fit)
        groups = dt.loadGroups(groups_file)
        star_pars_file = '../../data/{}_xyzuvw.fits'.format(synth_fit)
        memb_file = rdir + 'final_membership.npy'
        origins_file = rdir + 'synth_data/origins.npy'
        true_memb = dt.getZfromOrigins(origins_file, star_pars_file)
        ranges = calcRanges(dt.loadXYZUVW(star_pars_file))
        xaxis_ranges, yaxis_ranges =  calcRanges(dt.loadXYZUVW(star_pars_file),
                                                 sep_axes=True)
        # yaxis_ranges = {}
        # for key in ranges.keys():
        #     xaxis_ranges[key] = ranges[key][:]
        #     yaxis_ranges[key] = ranges[key][:]

        for dim1, dim2 in DEFAULT_DIMS: #planes[synth_fit]:
            print("   - {} and {}".format(dim1, dim2))
            xaxis_ranges[dim1], yaxis_ranges[dim2] = fp.plotPaneWithHists(
                dim1,
                dim2,
                groups=groups_file,
                star_pars=star_pars_file,
                group_now=True,
                membership=memb_file,
                true_memb=true_memb,
                savefile='{}_{}{}.pdf'.format(synth_fit,
                                              LABELS[dim1],
                                              LABELS[dim2]),
                with_bg=with_bg[synth_fit],
                group_bg=(synth_fit == 'assoc_in_field'),
                isotropic=(int(dim1/3) == int(dim2/3)),
                range_1=xaxis_ranges[dim1],
                range_2=yaxis_ranges[dim2],
                color_labels=COLOR_LABELS[:len(groups)] if dim1 == 2 else None,
                marker_labels=MARKER_LABELS[:len(groups)] #[ordering[synth_fit]]
                              if dim1 == 2 else None,
                ordering=ordering[synth_fit],
                marker_order=ordering[synth_fit],
            )
            scaleRanges(xaxis_ranges, (0, 1, 2))
            scaleRanges(xaxis_ranges, (3, 4, 5))
            scaleRanges(yaxis_ranges, (0, 1, 2))
            scaleRanges(yaxis_ranges, (3, 4, 5))


if PLOT_FAILURE:
    synth_fit='failure_mode'
    labels = ['a', 'b']
    groups = []
    for label in labels:
        rdir = '../../results/synth_fit/30_2_1_25_{}_double/'.format(label)
            # rdir = '../../results/new_fed_stars_20/gaia/'
        # origins_file = rdir + 'origins.npy'
        chain_file = rdir + 'final_chain.npy'
        lnprob_file = rdir + 'final_lnprob.npy'
        # init_xyzuvw_file = '../../data/sink_init_xyzuvw.npy'
        # init_xyzuvw_file = rdir + '../xyzuvw_init_offset.npy'
        # perf_xyzuvw_file = rdir + '../perf_xyzuvw.npy'
        # star_pars_file = '../../data/fed_stars_20_xyzuvw.fits'

        chain = np.load(chain_file).reshape(-1,9)
        lnprobs = np.load(lnprob_file)
        # best_fit_pars = np.load(chain_file)[np.unravel_index(np.argmax(lnprobs), lnprobs.shape)]
        best_fit_pars = chain[np.argmax(lnprobs)]
        groups.append(syn.Group(best_fit_pars, internal=True, starcount=False))
        # origins = dt.loadGroups(origins_file)
        # raw_init_xyzuvw = np.load(init_xyzuvw_file)
        # perf_xyzuvw = np.load(perf_xyzuvw_file)
        # init_xyzuvw = torb.traceManyOrbitXYZUVW(perf_xyzuvw, -origins[0].age,
        #                                         single_age=True)
        # init_xyzuvw = np.load(init_xyzuvw_file)


    # this luckiliy picks out sample 'b' which is what we want.
    star_pars_file = rdir + 'xyzuvw_now.fits'

    for dim1, dim2 in DEFAULT_DIMS: #['xy', 'xu', 'yv', 'zw', 'uv', 'uw']:
        fp.plotPane(
            dim1,
            dim2,
            groups=groups[::-1], # reverse groups so failure is coloured
            star_pars=star_pars_file,
            group_now=True,
            group_then=True,
            star_orbits=True,
            group_orbit=True,
            membership=None,
            true_memb=None,
            savefile='{}_{}{}.pdf'.format(synth_fit,
                                          LABELS[dim1],
                                          LABELS[dim2]),
            isotropic=(int(dim1/3) == int(dim2/3)),
        )
