*** Settings ***
Library    AsyncLibrary

*** Test Cases ***
Example
    ${handle 1}    Async Run    Deeply Nested Sleep    5    
    ${handle 2}    Async Run    Nested Sleep    4
    ${handle 3}    Async Run    Sleep    3
    ${handle 4}    Async Run    Deeply Nested Fail
    ${handle 5}    Async Run    Deeply Nested Fail
    
    ${handles}    Create List
    ...    ${handle 1}
    ...    ${handle 2}
    ...    ${handle 3}
    ...    ${handle 4}

    ${return_value}    Async Get    ${handles}

*** Keywords ***
Nested Sleep
    [Arguments]    ${time}
    Log To Console    Nested Sleep ${time}
    Sleep    ${time}


Deeply Nested Sleep
    [Arguments]    ${time}
    Log To Console    Deeply Nested Sleep ${time}
    Nested Sleep    ${time}

Deeply Nested Fail
    Fail    should fail
