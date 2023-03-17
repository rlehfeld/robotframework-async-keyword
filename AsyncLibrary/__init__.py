#    pylint: disable=invalid-name
'''
python extension for Robot Framework in order to add
the possibility to execute keywords asynchronously

The implementation is extensively using monkey patching
as Robot Framework is not prepared for this and as we are
using threads.

Thus currently we only guarantee that the functionality
which we use is working and also is only working with
the Robot Framework Version that we have in use

TODO: add tests for the functionality so it will be executed
      as part of the gitlab testing pipeline
'''
from .robot_async import AsyncLibrary  # noqa, F401
