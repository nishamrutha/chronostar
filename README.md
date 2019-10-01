# Chronostar
A stellar orbit traceback code - *work in progress*

In this repository, we will try to prototype some orbital traceback calculations.

## Project Structure
- benchmarks: A collection of scripts comparing the timings of various
implementations of the overlap integral calculation
- build: of no consequence, a byproduct of running setup.py
- chronostar: housing the integral modules of this software
- data: where astrometry data should live
- demos: toy examples deomstrating usages of various methods, not all
mine
- integration_tests: complicated tests that can take upwards of
30 mins to run, testing everythign workign together
- junkpile: where forgotten code goes to die.
- playground: where I work out how to use things
- results: plots and logs of science runs
- scripts: where the science happens
- tests: unittests that cover the low level stuff - should execute within
half a minute

## Installing

### Dependencies
Python libraries (i.e. pip install [library name])
- astropy
- emcee
- galpy

Other tools:
- mpirun


## Setup
Now that python dependencies are met, we need to install swig, a means
to wrap c code such that it can be imported and called by python.

Requirements:
- swig
- gsl (e.g. sudo apt install libgsl0-dev)
- pcre

If these are installed, in the main directory (chronostar) run:

	python setup.py build_ext -b .


### Installing swig
#### Linux (Ubuntu)

    sudo apt install libgsl0-dev
    sudo apt install libpcre3
    sudo apt install libpcre3-dev
    sudo apt install swig

#### Mac

    brew install gsl
    brew install swig  # (will auto install dependency: pcre)

#### Manual installation
If installing swig doesn't work, go to
https://sourceforge.net/projects/swig/
and download swig (target language python)
and, after installing pcre and gsl, follow
instructions in 'INSTALL.txt'

e.g.

    cd [source directory]
    ./configure
    make
    make install

# Testing

Next check everything is in working order. 

    cd unit_tests/
    pytest
    
will run the unittests.
Next, try the following:

    cd integration_tests/
    python test_groupfitter.py
   
This will take ~ 20-40 minutes on a typical machine. A single fit usually
requires approximately 3000 steps to converge, and 100 steps takes about a minute.

