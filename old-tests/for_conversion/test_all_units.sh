# Basic script which runs all the unit tests
# currently broken because input files for some if the unit tests are
# transient in nature
echo '___ Testing swig setup ___'
rm chronostar/_overlap.so
python setup.py build_ext -b .
echo '___ Swig setup passing all tests ___'
python -W ignore unit_test_maths.py
python -W ignore unit_test_swig_module.py
python -W ignore unit_test_group_fitter.py --debug
python -W ignore unit_test_group_fitter.py -b 10 -p 20 --run --debug
python -W ignore unit_test_analyser.py
echo '___ Entire test suite passing ___'