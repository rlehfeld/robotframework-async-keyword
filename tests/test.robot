*** Settings ***
Library    AsyncLibrary

*** Test Cases ***
Example
    ${handle 1}    Async Run    Deeply Nested Keyword    ${1}
    ${handle 2}    Async Run    Nested Keyword    ${2}
    ${handle 3}    Async Run    Set Variable    ${3}
    ${handle 4}    Async Run    Deeply Nested Fail
    ${handle 5}    Async Run    Deeply Nested Fail
    
    ${handles}    Create List
    ...    ${handle 3}
    ...    ${handle 2}
    ...    ${handle 1}

    ${return_value}    Async Get    ${handles}
    Log To Console    ${return_value}

    ${expected}    Create List   ${3}   ${2}    ${1}
    Log To Console    ${expected}

    Should Be True    $return_value==$expected

    Run Keyword And Expect Error    should fail
    ...    Async Get    ${handle 4}


*** Keywords ***
Nested Keyword
    [Arguments]    ${value}
    Log To Console    Got Value ${value}
    ${return}    Set Variable    ${value}
    RETURN    ${return}

Deeply Nested Keyword
    [Arguments]    ${value}
    Log To Console    Deeply Nested Keyword ${value}
    ${return}    Nested Keyword    ${value}
    RETURN    ${return}

Deeply Nested Fail
    Fail    should fail
