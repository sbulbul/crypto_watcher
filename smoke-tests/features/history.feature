Feature: History page

  @smoke
  Scenario: History page loads and shows the scan list or an empty state
    Given I am on the "/history" page
    Then I should see a heading "Scan History"
    Then I should see the history list or the empty state
