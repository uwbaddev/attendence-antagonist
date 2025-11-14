# Batching Functionality Test Suite

This Postman collection contains comprehensive tests for the event batching functionality.

## Setup

1. **Import the Collection**
   - Open Postman
   - Click "Import" and select `batching-tests.postman_collection.json`

2. **Configure Environment Variables**
   - The collection uses `{{base_url}}` variable (default: `http://localhost:5000`)
   - Update this in Postman's environment or collection variables if your server runs on a different URL/port

3. **Prerequisites**
   - Ensure your Flask server is running
   - The batch window is set to 5 seconds (as defined in `BATCH_WINDOW_SECONDS`)
   - Have access to your Discord webhook to verify messages are sent correctly

## Test Cases Overview

### Basic Functionality Tests

1. **Health Check** - Verifies the server is running
2. **Single Event - Should Queue** - Tests that a single event is queued
3. **Multiple Events Same Person - Should Batch** - Verifies events for the same person are batched together
4. **Multiple Events Different People - Should Batch Separately** - Ensures different people get separate messages
5. **Same Cell Multiple Changes - Should Merge** - Tests that multiple changes to the same cell merge correctly
6. **Different Cells Same Person - Should Not Merge** - Verifies different cells don't merge
7. **Background Color Changes - Latest Should Win** - Tests that latest bg color is used
8. **NewValue Changes - Latest Should Win** - Tests that latest newValue is used
9. **Mixed bg and newValue Changes - Both Latest Should Merge** - Tests merging of both field types

### Edge Cases

10. **Empty Payload - Should Return 400** - Tests error handling for empty requests
11. **Empty Array - Should Handle Gracefully** - Tests handling of empty array
12. **Missing Person Field - Should Use Unknown** - Tests default person value
13. **Present Status (Green) - Should Identify Correctly** - Tests green color detection
14. **Absent Status (Red) - Should Identify Correctly** - Tests red color detection
15. **Mixed Present and Absent - Should Count Both** - Tests status counting
16. **Large Batch - Multiple People Multiple Events** - Stress test with many events

### Timing Tests

17. **Wait for Batch Window - Verify Timing** - Tests batch window timing (5 seconds)
18. **Sequential Requests Within Window - Should Batch** - Tests rapid sequential requests

## How to Run Tests

### Individual Test
- Select a test from the collection
- Click "Send"
- Check the "Test Results" tab for assertions

### Run Collection
- Click on the collection name
- Click "Run" button
- Select which tests to run
- Click "Run Batching Functionality Test Suite"
- Review results in the test runner

### Automated Testing
- Use Postman CLI (Newman) to run tests:
  ```bash
  newman run batching-tests.postman_collection.json
  ```

## Understanding Batch Behavior

### Batch Window
- Events are batched within a 5-second window (`BATCH_WINDOW_SECONDS = 5`)
- Events older than 5 seconds are processed and sent
- A background thread checks every 5 seconds for ready events

### Batching Rules
1. **By Person**: Events are grouped by person - each person gets one message
2. **By Cell**: Events for the same cell are merged:
   - Latest `bg` (background color) change is kept
   - Latest `newValue` change is kept
   - Both are merged into a single event if they exist
3. **Timing**: Events within the batch window wait; older events are sent immediately

### Verification

To verify batching is working correctly:

1. **Check Server Logs**: Look for messages like:
   - `"Added X event(s) to pending queue. Total pending: Y"`
   - `"Sent batched message for [Person]: 200"`

2. **Check Discord Webhook**: 
   - Verify messages are sent after the batch window
   - Verify multiple events for same person appear in one message
   - Verify different people get separate messages

3. **Timing Verification**:
   - Send an event and wait 6+ seconds
   - Check that the message appears in Discord
   - Send multiple events quickly (within 5 seconds) and verify they batch together

## Test Data Structure

Each event in the test cases follows this structure:
```json
{
    "sheetName": "Fall Attendance",
    "cell": "AG11",
    "newValue": "",
    "bg": "#f4cccc",
    "type_change": "EDIT",
    "type": "6:00pm-7:30pm \nWarrior Zone",
    "practice_date": "2024-10-02T04:00:00.000Z",
    "date_changed": "09-27T09:23Z",
    "person": "Person Name"
}
```

### Key Fields
- `person`: Used for grouping events (required, defaults to "Unknown")
- `cell`: Used for merging events (same cell = merge)
- `bg`: Background color (hex format, e.g., "#f4cccc" for red, "#d9ead3" for green)
- `newValue`: Text value change
- `date_changed`: Timestamp for determining latest change

## Notes

- The batch window is 5 seconds - adjust tests if you change `BATCH_WINDOW_SECONDS`
- Some tests require manual verification (checking Discord webhook)
- The quiet period (Saturday 12:00am to Sunday 7:30pm EST) will cause tests to return 204 but skip notifications
- Tests use various person names to avoid conflicts when running multiple tests

## Troubleshooting

**Tests return 400:**
- Check that the request body is valid JSON
- Ensure Content-Type header is set to `application/json`

**Events not batching:**
- Verify batch window hasn't elapsed
- Check server logs for batch processor thread activity
- Ensure events are sent within the 5-second window

**No messages in Discord:**
- Check WEBHOOK_URL is configured correctly
- Verify you're not in quiet period (Saturday-Sunday)
- Check server logs for webhook errors


