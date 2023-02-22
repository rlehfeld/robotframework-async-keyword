Generic Robot Framework library for asynchronous keyword execution

Installation
============
If you have pip and git installed:
``pip install git+https://github.com/rlehfeld/robotframework-async.git``

Usage
=====
#) Import into a test suite with:
    ``Library AsyncLibrary``

#) To run a keyword asynchronously:
    ``${handle}    async run    some keyword    first argument    second argument``

#) To retrieve the return value, a blocking call to async_get is called with the handle:
    ``${return_value}    async get    ${handle}``
