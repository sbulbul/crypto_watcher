Feature: Home / Scanner page

  @smoke
  Scenario: Home page loads and can start a scan
    Given I am on the "/" page
    Then I should see a heading "Crypto Hourly Watcher"
    When I set the scan limit to "250"
    And I click "Scan Crypto"
    Then I should see the scan in progress
    When I stop the scan