Next, (assuming you're on a server with many cores) in the same directory try:

    nohup mpirun -np 19 python test_mpirun.py &
    
If your server has 19+ cores, then run as above. If there's less, then reduce
the number accordingly. Increasing the number of threads is not useful as
each thread is associated with an *emcee* walker, and there are only 18 walkers
being used in this run. Depending on the cores available and how busy the server
is, this should take ~5 minutes. Checkout the walker plots in temp_plots/.

## Files
(will include links to required files)

## Running
Running Chronostar is split into two main parts. The first is the data 
preparation where, for example, astrometric data are converted into the
Chronostar Cartesian based coordinate system. The second is the actual
fitting to the data.

The entry points for these are chronostar.datatoo.prepare_data()
and chronostar.chronostar.NaiveFit().

In both cases, runnable scripts are provided which takes as a single 
commandline argument the path to a parameter file. Alternatively,
one can import the methods into a custom script and pass in either
a parameter file or a dictionary `data_pars`.

If setting parameters via a .pars file, then simply enter the raw information,
i.e. no quotation markers for strings. Lists with `[` and `]`. File paths
must be relative to the directory in which Chronostar is being executed.

An example 
```
# Whole line comments are fine
input_file = data/my_astrometric_data_file.fits      # In line Comments are fine
# If applying data cuts, DO NOT set output file to be the same as input file
output_file = data/my_input_to_chronostar.fits
# Denote lists with square brackets
astr_main_colnames = [ra,dec,parallax,pmra,pmdec,radial_velocity]
convert_astrometry = True
# Set booleans as True or False
apply_cart_cuts = True
# Any case style is... fine
cut_on_bounds = tRuE
# Lists of floats can be provided thusly
cut_bound_min = [-100.,-50., -20.,-5.,-5.,-5]  
# Whitespace is fine, and trailing commas are undesirable, but handled
cut_bound_max = [ 100., 50.,  20., 5., 5., 5,]
```
 
### Data Preparation
A list of viable parameters (with defaults) is listed in
`readparam.update_data_defaults`
An non-exhaustive list of data preparation parameters are listed here:
  - input_file: string or astropy table [default = ''] [required]
    
    (path to) an astropy table (stored as a fits file) with, at a
    minimum, all the required astrometric data (radec position, parallax,
    proper motions, radial velocity [optional]). This file can be the
    output of a previous call to `prepare_data()`, with cartesian data,
    background overlaps etc.
  - convert_astrometry: "True" or "False" [def = 'False'] [optional]
    
    If "True", convert astrometric data in table into cartesian, adding
    designated columns for storing these.
  
  - astr_main_colnames: list of labels [default = None] [optional]
  
    Can optionally include the name of column names for measured data.
    It is recommended to manually
    modify the column names of the input table to reflect the defaults assumed by
    Chronostar (which are the default Gaia column names) prior to running
    `prepare_data`:
    [ra,dec,parallax,pmra,pmdec,radial_velocity]
    with units
    [degrees, degrees, mas, mas/yr, mas/yr, km/s]
    But if the users desires to retain their column names, provide a list
    of labels in the same order.
    Chronostar can in theory run on data with missing radial velocity data.
    The user must simply insert 0s into the radial_velocity column.
    
  - astr_error_colnames: list of labels [default = None] [optional]
  
    Similar to astr_main_colnames, but for the errors. The default labels
    are
    [ra_error,dec_error,parallax_error,pmra_error,pmdec_error,radial_velocity_error]
    If your data has no error for ra and dec, manually insert something very
    small, like... 1e-6 degrees.
    Any user input must match the order.
    Note: if you have provided astr_main_colnames, and your error column names
    are of the form 'measure_error' then this parameter can be left alone.
    If any of your stars are missing radial velocities, Chronsotar can in theory
    run. The user must simply insert a very large uncertainty (say 100km/s).
    
  - astr_corr_colnames: list of labels [default = None] [optional]
  
    Similar to astr_main_colnames, but for the correlations. The default labels
    reflect those used by Gaia and can be generated with:
    ```
    amcs = ['ra','dec','parallax','pmra','pmdec','radial_velocity']
    astr_corr_colnames = []
    for i in range(6):
        for j in range(i+1,6):
            astr_corr_colnames.append('{}_{}_corr'.format(amcs[i], amcs[j]))
    ```
    note: if you have provided astr_main_colnames, and your correlation column
    names match the generation snippet above, then this parameter can be 
    left alone.
    
   - cart_main_colnames: list of labels [default = None] [optional] 
   
     Similar to astr_main_colnames, but for the Cartesian coordinate conversions.
     If left unset, defaults to:
     [X,Y,Z,U,V,W]
    
   - cart_error_colnames: list of labels [default = None] [optional]
   
     The astr_error_colnames of cart_main_colnames
     
   - cart_corr_colnames: list of labels [default = None] [optional]
   
     The astr_corr_colnames of cart_main_colnames
     
   - apply_cart_cuts: True or False [default = False] [optional]
   
     If true, Chronostar will apply a data cut based in cartesian space.
     Either by some 6D box drawn around a provided set of stars (by setting
     the flag `cut_on_region` and providing a reference table by filename to
     `cut_ref_table`) or by some provided set of boundaries in XYZUVW (by
     setting the flag `cut_on_bounds` and providing a list of floats to
     `cut_bound_min` and `cut_bound_max` [UNTESTD!]).
     
   - cut_on_region: True or False [default = False] [optional]
   
     If true, Chronostar will use a provided astropy table to generate
     a set of boundaries that encompass the target stars within said table.
     A subset of this table can be used by ensuring the label given to
     `cut_assoc_name` is featured in the column `cut_colname`.
     For example, if you have a table saved to 'some_assocs.fits',
     which, within held members of the beta pictoris moving group, identified
     by the label 'bpmg' in the 'moving_groups' column, one would set:
     ```
     apply_cart_cuts = True
     cut_on_region = True
     cut_ref_table = some_assocs.fits
     cut_colname = moving_groups
     cut_assoc_name = bpmg
     ```
     The current default is to add a margin of 30 pc in position in 5 km/s
     in velocity around the containing volume of the reference stars.
    
   - cut_ref_table: string or astropy table [default = None] [optional]  
    
     A (path to an) astropy table which holds the reference stars with which
     some cartesian boundary will be generated.
     
   - cut_assoc_name: string [defalut = None] [optional]
   
     The label used to identify the reference stars in `cut_ref_table` in
     the column `cut_colname`. If left unset, then all stars in `cut_ref_table`
     will be used.
     
   - cut_colname: string [default = None] [optional]
   
     The column in `cut_ref_table` where certain stars can be identified to
     be the reference stars.
    
   - cut_on_bounds: True or False [default = False] [optional]
   
     If true, will use a provided list of floats (`cut_bound_min` and 
     `cut_bound_max`) to only fit to stars within the 6D box drawn by 
     these boundaries.
     
   - cut_bound_min: list of floats [default = None] [optional]
   
     Minimum in XYZUVW. If provided in file, set like:
     ```
     #                X[pc] Y[pc],Z[pc],U[km/s],V[km/s],W[km/s]
     cut_bound_min = [-100, -50.8,  0. , -20.,  10.,  15] 
     ```
     If provided via dictionary built within a script, ensure values
     are actually floats (and not strings).
     
   - cut_bound_max: list of floats [default = None] [optional]
   
     Maximum in XYZUVW. Set just like `cut_bound_min`
     
   - calc_overlaps: True or False [default = False] [optional]
     
     If true, will calculate the overlaps of the stars with an assumed
     background density distribution. Basically the likelihood (unnormalised
     probability) of membership to the background field.
     This is particularly expensive and time consuming, so try to do this once
     and save the result.
     
     You must also provide an astropy table to `bg_ref_table` which is a list
     of stars believed to be representative of the background. For example
     Crundall et al. (2019) use all Gaia DR2 stars with RVs and parallax
     error better than 20%.
     
     The calculated overlaps will be stored in the column name given to
     `bg_col_name`
     
   - bg_ref_table: string [default = ''] [optional]
     An astropy table which is a list
     of stars believed to be representative of the background. For example
     Crundall et al. (2019) use all Gaia DR2 stars with RVs and parallax
     error better than 20% (~6,000,000 stars).
     
     This table must have cartesian columns [X,Y,Z,U,V,W] (errors are unnecessary).
     
     User must first set up this table, and convert from astrometry to cartesian.
     This will take a while to run... alternatively feel free to contact
     Tim Crundall (crundall[at]ph1.uni-koeln.de) for this reference data.
    
   - bg_main_colnames: list of labels [default = None] [optional]
     
     The cartesian column names (if None then uses [X,Y,Z,U,V,W]) of the
     data in parsecs.
   
   - bg_col_name: string [default = None] [optional]
     
     The name of the column in which to store background overlaps
     
   - par_log_file: string [default = 'data_pars.log'] [optional]
    
     The name of the log file which makes a log of all parameters used,
     their values, and whether they were left as default. This file respects
     the format of the input .pars file, and so can be used as a .pars file
     for a future run.
     
   - output_file: string [required]
   
     Resulting table will be saved to this filename.
    
   - overwrite_datafile: True or False [default = False] [optional]
   
     If true, in the event that `output_file` already exists, it will be
     overwritten.
   
     If you wish to overwrite the input file, then as a safety precaution, you
     must both set the `output_file` to the same filename as `input_file` AND
     set this flag to True.
     
   - return_data_table: True or False [default = True] [optional]
   
     If true, `prepare_data` will return the resulting table. This is useful
     if working in a script.
     

[//]: # (# Outdated information)


[//]: # (## EXAMPLE RUN Need to update this section)

[//]: # (For synthetic data:)

[//]: # (./gen_synth_data.py)
[//]: # (./generate_default_tb.py data/synth_data_1groups_*)
[//]: # (./fit_synth_1groups.sh )
[//]: # ()
[//]: # (Investigate results by checking most recent log fils:)
[//]: # (ls logs/ -rtal)
[//]: # ()
[//]: # (You can also plot the corner plots and the lnlike plots. After each run the)
[//]: # (suitable command will be displayed. e.g.)
[//]: # (Logs written)
[//]: # (Plot data saved. Go back and plot with:)
[//]: # (./plot_it.py -t 817882 -f 1 -r 0 -p 1000 -l)
[//]: # (   if not on raijin, or:)
[//]: # (./plot_it.py -t 817882 -f 1 -r 0 -p 1000)
[//]: # ()
[//]: # ()
[//]: # (## Example Setup on Raijin)
[//]: # (if running on node, load required modules:)
[//]: # (	can optionally append these commands to .profile file)
[//]: # (	but I don't fully understand behaviour and can lead to)
[//]: # (	conflicts if modules are preloaded elsewhere...)
[//]: # (	)
[//]: # (	module load python/2.7.11)
[//]: # (	module load python/2.7.11-matplotlib)
[//]: # (	module load gsl/1.15)
[//]: # (	)
[//]: # (nly need to install required python packages once (ever)
[//]: # (ut modules must be loaded first, and I believe these packages)
[//]: # (ill be guaranteed to work for only those modules)
[//]: # ()
[//]: # (	pip install --user astropy)
[//]: # (	pip install --user galpy)
[//]: # (	pip install --user emcee)
[//]: # (	pip install --user corner)
[//]: # (	pip install --user mpi4py)
[//]: # (	pip install --user sympy)
[//]: # ()
[//]: # (build)
[//]: # ()
[//]: # (	python setup.py build_ext -b .)

