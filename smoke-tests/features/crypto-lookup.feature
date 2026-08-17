Feature: Crypto Lookup page

  @smoke
  Scenario: Crypto Lookup page loads and returns a lookup result
    Given I am on the "/crypto" page
    Then I should see a heading "Crypto Lookup"
    When I look up ticker "BTC"
    Then I should see a result or a warning
