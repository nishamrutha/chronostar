"""
Author: Marusa Zerjal, 2019 - 07 - 15

Take Sco-Cen components fitted to 6D data and make overlaps
(using covariance matrix) with stars missing radial velocities
in order to find more Sco-Cen candidates.

MZ: It fails in python2 (cannot import emcee).

"""

import numpy as np
import sys
sys.path.insert(0, '..')
from chronostar.component import SphereComponent
from chronostar import tabletool
from chronostar import expectmax
from astropy.table import Table, vstack, join

datafile = 'data_table_cartesian.fits'


# Read all components
#c_usco = np.load('usco_res/final_comps.npy')
#c_ucl = np.load('ucl_res/final_comps.npy')
#c = np.vstack((c_usco, c_ucl))

c = np.load('all_nonbg_scocen_comps.npy') # including LCC
print('components', c.shape)
print('Are there duplicate components?')

print (c)
print (c.shape)



try:
    data_table = Table.read(datafile)
except:
    # Read Gaia data including both stars with known and missing radial velocities
    data_table = tabletool.read('../data/ScoCen_box_result.fits')
    #data_table = tabletool.read('../data/scocen_for_testing.fits') # Shorter table
    #data_table=data_table[:100]
    print('DATA READ', len(data_table))
    # Set missing radial velocities to some value, and their errors to something very big

    # Set missing radial velocities (nan) to 0
    data_table['radial_velocity'] = np.nan_to_num(data_table['radial_velocity'])

    # Set missing radial velocity errors (nan) to 1e+10
    data_table['radial_velocity_error'][np.isnan(data_table['radial_velocity_error'])] = 1e+4

    print(data_table)

    # Convert to Cartesian
    print('Convert to cartesian')
    historical = 'c_XU' in data_table.colnames
    # Performs conversion in place (in memory) on `data_table`
    if (not 'c_XU' in data_table.colnames and not 'X_U_corr' in data_table.colnames):
        tabletool.convert_table_astro2cart(table=data_table, return_table=True)


#data_table.write('data_table_cartesian.fits')

# data_table should include background overlaps as well

# Background overlaps (using covariance matrix)
ln_bg_ols = expectmax.get_background_overlaps_with_covariances(
    '/home/tcrun/chronostar/data/gaia_cartesian_full_6d_table.fits',
    data_table,
)

bg_lnol_colname = 'background_log_overlap'
print('Background overlaps')
tabletool.insert_column(data_table, bg_lnol_colname, ln_bg_ols, filename=datafile)

print('Create data dict')
# Create data dict
data_dict = tabletool.build_data_dict_from_table(
        data_table,
        get_background_overlaps=True, # TODO change to True and provide bg ols
        historical=historical,
)

# Create components
comps = [SphereComponent(pars=x) for x in c]
print(comps)



overlaps = expectmax.get_all_lnoverlaps(data_dict, comps)
#print(overlaps)
#print('overlaps.shape', overlaps.shape)

membership_probabilities = np.array([expectmax.calc_membership_probs(ol) for ol in overlaps])
#print(membership_probabilities)
#print(membership_probabilities.shape)

for i in range(membership_probabilities.shape[1]):
    data_table['comp_overlap_%d' % (i + 1)] = membership_probabilities[:, i]
#for i in range(4):
#    data_table['comp_overlap_usco%d'%(i+1)]=membership_probabilities[:,i]
#for i in range(4):
#    data_table['comp_overlap_ucl%d'%(i+1)]=membership_probabilities[:,i+4]

print(data_table)

# Compare with membership probabilities of stars with known radial velocities
memb_usco = np.load('usco_res/final_membership.npy')
data_usco = Table.read('usco_res/usco_run_subset.fit')
for i in range(memb_usco.shape[1]-1):
    data_usco['Comp_USco_%d'%(i+1)] = memb_usco[:,i]
data_usco['Comp_bg'] = memb_usco[:,-1]

memb_ucl = np.load('ucl_res/final_membership.npy')
data_ucl = Table.read('ucl_res/ucl_run_subset.fit')
for i in range(memb_ucl.shape[1]-1):
    data_ucl['Comp_UCL_%d'%(i+1)] = memb_ucl[:,i]
data_ucl['Comp_bg'] = memb_ucl[:,-1]

data_memb = vstack([data_usco, data_ucl])
print(data_memb)

print(type(data_table['source_id'][0]))
print(type(data_memb['source_id'][0]))

d = join(data_table, data_memb, keys='source_id')
print(d)