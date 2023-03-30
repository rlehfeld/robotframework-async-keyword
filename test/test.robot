*** Settings ***
Library    AsyncLibrary

*** Test Cases ***
Example
    ${handle 1}    Async Run    Deeply Nested Keyword    ${1}
    ${handle 2}    Async Run    Nested Keyword    ${2}
    ${handle 3}    Async Run    Set Variable    ${3}
    ${handle 4}    Async Run    Deeply Nested Fail    ${4}
    ${handle 5}    Async Run    Deeply Nested Fail    ${5}
    ${handle 6}    Async Run    Deeply Nested Fail    ${6}

    ${handles}    Create List
    ...    ${handle 3}
    ...    ${handle 2}
    ...    ${handle 1}

    ${return_value}    Async Get    ${handles}
    Log To Console    ${return_value}

    ${expected}    Create List   ${3}   ${2}    ${1}
    Log To Console    ${expected}

    Should Be True    $return_value==$expected

    Run Keyword And Expect Error    should fail ${4}
    ...    Async Get    ${handle 4}

    [Teardown]        Run Keyword And Expect Error    should fail ${5}
    ...    Async Get    ${handle 5}

*** Keywords ***
Nested Keyword
    [Arguments]    ${value}
    Sleep    1 sec
    Log To Console    Got Value ${value}
    ${return}    Set Variable    ${value}
    RETURN    ${return}

Deeply Nested Keyword
    [Arguments]    ${value}
    Log To Console    Deeply Nested Keyword ${value}
    ${return}    Nested Keyword    ${value}
    RETURN    ${return}

Deeply Nested Fail
    [Arguments]    ${value}
    Sleep    1 sec
    Fail    should fail ${value}
    [Teardown]    Run Keywords
    ...    Should Be Equal    ${KEYWORD MESSAGE}    should fail ${value}   AND
    ...    Log To Console    Deeply Nested Fail ${KEYWORD MESSAGE}
