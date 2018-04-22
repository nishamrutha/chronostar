"""
Testing the coordinates.py moduel - a utility module for converting
between various coordinate systems
"""
import numpy as np
import sys

import astropy.units as u
#from astropy.coordinates import SkyCoord

#from galpy.util import bovy_coords
import logging

sys.path.insert(0,'..')

import chronostar.coordinate_fun as cf

def test_calcGCToEQMatrix():
    """
    Check the implementation of Johnson and Soderblom 1987
    """
    old_a_ngp = 192.25 * u.degree
    old_d_ngp = 27.4 * u.degree
    old_th = 123 * u.degree

    js1987 = np.array([
        [-0.06699, -0.87276, -0.48354],
        [0.49273, -0.45035, 0.74458],
        [-0.86760, -0.18837, 0.46020],
    ])

    assert np.allclose(
        js1987, cf.calcGCToEQMatrix(old_a_ngp,old_d_ngp,old_th),
        rtol=1e-4
    )

def test_CartesianAngleConversions():
    sphere_pos_list = [
        (0,0),
        (45,0),
        (-45,0),
        (0,45),
        (0,90),
    ]

    cart_list = [
        (1,0,0),
        (np.sqrt(0.5), np.sqrt(0.5), 0),
        (np.sqrt(0.5), -np.sqrt(0.5), 0),
        (np.sqrt(0.5), 0, np.sqrt(0.5)),
        (0, 0, 1)
    ]

    for sphere_pos, cart in zip(sphere_pos_list, cart_list):
        cart = cf.convertAnglesToCartesian(*sphere_pos)
        sphere_pos2 = cf.convertCartesianToAngles(*cart)
        assert np.allclose(sphere_pos,
                           [c.value for c in sphere_pos2])
