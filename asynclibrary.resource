*** Settings ***
Library  AsyncLibrary/AsyncLibrary.py  WITH NAME  ASYNCLIBRARY


*** Variables ***


*** Keywords ***
Async run ${task}
    return  ASYNCLIBRARY.Async run  ${task}

Async get ${handle}
    return  ASYNCLIBRARY.Async get  ${handle}
