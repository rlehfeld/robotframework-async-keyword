Robot Framework AsyncLibrary
============================
Generic Robot Framework library for asynchronous keyword execution

Installation
============
Install the latest release via PyPi using pip:

::

    pip install robotframework-async-keyword

Or add to your ``conda.yaml`` file:

::

    - pip:
        - robotframework-async-keyword


In oder to help with development you can directly install from GitHub via:

::

    pip install git+https://github.com/rlehfeld/robotframework-async-keyword.git

Or add to your ``conda.yaml`` file:

::

    - pip:
        - git+https://github.com/rlehfeld/robotframework-async-keyword.git


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

#) To wait with a timeout use

   .. code:: robotframework

      ${return_value}    Async Get    ${handle}    timeout=5 sec
