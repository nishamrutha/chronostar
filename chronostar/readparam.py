"""
This module defines the parameter reading function.
Used to parse a text file into a dictionary to be
passed to datatool.prepare_data()

It also defines the default parameters for prepare_data()


Credit: Mark Krumholz
"""

# def update_data_defaults(data_pars):
#     """
#     Maybe this belongs somewhere else, but... for now....
#
#     Default parameters are stored in this function. If a parameter is
#     missing from data_pars, then it is inserted with it's default value.
#
#     Parameters
#     ----------
#     data_pars : dict
#
#     Returns
#     -------
#     updated_data_pars : dict
#     """
#     default_dict = {
#         'input_file':'',
#         'convert_astrometry':False,
#
#         'astr_main_colnames':None,
#         'astr_error_colnames':None,
#         'astr_corr_colnames':None,
#
#         'cart_main_colnames':None,
#         'cart_error_colnames':None,
#         'cart_corr_colnames':None,
#
#         'apply_cart_cuts':False,
#         'cut_on_region':False,
#         'cut_ref_table':None,
#         'convert_ref_table':False,
#         'cut_assoc_name':None,
#         'cut_colname':None,
#         'cut_on_bounds':False,
#         'cut_bound_min':None,
#         'cut_bound_max':None,
#
#         'calc_overlaps':False,
#         'bg_ref_table':'',
#         'bg_main_colnames':None,
#         'bg_col_name':'background_log_overlap',
#         'par_log_file':'data_pars.log',
#
#         'overwrite_datafile':False,
#         'output_file':None,
#
#         'return_data_table':True,
#     }
#
#     default_dict.update(data_pars)
#     return default_dict

def log_used_pars(custom_pars, default_pars=None):
    """
    Write parameter record to file, making a note which have been
    changed.

    Parameters
    ----------
    data_pars : dict
        A dict that has been generated by `readParam`

    Returns
    -------
    None

    Side effects
    ------------
    Writes a file to `data_pars['par_log_file']`
    """
    if default_pars is None:
        default_pars = {}

    # update defaults (no change if already performed)
    combined_pars = dict(default_pars)
    combined_pars.update(custom_pars)
    # data_pars = update_data_defaults(data_pars, default)

    with open(combined_pars['par_log_file'], 'w') as fp:
        fp.write('# Parameters used\n\n')
        for k in sorted(combined_pars.keys()):
            if k not in default_pars.keys():
                msg = '# [NO PROVIDED DEFAULT]'
            elif combined_pars[k] != default_pars[k]:
                msg = '# [CHANGED]'
            else:
                msg = ''
            line = '{:25} = {:45} {}\n'.format(k, str(combined_pars[k]), msg)
            fp.write(line.replace("'",''))


def readParam(param_file, default_pars=None, noCheck=False):
    """
    This function reads a parameter file.

    Parameters
    ----------
    param_file : string
       A string giving the name of the parameter file
    noCheck : bool
       If True, no checking is performed to make sure that all
       mandatory parameters have been specified

    Returns
    -------
    param_dict : dict
       A dict containing a parsed representation of the input file

    Notes
    -----
    TODO: Work out how to format input for synthetic association
    TODO: maybe just dont? And require the use of a script to intialise things?
    """
    if default_pars is None:
        default_pars = {}

    # Prepare an empty dict to hold inputs
    custom_pars = {}

    # Try to open the file
    with open(param_file, 'r') as fp:

        # Read the file
        for line in fp:

            # Skip blank and comment lines
            if line == '\n':
                continue
            if line.strip()[0] == "#":
                continue

            # Break line up based on equal sign
            linesplit = line.split("=")
            if len(linesplit) < 2:
                print("Error parsing input line: " + line)
                raise IOError
    #         if linesplit[1] == '':
    #             print("Error parsing input line: " + line)
    #             raise IOError

            # Trim trailing comments from portion after equal sign
            linesplit2 = linesplit[1].split('#')

            # Store token-value pairs, as strings for now. Type conversion
            # happens below.
            if linesplit2 != '':
                # linesplit2[0].replace("'",'')
                custom_pars[linesplit[0].strip()] = linesplit2[0].strip()

    # Try converting parameters to bools or numbers, for convenience
    for k in custom_pars.keys():
        try:
            custom_pars[k] = int(custom_pars[k])
        except ValueError:
            try:
                custom_pars[k] = float(custom_pars[k])
            except ValueError:
                pass

        # Order is important, as int(True) -> 1
        try:
            if custom_pars[k].lower() == 'true':
                custom_pars[k] = True
            elif custom_pars[k].lower() == 'false':
                custom_pars[k] = False
        except AttributeError:
            pass

    # Find any lists (of floats) and convert accordingly
    # Assumes first char is '[' and last char is ']'
    # Can allow for trailing ','
    for k in custom_pars.keys():
        try:
            if custom_pars[k][0] == '[':
                # First build list of strings
                custom_pars[k] = [val.strip() for val in custom_pars[k][1:-1].split(',')
                                if val.strip()]
                # Then try converting to floats
                try:
                    custom_pars[k] = [float(val) for val in custom_pars[k]]
                except ValueError:
                    pass
        except (TypeError, IndexError):
            pass

    # Now that we have collected custom parameters into a dictionary,
    # Make copy of default parameters, and update
    combined_pars = dict(default_pars)
    combined_pars.update(custom_pars)

    # if not noCheck:
    #     mandatory = ['alpha', 'gamma', 'ibc_pres_type', 'ibc_enth_type',
    #                  'ibc_pres_val', 'obc_pres_type', 'obc_enth_type',
    #                  'obc_pres_val']
    #     for m in mandatory:
    #         if not m in param_dict:
    #             raise ValueError("Error: must specify parameter " + m + "!\n")

    return combined_pars
