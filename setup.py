from setuptools import setup
from os import path

# Read the contents of the README file for the long description on PyPI
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='cbpi4-tasmota-scurveagitator',
    version='1.0.0',
    description='CraftBeerPi4 Actor Plugin for Tasmota PWM Agitator with S-Curve Soft-Start/Stop Ramping',
    author='Reinhard A. Bergmann',
    author_email='reinhard.bergmann@web.de',
    url='https://github.com/kaeptn-h/cbpi4-Tasmota-S-CurveAgitator',
    license='MIT',
    include_package_data=True,
    package_data={
        '': ['*.txt', '*.rst', '*.yaml'],
        'cbpi4_tasmota_scurveagitator': ['*', '*.txt', '*.rst', '*.yaml'],
    },
    packages=['cbpi4_tasmota_scurveagitator'],
    install_requires=[
        'cbpi4>=4.0.0',
    ],
    entry_points={
        'cbpi4.plugins': [
            'cbpi4_tasmota_scurveagitator = cbpi4_tasmota_scurveagitator'
        ],
    },
    long_description=long_description,
    long_description_content_type='text/markdown',
)
