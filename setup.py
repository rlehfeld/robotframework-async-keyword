'''
setup/install instructions for pip
'''
from setuptools import setup

setup(
    name='robotframework-async',
    version='1.1.2',
    description=(
        'Generic Robot Framework library for asynchronous keyword execution'
    ),
    author='René Lehfeld',
    author_email='54720674+rlehfeld@users.noreply.github.com',
    license='MIT',
    url='https://github.com/rlehfeld/robotframework-async',
    download_url='https://github.com/rlehfeld/robotframework-async',
    keywords=['async', 'robotframework'],
    install_requires=['robotframework >= 5.0.1'],
    packages=['AsyncLibrary'],
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Development Status :: 4 - Beta',
        'Environment :: Other Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ]
)
