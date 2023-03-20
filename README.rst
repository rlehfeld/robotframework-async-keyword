Robot Framework AsyncLibrary
============================
Generic Robot Framework library for asynchronous keyword execution

Installation
============
Install the library from GitHub using pip:

::

    pip install git+https://github.com/rlehfeld/robotframework-async.git

Or add to your ``conda.yaml`` file:

::

    - pip:
        - git+https://github.com/rlehfeld/robotframework-async.git


Usage
=====

#) Import into a test suite with:

   .. code:: robotframework

      Library AsyncLibrary

#) To run a keyword asynchronously:

   .. code:: robotframework

      ${handle}    Async Run    some keyword    first argument    second argument

#) To retrieve the return value, a blocking call to ``Async Get`` is called with the handle:

   .. code:: robotframework

      ${return_value}    Async Get    ${handle}
